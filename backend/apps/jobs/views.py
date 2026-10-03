"""Job APIs: catalog browse, custom JD profiles, LLM match analysis."""
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.llm import pick_llm
from apps.profiling.engine import compute_portrait, select_candidate_jobs
from apps.resumes.models import Resume, ResumeVersion
from core.llm_adapter import LLMClient

from .analysis import analyze_catalog, analyze_match
from .models import JobPosition, JobProfile, JobSelfCheck, JobTarget, MatchAnalysis


def _my_annotations(user, jobs):
    """latest LLM match score + target flag per job (备考工作台 personalization)."""
    latest = {}
    for a in MatchAnalysis.objects.filter(user=user, job__isnull=False).order_by("-created_at"):
        latest.setdefault(a.job_id, a.score)
    target_ids = set(JobTarget.objects.filter(user=user, job__isnull=False)
                     .values_list("job_id", flat=True))
    return latest, target_ids


@api_view(["GET"])
def job_list(request):
    qs = JobPosition.objects.filter(is_active=True)
    category = request.query_params.get("category")
    level = request.query_params.get("level")
    if category:
        qs = qs.filter(category=category)
    if level:
        qs = qs.filter(level=level)
    jobs = list(qs)
    latest, target_ids = _my_annotations(request.user, jobs)
    return Response([
        {
            "id": j.id, "category": j.category, "title": j.title, "level": j.level,
            "description": j.description,
            "skill_requirements": j.skill_requirements,
            "affinity_tags": j.affinity_tags,
            "knowledge_points": j.knowledge_points,
            "coding_topics": j.coding_topics,
            "interview_focus": j.interview_focus,
            "my_score": latest.get(j.id),
            "is_target": j.id in target_ids,
        }
        for j in jobs
    ])


@api_view(["POST", "DELETE"])
def job_target(request, job_id):
    job = get_object_or_404(JobPosition, pk=job_id, is_active=True)
    if request.method == "POST":
        JobTarget.objects.get_or_create(user=request.user, job=job)
        return Response({"is_target": True})
    JobTarget.objects.filter(user=request.user, job=job).delete()
    return Response({"is_target": False})


@api_view(["GET", "PUT"])
def job_self_check(request, job_id):
    job = get_object_or_404(JobPosition, pk=job_id, is_active=True)
    check, _ = JobSelfCheck.objects.get_or_create(user=request.user, job=job)
    if request.method == "PUT":
        checks = request.data.get("checks") or {}
        valid = {"掌握", "模糊", "不会"}
        check.checks_json = {k: v for k, v in checks.items() if v in valid}
        check.save(update_fields=["checks_json", "updated_at"])
    return Response({"job_id": job_id, "checks": check.checks_json})


@api_view(["GET"])
def job_targets(request):
    """My target jobs — the main-line shortlist (with latest scores)."""
    targets = JobTarget.objects.filter(user=request.user, job__isnull=False)\
        .select_related("job").order_by("-created_at")
    latest, _ = _my_annotations(request.user, [])
    return Response([
        {
            "id": t.id, "job_id": t.job_id, "title": t.job.title,
            "category": t.job.category, "level": t.job.level,
            "my_score": latest.get(t.job_id),
            "created_at": t.created_at.isoformat(),
        }
        for t in targets
    ])


