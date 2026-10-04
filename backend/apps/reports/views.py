"""综合报告 API（PLAN.md §5.4）——生成/查看报告 + 简历建议采纳闭环。"""
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.llm import pick_llm
from apps.resumes.models import Resume, ResumeVersion
from apps.sessions.models import ApplicationSession
from core.llm_adapter import LLMClient

from .models import FinalReport, ResumeEditSuggestion
from .report import (_fmt_coding, _fmt_interview, _fmt_quiz,
                     apply_suggestion_to_structured, generate_report)


def _llm_or_400(request):
    cred, model = pick_llm(request.user)
    if not cred:
        return None, Response({"detail": "请先在设置中配置大模型 API-Key"},
                              status=status.HTTP_400_BAD_REQUEST)
    llm = LLMClient(provider=cred.provider, api_key=cred.reveal_api_key(),
                    model=model, base_url=cred.base_url or None)
    return llm, None


def _suggestion_payload(s: ResumeEditSuggestion) -> dict:
    return {"id": s.id, "field_path": s.field_path, "original_text": s.original_text,
            "suggested_text": s.suggested_text, "reason": s.reason,
            "status": s.status, "apply_note": s.apply_note}


def _report_payload(report: FinalReport) -> dict:
    return {
        "id": report.id,
        "overall_score": report.overall_score,
        "hire_recommendation": report.hire_recommendation,
        "dimension_radar": report.dimension_radar,
        "stage_scores": report.stage_scores,
        "per_stage_summary": report.per_stage_summary,
        "highlights": report.highlights,
        "weaknesses": report.weaknesses,
        "improvement_plan": report.improvement_plan,
        "model_name": report.model_name,
        "created_at": report.created_at.isoformat(),
        "suggestions": [_suggestion_payload(s) for s in report.suggestions.all()],
    }


@api_view(["GET", "POST"])
def application_report(request, pk):
    """综合报告：POST 生成（幂等，force 重出）/ GET 查看。"""
    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    existing = FinalReport.objects.filter(application=session).first()

    if request.method == "GET":
        return Response({"report": _report_payload(existing) if existing else None})

    if existing and not request.data.get("force"):
        return Response({"report": _report_payload(existing), "reused": True})
    if existing:
        existing.delete()  # force 重出连同旧建议

    if session.status != ApplicationSession.Status.FINISHED:
        return Response({"detail": "面试还未结束，无法生成综合报告"},
                        status=status.HTTP_400_BAD_REQUEST)

    llm, err = _llm_or_400(request)
    if err:
        return err

    quiz_qs = list(session.exam_questions.all())
    coding_qs = list(session.coding_questions.all())
    quiz_total = sum(q.answers.order_by("-submitted_at").first().score or 0
                     for q in quiz_qs if q.answers.exists())
    coding_total = sum(q.answers.order_by("-submitted_at").first().score or 0
                       for q in coding_qs if q.answers.exists())
    quiz_data = _fmt_quiz(quiz_qs, round(quiz_total, 1), sum(q.score_full for q in quiz_qs))
    coding_data = _fmt_coding(coding_qs, round(coding_total, 1),
                              sum(q.score_full for q in coding_qs))
    interview_data = _fmt_interview(session)
    import json as _json
    resume_data = _json.dumps(session.resume_version.structured_json or {},
                              ensure_ascii=False)

    try:
        data = generate_report(llm, job_title=session.job_title, quiz_data=quiz_data,
                               coding_data=coding_data, interview_data=interview_data,
                               resume_data=resume_data)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    stage_scores = {
        "quiz": round(quiz_total, 1) if quiz_qs else None,
        "coding": round(coding_total, 1) if coding_qs else None,
        "interview": (session.review_json or {}).get("dimensions"),
    }
    report = FinalReport.objects.create(
        user=request.user, application=session,
        overall_score=data["overall_score"],
        hire_recommendation=data["hire_recommendation"],
        dimension_radar=data["dimension_radar"],
        stage_scores=stage_scores,
        per_stage_summary=data["per_stage_summary"],
        highlights=data["highlights"], weaknesses=data["weaknesses"],
        improvement_plan=data["improvement_plan"],
        model_name=f"{llm.provider}/{llm.model}")
    for s in data["resume_suggestions"]:
        ResumeEditSuggestion.objects.create(report=report, **s)
    return Response({"report": _report_payload(report), "reused": False})


def _apply_decision(request, pk, suggestion_id, accept: bool):
    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    suggestion = get_object_or_404(ResumeEditSuggestion, pk=suggestion_id,
                                   report__application=session)
    if suggestion.status != ResumeEditSuggestion.Status.PENDING:
        return Response({"suggestion": _suggestion_payload(suggestion)})

    if not accept:
        suggestion.status = ResumeEditSuggestion.Status.REJECTED
        suggestion.save(update_fields=["status", "updated_at"])
        return Response({"suggestion": _suggestion_payload(suggestion)})

    # 采纳：替换进结构化简历 → 生成新版本（在线编辑，绝不触发 PDF 解析）
    version = session.resume_version
    updated, hits = apply_suggestion_to_structured(
        version.structured_json or {}, suggestion.original_text, suggestion.suggested_text)
    if hits == 0:
        suggestion.status = ResumeEditSuggestion.Status.ACCEPTED
        suggestion.apply_note = "原文未在简历中找到，请手动修改"
    else:
        next_no = max([v.version_no for v in version.resume.versions.all()] or [0]) + 1
        new_version = ResumeVersion.objects.create(
            resume=version.resume, version_no=next_no, structured_json=updated,
            change_note=f"采纳面试修改建议：{suggestion.reason[:60] or suggestion.original_text[:30]}")
        Resume.objects.filter(pk=version.resume_id).update(current_version=new_version)
        suggestion.status = ResumeEditSuggestion.Status.ACCEPTED
        suggestion.apply_note = f"已应用（{hits} 处）→ v{next_no}"
    suggestion.save(update_fields=["status", "apply_note", "updated_at"])
    return Response({"suggestion": _suggestion_payload(suggestion)})


@api_view(["POST"])
def suggestion_accept(request, pk, suggestion_id):
    return _apply_decision(request, pk, suggestion_id, accept=True)


@api_view(["POST"])
def suggestion_reject(request, pk, suggestion_id):
    return _apply_decision(request, pk, suggestion_id, accept=False)
