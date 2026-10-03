"""模拟应聘会话 API（PLAN.md §5.3③）——创建 / 列表 / 详情 / 面试计划。

面试计划生成挂在这里（一次 LLM 调用，幂等：已有计划直接返回，force=true 重生成）。
SSE 面试轮次接口在 Phase 3 增量 2（interview turn 状态机）。
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.llm import pick_llm
from apps.jobs.models import JobPosition, JobProfile, JobSelfCheck
from apps.resumes.models import Resume
from core.llm_adapter import LLMClient

from .interview import generate_plan
from .models import ApplicationSession, InterviewPlan, InterviewTurn


def _resolve_resume_version(request):
    resume_id = request.data.get("resume_id")
    if resume_id:
        resume = get_object_or_404(Resume, pk=resume_id, user=request.user)
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


def _target_context(data: dict, user=None):
    """Resolve (job_id | job_profile_id) -> (job, job_profile, job_title, jd_text)."""
    if data.get("job_profile_id"):
        qs = JobProfile.objects.filter(pk=data["job_profile_id"])
        if user is not None:
            qs = qs.filter(user=user)
        job_profile = get_object_or_404(qs)
        return None, job_profile, job_profile.title, job_profile.jd_text
    if data.get("job_id"):
        job = get_object_or_404(JobPosition, pk=data["job_id"], is_active=True)
        jd_text = (f"{job.description}\n岗位要求："
                   + "；".join(f"{r['skill']}({'必会' if r.get('required') else '加分'})"
                              for r in job.skill_requirements)
                   + f"\n面试重点：{'、'.join(job.interview_focus)}")
        return job, None, f"{job.title}（{job.level}）", jd_text
    return None, None, "", ""


def _weak_points(session) -> list[str]:
    """考点自评薄弱项（模糊/不会）——喂给面试官的重点考察目标（备考工作台联动）。"""
    if not session.job_id:
        return []
    checks = JobSelfCheck.objects.filter(user=session.user, job=session.job).first()
    if not checks:
        return []
    return [point for point, state in checks.checks_json.items()
            if state in ("模糊", "不会")]


def _turn_payload(t: InterviewTurn) -> dict:
    return {"seq": t.seq, "role": t.role, "content": t.content,
            "meta": t.meta, "has_eval": t.eval_json is not None,
            "created_at": t.created_at.isoformat()}


def _session_payload(s: ApplicationSession, *, with_plan=False,
                     with_turns=False) -> dict:
    payload = {
        "id": s.id,
        "status": s.status,
        "current_stage": s.current_stage,
        "settings": s.settings_json,
        "job": ({"id": s.job_id, "title": s.job.title, "level": s.job.level}
                if s.job_id else None),
        "job_profile": ({"id": s.job_profile_id, "title": s.job_profile.title}
                        if s.job_profile_id else None),
        "job_title": s.job_title,
        "resume_version": {"id": s.resume_version_id,
                           "version_no": s.resume_version.version_no},
        "model_name": s.model_name,
        "interview_state": s.interview_state_json,
        "last_turn_seq": s.last_turn_seq,
        "has_plan": InterviewPlan.objects.filter(application=s).exists(),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        "updated_at": s.updated_at.isoformat(),
        "created_at": s.created_at.isoformat(),
    }
    if with_plan:
        plan = InterviewPlan.objects.filter(application=s).first()
        payload["plan"] = plan.plan_json if plan else None
        payload["plan_model"] = plan.model_name if plan else ""
    if with_turns:
        payload["turns"] = [_turn_payload(t) for t in s.turns.all()[:50]]
    return payload


@api_view(["GET", "POST"])
def application_list(request):
    if request.method == "GET":
        sessions = ApplicationSession.objects.filter(user=request.user) \
            .select_related("job", "job_profile", "resume_version")
        items = [{
            "id": s.id, "status": s.status, "current_stage": s.current_stage,
            "job_title": s.job_title,
            "job": ({"id": s.job_id, "title": s.job.title} if s.job_id else None),
            "job_profile": ({"id": s.job_profile_id, "title": s.job_profile.title}
                            if s.job_profile_id else None),
            "last_turn_seq": s.last_turn_seq,
            "has_plan": InterviewPlan.objects.filter(application=s).exists(),
            "updated_at": s.updated_at.isoformat(),
            "created_at": s.created_at.isoformat(),
        } for s in sessions]
        return Response(items)

    # POST — create a session for job_id | job_profile_id
    job, job_profile, job_title, jd_text = _target_context(request.data, request.user)
    if not job and not job_profile:
        return Response({"detail": "需要 job_id 或 job_profile_id"},
                        status=status.HTTP_400_BAD_REQUEST)
    version = _resolve_resume_version(request)
    if version is None:
        return Response({"detail": "没有可用的简历版本，请先解析简历"},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        duration_min = max(10, min(120, int(request.data.get("duration_min", 30))))
    except (TypeError, ValueError):
        duration_min = 30
    strict_mode = bool(request.data.get("strict_mode", False))

    cred, model = pick_llm(request.user)
    session = ApplicationSession.objects.create(
        user=request.user, job=job, job_profile=job_profile,
        resume_version=version,
        provider=cred.provider if cred else "", model_name=model or "",
        settings_json={"duration_min": duration_min, "strict_mode": strict_mode},
        interview_state_json={"phase": None, "time_used_min": 0,
                              "asked_question_ids": [], "evals_digest": [],
                              "dangling_threads": [], "found_flaws": [],
                              "found_highlights": [], "plan_adjustments": []},
    )
    return Response(_session_payload(session), status=status.HTTP_201_CREATED)


@api_view(["GET"])
def application_detail(request, pk):
    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    return Response(_session_payload(session, with_plan=True, with_turns=True))


@api_view(["POST"])
def application_plan(request, pk):
    """Generate the interview plan (idempotent; force=true to regenerate)."""
    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    existing = InterviewPlan.objects.filter(application=session).first()
    if existing and not request.data.get("force"):
        return Response({"plan": existing.plan_json, "reused": True,
                        "model_name": existing.model_name})

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    _, _, job_title, jd_text = _target_context(
        {"job_id": session.job_id, "job_profile_id": session.job_profile_id},
        request.user)
    settings_json = session.settings_json or {}
    try:
        plan_json = generate_plan(
            llm, session.resume_version.structured_json,
            job_title=job_title, jd_text=jd_text,
            weak_points=_weak_points(session), quiz_weak=[],
            duration_min=settings_json.get("duration_min", 30),
            strict_mode=settings_json.get("strict_mode", False))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    plan, _ = InterviewPlan.objects.update_or_create(
        application=session,
        defaults={"plan_json": plan_json, "model_name": f"{llm.provider}/{llm.model}"})
    if session.status == ApplicationSession.Status.CREATED:
        session.status = ApplicationSession.Status.IN_PROGRESS
        session.started_at = session.started_at or timezone.now()
        session.save(update_fields=["status", "started_at", "updated_at"])
    return Response({"plan": plan.plan_json, "reused": False,
                    "model_name": plan.model_name})


@api_view(["POST"])
def application_plan_stream(request, pk):
    """SSE: plan generation with live progress — `stage`/`tick` events while the
    LLM streams (tick carries the questions discovered so far), then `done` with
    the validated plan. The loading UI renders ticks as a live reveal.
    """
    import queue as queue_mod
    import threading

    from django.db import connection

    from core.sse import sse_event, sse_response

    from .interview import extract_plan_hints

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    existing = InterviewPlan.objects.filter(application=session).first()
    if existing and not request.data.get("force"):
        def ready_iter():
            yield sse_event("done", {"plan": existing.plan_json, "reused": True,
                                    "model_name": existing.model_name})
        return sse_response(ready_iter())

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    _, _, job_title, jd_text = _target_context(
        {"job_id": session.job_id, "job_profile_id": session.job_profile_id},
        request.user)
    settings_json = session.settings_json or {}
    q: queue_mod.Queue = queue_mod.Queue()

    def worker():
        try:
            seen = [0]

            def on_tick(buf):
                hints = extract_plan_hints(buf)
                if len(hints) > seen[0]:
                    seen[0] = len(hints)
                    q.put(("tick", {"items": hints}))

            plan_json = generate_plan(
                llm, session.resume_version.structured_json,
                job_title=job_title, jd_text=jd_text,
                weak_points=_weak_points(session), quiz_weak=[],
                duration_min=settings_json.get("duration_min", 30),
                strict_mode=settings_json.get("strict_mode", False),
                on_tick=on_tick)
            plan, _ = InterviewPlan.objects.update_or_create(
                application=session,
                defaults={"plan_json": plan_json,
                          "model_name": f"{llm.provider}/{llm.model}"})
            if session.status == ApplicationSession.Status.CREATED:
                session.status = ApplicationSession.Status.IN_PROGRESS
                session.started_at = session.started_at or timezone.now()
                session.save(update_fields=["status", "started_at", "updated_at"])
            q.put(("done", {"plan": plan.plan_json, "reused": False,
                            "model_name": plan.model_name}))
        except ValueError as exc:
            q.put(("error", {"detail": str(exc)}))
        finally:
            connection.close()

    threading.Thread(target=worker, daemon=True).start()

    def event_iter():
        yield sse_event("stage", {"stage": "generating"})
        while True:
            kind, data = q.get()
            yield sse_event(kind, data)
            if kind in ("done", "error"):
                return

    return sse_response(event_iter())


@api_view(["POST"])
def application_turn(request, pk):
    """SSE：候选人发言（或 start/hint/skip/end）→ 流式返回面试官回复。

    隐藏评估 [EVAL] 标记行在服务端剥离，绝不泄露给候选人；回复完成后
    逐轮落库 InterviewTurn 并更新 interview_state_json（断点续面的事实来源）。
    """
    import queue as queue_mod
    import threading

    from django.db import connection

    from core.sse import sse_event, sse_response

    from .engine import (ACTION_DIRECTIVES, apply_eval_to_state, build_messages,
                         decide_action, generate_reply, prohibition_hits,
                         summarize_history)

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    if session.status == ApplicationSession.Status.FINISHED:
        return Response({"detail": "这场面试已结束"}, status=status.HTTP_400_BAD_REQUEST)
    plan = InterviewPlan.objects.filter(application=session).first()
    if not plan:
        return Response({"detail": "请先生成面试计划"},
                        status=status.HTTP_400_BAD_REQUEST)

    action = request.data.get("action") or (
        "start" if session.last_turn_seq == 0 else "answer")
    content = (request.data.get("content") or "").strip()
    if action == "answer" and not content:
        return Response({"detail": "回答内容不能为空"},
                        status=status.HTTP_400_BAD_REQUEST)
    if action == "start" and session.last_turn_seq > 0:
        return Response({"detail": "面试已开始"}, status=status.HTTP_400_BAD_REQUEST)

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    now = timezone.now()
    state = dict(session.interview_state_json or {})
    started = session.started_at or now
    state["time_used_min"] = int((now - started).total_seconds() // 60)

    # 本轮发言先行落库（断点续面：即使生成失败，候选人的原话也在）
    seq = session.last_turn_seq + 1
    labels = {"start": "面试开始", "hint": "（提示一下）",
              "skip": "（换一题）", "end": "（结束面试）"}
    candidate_turn = InterviewTurn.objects.create(
        application=session, seq=seq,
        role=(InterviewTurn.Role.CANDIDATE if action == "answer"
              else InterviewTurn.Role.SYSTEM),
        content=content if action == "answer" else labels.get(action, content),
        meta={"action": action, **({"note": content} if action in ("hint", "skip", "end") else {})})

    # 后端状态机的下一步动作（机制 2）——客户端指令优先，其余由上一轮隐藏评估决定
    if action == "answer":
        last_eval = (session.turns.filter(role=InterviewTurn.Role.INTERVIEWER)
                     .order_by("-seq").values_list("eval_json", flat=True).first())
        decided = decide_action(last_eval)
        directive = ACTION_DIRECTIVES.get(decided, "")
    else:
        decided = {"start": "continue", "hint": "give_hint",
                   "skip": "switch_topic", "end": "farewell"}[action]
        directive = ACTION_DIRECTIVES[decided]

    session.last_turn_seq = seq
    session.interview_state_json = state
    session.status = ApplicationSession.Status.IN_PROGRESS
    session.started_at = started
    session.save()

    q: queue_mod.Queue = queue_mod.Queue()

    def worker():
        try:
            messages = build_messages(session, plan.plan_json, content,
                                      directive=directive, exclude_seq=seq)
            result: dict = {}
            chunks: list[str] = []
            try:
                for chunk in generate_reply(llm, messages, result):
                    chunks.append(chunk)
                    q.put(("delta", {"text": chunk}))
            except Exception as exc:  # noqa: BLE001 — 流中断：partial 落库
                InterviewTurn.objects.create(
                    application_id=session.id, seq=seq + 1,
                    role=InterviewTurn.Role.INTERVIEWER,
                    content="".join(chunks), meta={"partial": True})
                session.last_turn_seq = seq + 1
                session.save(update_fields=["last_turn_seq", "updated_at"])
                raise exc

            visible = result.get("visible", "")
            eval_data = result.get("eval")
            next_action = decide_action(eval_data) if action == "answer" else decided
            turn = InterviewTurn.objects.create(
                application_id=session.id, seq=seq + 1,
                role=InterviewTurn.Role.INTERVIEWER, content=visible,
                eval_json=eval_data,
                meta={"phase": state.get("phase"), "action": next_action,
                      "prohibitions": prohibition_hits(visible)})
            new_state = apply_eval_to_state(state, eval_data, seq=seq + 1,
                                            plan_json=plan.plan_json,
                                            visible=visible)
            if action == "end":
                session.status = ApplicationSession.Status.FINISHED
                session.finished_at = timezone.now()
            session.interview_state_json = new_state
            session.last_turn_seq = seq + 1
            session.save()
            summarize_history(llm, session)  # 每 K 轮内部判定
            q.put(("done", {"turn": _turn_payload(turn),
                            "state": session.interview_state_json,
                            "status": session.status,
                            "last_turn_seq": session.last_turn_seq}))
        except Exception as exc:  # noqa: BLE001
            q.put(("error", {"detail": str(exc)}))
        finally:
            connection.close()

    threading.Thread(target=worker, daemon=True).start()

    def event_iter():
        yield sse_event("meta", {"session_id": session.id, "seq": seq,
                                "action": action, "decided": decided,
                                "model": f"{llm.provider}/{llm.model}"})
        while True:
            kind, data = q.get()
            yield sse_event(kind, data)
            if kind in ("done", "error"):
                return

    return sse_response(event_iter())