class JobProfileViewSet(viewsets.ModelViewSet):
    """Custom positions from pasted JDs — any job, not just the catalog."""

    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return JobProfile.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        title = (request.data.get("title") or "").strip()
        jd_text = (request.data.get("jd_text") or "").strip()
        if not title or not jd_text:
            return Response({"detail": "title 与 jd_text 必填"}, status=status.HTTP_400_BAD_REQUEST)
        profile = JobProfile.objects.create(
            user=request.user, title=title[:200], jd_text=jd_text,
            category=request.data.get("category", "")[:10],
            level=request.data.get("level", "")[:10],
        )
        return Response(_profile_payload(profile), status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        return Response([_profile_payload(p) for p in self.get_queryset()])

    def retrieve(self, request, *args, **kwargs):
        return Response(_profile_payload(self.get_object()))


def _profile_payload(p: JobProfile) -> dict:
    return {"id": p.id, "title": p.title, "jd_text": p.jd_text,
            "category": p.category, "level": p.level, "created_at": p.created_at.isoformat()}


def _resolve_resume_version(request):
    resume_id = request.data.get("resume_id")
    if resume_id:
        resume = get_object_or_404(Resume, pk=resume_id, user=request.user)
        if not resume.current_version:
            return None
        return resume.current_version
    resume = (Resume.objects.filter(user=request.user, current_version__isnull=False)
              .order_by("-updated_at").first())
    return resume.current_version if resume else None


def _llm_or_400(request):
    cred, model = pick_llm(request.user)
    if not cred:
        return None, None, Response({"detail": "请先在设置中配置大模型 API-Key"},
                                    status=status.HTTP_400_BAD_REQUEST)
    llm = LLMClient(provider=cred.provider, api_key=cred.reveal_api_key(),
                    model=model, base_url=cred.base_url or None)
    return llm, model, None


def _job_brief(job) -> dict:
    """Title + ALL levels for that role (one card per title; 校招/社招 merged)."""
    levels = sorted(JobPosition.objects.filter(
        category=job.category, title=job.title).values_list("level", flat=True))
    order = {"实习": 0, "校招": 1, "社招": 2}
    levels.sort(key=lambda lv: order.get(lv, 9))
    return {"id": job.id, "title": job.title, "category": job.category,
            "level": job.level, "levels": levels}


def _analysis_payload(a: MatchAnalysis) -> dict:
    return {
        "id": a.id, "score": a.score, "summary": a.summary,
        "matched": a.matched, "gaps": a.gaps, "advice": a.advice,
        "model_name": a.model_name, "created_at": a.created_at.isoformat(),
        "job": (_job_brief(a.job) if a.job_id else None),
        "job_profile": ({"id": a.job_profile_id, "title": a.job_profile.title}
                        if a.job_profile_id else None),
    }


@api_view(["POST"])
def analyze(request):
    """Analyze one position (job_id preset OR job_profile_id custom) vs resume."""
    version = _resolve_resume_version(request)
    if version is None:
        return Response({"detail": "没有可分析的简历版本"}, status=status.HTTP_400_BAD_REQUEST)
    llm, model, err = _llm_or_400(request)
    if err:
        return err

    job = job_profile = None
    if request.data.get("job_profile_id"):
        job_profile = get_object_or_404(JobProfile, pk=request.data["job_profile_id"],
                                        user=request.user)
        job_title, jd_text = job_profile.title, job_profile.jd_text
    elif request.data.get("job_id"):
        job = get_object_or_404(JobPosition, pk=request.data["job_id"], is_active=True)
        job_title = f"{job.title}（{job.level}）"
        jd_text = (f"{job.description}\n岗位要求："
                   + "；".join(f"{r['skill']}({'必会' if r.get('required') else '加分'})"
                              for r in job.skill_requirements)
                   + f"\n面试重点：{'、'.join(job.interview_focus)}")
    else:
        return Response({"detail": "需要 job_id 或 job_profile_id"},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        eval_data = analyze_match(llm, version.structured_json,
                                  job_title=job_title, jd_text=jd_text)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    analysis = MatchAnalysis.objects.create(
        user=request.user, resume_version=version, job=job, job_profile=job_profile,
        model_name=f"{llm.provider}/{llm.model}",
        score=eval_data["score"], summary=eval_data["summary"],
        matched=eval_data["matched"], gaps=eval_data["gaps"], advice=eval_data["advice"],
    )
    return Response(_analysis_payload(analysis), status=status.HTTP_201_CREATED)


@api_view(["POST"])
def analyze_catalog_view(request):
    """LLM-evaluate the whole preset catalog (parallel per-job; replaces rule scores)."""
    version = _resolve_resume_version(request)
    if version is None:
        return Response({"detail": "没有可分析的简历版本"}, status=status.HTTP_400_BAD_REQUEST)
    llm, model, err = _llm_or_400(request)
    if err:
        return err

    all_jobs = list(JobPosition.objects.filter(is_active=True))
    portrait = compute_portrait(version.structured_json)
    jobs = select_candidate_jobs(all_jobs, portrait)  # adaptive: >=5, fits vary
    try:
        evals = analyze_catalog(llm, version.structured_json, jobs)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    by_id = {j.id: j for j in jobs}
    payload = []
    for ev in evals:
        job = by_id[ev["job_id"]]
        analysis = MatchAnalysis.objects.create(
            user=request.user, resume_version=version, job=job,
            model_name=f"{llm.provider}/{llm.model}",
            score=ev["score"], summary=ev.get("summary", ""),
            matched=ev.get("matched", []), gaps=ev.get("gaps", []),
            advice=ev.get("advice", []),
        )
        payload.append(_analysis_payload(analysis))
    return Response(payload)


@api_view(["POST"])
def analyze_catalog_stream(request):
    """SSE: stream one `eval` event per job as parallel analyses finish."""
    from core.sse import sse_event, sse_response

    version = _resolve_resume_version(request)
    if version is None:
        return Response({"detail": "没有可分析的简历版本"}, status=status.HTTP_400_BAD_REQUEST)
    llm, model, err = _llm_or_400(request)
    if err:
        return err

    all_jobs = list(JobPosition.objects.filter(is_active=True))
    portrait = compute_portrait(version.structured_json)
    jobs = select_candidate_jobs(all_jobs, portrait)  # adaptive: >=5, fits vary

    import queue as queue_mod
    import threading

    from django.db import connection

    q: queue_mod.Queue = queue_mod.Queue()
    user_id = request.user.id
    jobs_by_id = {j.id: j for j in all_jobs}

    def on_result(ev):
        """Runs in pool threads — persist HERE so results survive client disconnect."""
        try:
            analysis = MatchAnalysis.objects.create(
                user_id=user_id, resume_version=version, job=jobs_by_id[ev["job_id"]],
                model_name=f"{llm.provider}/{llm.model}",
                score=ev["score"], summary=ev.get("summary", ""),
                matched=ev.get("matched", []), gaps=ev.get("gaps", []),
                advice=ev.get("advice", []),
            )
            q.put(("eval", _analysis_payload(analysis)))
        finally:
            connection.close()

    def worker():
        try:
            analyze_catalog(llm, version.structured_json, jobs, on_result=on_result)
            q.put(("done", None))
        except ValueError as exc:
            q.put(("error", {"detail": str(exc)}))

    threading.Thread(target=worker, daemon=True).start()

    def event_iter():
        yield sse_event("meta", {"total": len(jobs), "candidates": len(all_jobs),
                                "model": f"{llm.provider}/{llm.model}"})
        finished = 0
        while True:
            kind, data = q.get()
            if kind == "eval":
                finished += 1
                data["progress"] = {"done": finished, "total": len(jobs)}
                yield sse_event("eval", data)
            elif kind == "done":
                yield sse_event("done", {"done": finished, "total": len(jobs)})
                return
            else:
                yield sse_event("error", data)
                return

    return sse_response(event_iter())


@api_view(["GET"])
def analyses_list(request):
    """Latest analysis per target for a resume version — restores UI state."""
    try:
        version = _resolve_resume_version(request)
    except ResumeVersion.DoesNotExist as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    qs = MatchAnalysis.objects.filter(
        user=request.user, resume_version=version).order_by("-created_at")
    seen, items = set(), []
    for a in qs.select_related("job", "job_profile"):
        key = (a.job_id, a.job_profile_id)
        if key in seen:
            continue
        seen.add(key)
        items.append(_analysis_payload(a))
    items.sort(key=lambda x: -x["score"])
    return Response(items)
