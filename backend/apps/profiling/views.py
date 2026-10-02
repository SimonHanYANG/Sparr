"""Profiling APIs (PLAN.md §6): compute portrait + recommendations for a resume version."""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.jobs.models import JobPosition
from apps.resumes.models import Resume, ResumeVersion

from .engine import compute_portrait, direction_scores, recommend
from .models import JobRecommendation, UserPortrait


def _resolve_version(request) -> ResumeVersion:
    resume_id = request.query_params.get("resume_id") or request.data.get("resume_id")
    version_id = request.query_params.get("version_id") or request.data.get("version_id")
    if version_id:
        return ResumeVersion.objects.get(pk=version_id, resume__user=request.user)
    if resume_id:
        resume = Resume.objects.get(pk=resume_id, user=request.user)
        if not resume.current_version:
            raise ResumeVersion.DoesNotExist("resume has no parsed version yet")
        return resume.current_version
    # default: the most recently updated resume with a version
    resume = (Resume.objects.filter(user=request.user, current_version__isnull=False)
              .order_by("-updated_at").first())
    if not resume:
        raise ResumeVersion.DoesNotExist("no parsed resume")
    return resume.current_version


@api_view(["POST"])
def compute(request):
    """(Re)compute portrait + top recommendations for a resume version."""
    try:
        version = _resolve_version(request)
    except ResumeVersion.DoesNotExist as exc:
        return Response({"detail": str(exc)}, status=400)

    jobs = list(JobPosition.objects.filter(is_active=True))
    portrait_json = compute_portrait(version.structured_json)
    portrait_json["direction_scores"] = direction_scores(jobs, portrait_json)

    portrait, _ = UserPortrait.objects.update_or_create(
        user=request.user, resume_version=version,
        defaults={"profile_json": portrait_json},
    )
    portrait.recommendations.all().delete()
    recs = recommend(jobs, portrait_json, top_n=8)
    for rec in recs:
        JobRecommendation.objects.create(
            portrait=portrait, job=rec["job"], score=rec["score"],
            matched_skills=rec["matched_skills"], gap_skills=rec["gap_skills"],
            reasons=rec["reasons"],
        )
    return Response(_payload(portrait))


@api_view(["GET"])
def portrait(request):
    try:
        version = _resolve_version(request)
    except ResumeVersion.DoesNotExist as exc:
        return Response({"detail": str(exc)}, status=404)
    portrait_obj = UserPortrait.objects.filter(
        user=request.user, resume_version=version).prefetch_related("recommendations__job").first()
    if not portrait_obj:
        return Response({"detail": "not computed yet"}, status=404)
    return Response(_payload(portrait_obj))


def _payload(portrait: UserPortrait) -> dict:
    return {
        "portrait": portrait.profile_json,
        "resume_version_id": portrait.resume_version_id,
        "computed_at": portrait.computed_at,
        "recommendations": [
            {
                "id": r.id,
                "job": {"id": r.job_id, "title": r.job.title, "category": r.job.category,
                        "level": r.job.level, "description": r.job.description},
                "score": r.score,
                "matched_skills": r.matched_skills,
                "gap_skills": r.gap_skills,
                "reasons": r.reasons,
            }
            for r in portrait.recommendations.all()
        ],
    }
