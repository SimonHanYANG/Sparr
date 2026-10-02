"""Background parse pipeline: PDF -> MinerU markdown -> LLM structured version.

Runs via core.tasks.dispatch (celery or lite thread) — never blocking the
upload request (PLAN.md §5.1).
"""
import logging

from django.utils import timezone

from core.llm_adapter import LLMClient
from core.mineru_client import MinerUClient, MinerUError
from core.storage import read_upload
from core.tasks import background

logger = logging.getLogger(__name__)

MARKDOWN_KEYS = ("markdown", "md", "md_text", "md_url", "extract_result", "content")


def _pick_llm_credential(user):
    """Prefer DeepSeek, fall back to MiMo — the resume extraction workhorse."""
    from apps.accounts.models import ProviderCredential

    creds = {c.provider: c for c in user.credentials.all()}
    for provider in ("deepseek", "mimo"):
        if provider in creds:
            return creds[provider]
    return None


def _markdown_from_result(item: dict) -> str:
    """Pull markdown text (or download it) out of a MinerU done-result item."""
    import httpx

    for key in MARKDOWN_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            if value.lstrip().startswith("http"):
                resp = httpx.get(value, timeout=60)
                resp.raise_for_status()
                return resp.text
            return value
    raise MinerUError(f"no markdown in MinerU result (keys: {list(item.keys())})")


@background
def parse_resume_task(resume_id: int) -> None:
    from .extraction import extract_structured
    from .models import Resume, ResumeVersion

    resume = Resume.objects.select_related("user").get(pk=resume_id)
    resume.parse_status = Resume.ParseStatus.PARSING
    resume.parse_error = ""
    resume.save(update_fields=["parse_status", "parse_error", "updated_at"])

    try:
        # 1. MinerU parse
        mineru_cred = resume.user.credentials.filter(provider="mineru").first()
        if not mineru_cred:
            raise MinerUError("请先在「设置」中添加 MinerU API-Key")
        client = MinerUClient(mineru_cred.reveal_api_key())
        content = read_upload(resume.source_path)
        batch_id = client.submit_pdf(content, resume.source_filename)
        resume.mineru_batch_id = batch_id
        resume.save(update_fields=["mineru_batch_id", "updated_at"])
        result = client.wait_for_result(batch_id)
        markdown = _markdown_from_result(result)
        resume.mineru_markdown = markdown

        # 2. LLM structured extraction
        llm_cred = _pick_llm_credential(resume.user)
        if not llm_cred:
            resume.parse_status = Resume.ParseStatus.FAILED
            resume.parse_error = "简历文本已解析，请先在「设置」中添加大模型 API-Key 后重新解析"
            resume.save(update_fields=["mineru_markdown", "parse_status", "parse_error", "updated_at"])
            return
        llm = LLMClient(provider=llm_cred.provider, api_key=llm_cred.reveal_api_key(),
                        model=llm_cred.model_name or None, base_url=llm_cred.base_url or None)
        structured = extract_structured(markdown, llm)

        # 3. First version
        version = ResumeVersion.objects.create(
            resume=resume, version_no=1, structured_json=structured,
            change_note="自动解析生成",
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
