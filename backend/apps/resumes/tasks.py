"""Background parse pipeline: PDF -> MinerU markdown -> LLM structured version.

NOTE: this module MUST be imported at app startup (see apps.py ready()) so the
@background decorator registers parse_resume_task — otherwise the web process
dispatches into an empty registry (regression: upload 500).

Runs via core.tasks.dispatch (celery or lite thread) — never blocking the
upload request (PLAN.md §5.1).

MinerU strategy (user requirement): 🎯 accurate parse first; if the cloud
queue is still slow after MINERU_ACCURATE_PATIENCE seconds, fall back to
⚡ Agent lightweight parse. Full contract in core/mineru_client.py.
"""
import hashlib
import logging
import os

from core.llm_adapter import LLMClient
from core.mineru_client import MinerUClient, MinerUError, MinerUTimeout
from core.storage import read_upload
from core.tasks import background

logger = logging.getLogger(__name__)

# How long to wait on the accurate queue before falling back to Agent parse.
ACCURATE_PATIENCE_S = int(os.environ.get("MINERU_ACCURATE_PATIENCE", "300"))


def _pick_llm(user):
    """Pick (credential, model_name) honoring the user's UI preference.

    Preference (UserPreference.llm_provider/llm_model) wins when that provider
    has a stored key; otherwise fallback deepseek -> mimo. Returns (cred, model)
    or (None, None).
    """
    from apps.accounts.models import ProviderCredential, UserPreference

    creds = {c.provider: c for c in user.credentials.all()}
    pref = getattr(user, "llm_preference", None)
    if pref and pref.llm_provider and pref.llm_provider in creds:
        cred = creds[pref.llm_provider]
        return cred, (pref.llm_model or cred.model_name or None)
    for provider in ("deepseek", "mimo"):
        if provider in creds:
            return creds[provider], (creds[provider].model_name or None)
    return None, None


def parse_markdown(client: MinerUClient, content: bytes, filename: str, resume) -> str:
    """Accurate parse with Agent lightweight fallback (returns markdown text).

    Caching rule (user requirement): if the PDF bytes are unchanged
    (md5 == mineru_source_hash) and markdown is already stored, NEVER re-parse
    the PDF — reuse the cached markdown. Only a changed PDF re-triggers MinerU.
    """
    digest = hashlib.md5(content).hexdigest()
    if resume.mineru_markdown and resume.mineru_source_hash == digest:
        logger.info("resume %s: PDF unchanged, reusing cached markdown (skip MinerU)", resume.pk)
        return resume.mineru_markdown

    try:
        batch_id = client.submit_pdf(content, filename)
        resume.mineru_batch_id = f"accurate:{batch_id}"
        resume.save(update_fields=["mineru_batch_id", "updated_at"])
        item = client.wait_for_result(batch_id, timeout_s=ACCURATE_PATIENCE_S)
        markdown = client.fetch_markdown(item)
    except MinerUTimeout:
        logger.info("accurate parse slow (batch %s) — falling back to Agent parse",
                    resume.mineru_batch_id)
        task_id = client.submit_pdf_agent(content, filename)
        resume.mineru_batch_id = f"agent:{task_id}"
        resume.save(update_fields=["mineru_batch_id", "updated_at"])
        item = client.wait_for_agent_result(task_id)
        markdown = client.fetch_agent_markdown(item)

    resume.mineru_source_hash = digest
    resume.save(update_fields=["mineru_source_hash", "updated_at"])
    return markdown


@background
def parse_resume_task(resume_id: int) -> None:
    from .extraction import extract_structured
    from .models import Resume, ResumeVersion

    resume = Resume.objects.select_related("user").get(pk=resume_id)
    resume.parse_status = Resume.ParseStatus.PARSING
    resume.parse_error = ""
    resume.save(update_fields=["parse_status", "parse_error", "updated_at"])

    try:
        # 1. MinerU parse (accurate -> agent fallback)
        mineru_cred = resume.user.credentials.filter(provider="mineru").first()
        if not mineru_cred:
            raise MinerUError("请先在「设置」中添加 MinerU API-Key")
        client = MinerUClient(mineru_cred.reveal_api_key())
        content = read_upload(resume.source_path)
        markdown = parse_markdown(client, content, resume.source_filename, resume)
        resume.mineru_markdown = markdown

        # 2. LLM structured extraction (user-preferred model when set)
        llm_cred, llm_model = _pick_llm(resume.user)
        if not llm_cred:
            resume.parse_status = Resume.ParseStatus.FAILED
            resume.parse_error = "简历文本已解析，请先在「设置」中添加大模型 API-Key 后重新解析"
            resume.save(update_fields=["mineru_markdown", "parse_status", "parse_error", "updated_at"])
            return
        llm = LLMClient(provider=llm_cred.provider, api_key=llm_cred.reveal_api_key(),
                        model=llm_model, base_url=llm_cred.base_url or None)
        structured = extract_structured(markdown, llm)

        # 3. New version (re-parsing appends a version, never overwrites)
        from .models import ResumeVersion

        next_no = (resume.versions.order_by("-version_no").first().version_no + 1
                   if resume.versions.exists() else 1)
        version = ResumeVersion.objects.create(
            resume=resume, version_no=next_no, structured_json=structured,
            change_note=f"自动解析生成（{llm.provider}/{llm.model}）",
        )
        resume.current_version = version
        resume.parse_status = Resume.ParseStatus.PARSED
        resume.save(update_fields=["mineru_markdown", "current_version",
                                   "parse_status", "parse_error", "updated_at"])
    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
        logger.exception("parse_resume_task failed for resume %s", resume_id)
        resume.parse_status = Resume.ParseStatus.FAILED
        resume.parse_error = str(exc)[:1000]
        resume.save(update_fields=["parse_status", "parse_error", "updated_at"])
