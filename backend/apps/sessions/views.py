"""模拟应聘会话 API（PLAN.md §5.3③）——创建 / 列表 / 详情 / 面试计划。

面试计划生成挂在这里（一次 LLM 调用，幂等：已有计划直接返回，force=true 重生成）。
SSE 面试轮次接口在 Phase 3 增量 2（interview turn 状态机）。
"""
import json

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
from .models import (ApplicationSession, CodingAnswer, CodingQuestion, ExamAnswer,
                     ExamQuestion, InterviewPlan, InterviewTurn)

# 进行中轮次的取消信号（打断）：(user_id, session_id) -> Event
_turn_cancels: dict = {}


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
        "review": s.review_json,
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
            weak_points=_weak_points(session),
                quiz_weak=(session.interview_state_json or {}).get("quiz_weak", []),
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
                weak_points=_weak_points(session),
                quiz_weak=(session.interview_state_json or {}).get("quiz_weak", []),
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

    if action == "end":
        # 结束即结束（用户要求）：直接收束会话，不再生成面试官告别语
        seq = session.last_turn_seq + 1
        InterviewTurn.objects.create(
            application=session, seq=seq, role=InterviewTurn.Role.SYSTEM,
            content="（结束面试）", meta={"action": "end"})
        session.last_turn_seq = seq
        session.status = ApplicationSession.Status.FINISHED
        session.finished_at = timezone.now()
        session.save()

        def end_iter():
            yield sse_event("meta", {"session_id": session.id, "seq": seq,
                                    "action": "end", "decided": "end",
                                    "model": session.model_name})
            yield sse_event("done", {"turn": None,
                                    "state": session.interview_state_json,
                                    "status": session.status,
                                    "last_turn_seq": session.last_turn_seq})

        return sse_response(end_iter())

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    now = timezone.now()
    state = dict(session.interview_state_json or {})
    started = session.started_at or now
    state["time_used_min"] = int((now - started).total_seconds() // 60)

    # 本轮发言先行落库（断点续面：即使生成失败，候选人的原话也在）
    seq = session.last_turn_seq + 1
    labels = {"start": "面试开始", "hint": "（提示一下）", "skip": "（换一题）"}
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
                   "skip": "switch_topic"}[action]
        directive = ACTION_DIRECTIVES[decided]

    session.last_turn_seq = seq
    session.interview_state_json = state
    session.status = ApplicationSession.Status.IN_PROGRESS
    session.started_at = started
    session.save()

    q: queue_mod.Queue = queue_mod.Queue()
    cancel = threading.Event()
    _turn_cancels[(session.user_id, session.id)] = cancel

    def worker():
        try:
            messages = build_messages(session, plan.plan_json, content,
                                      directive=directive, exclude_seq=seq)
            result: dict = {}
            chunks: list[str] = []
            interrupted = False
            gen = generate_reply(llm, messages, result)
            try:
                for chunk in gen:
                    if cancel.is_set():  # 打断：停止生成，已流出的部分落库
                        interrupted = True
                        gen.close()
                        break
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

            if interrupted:
                turn = InterviewTurn.objects.create(
                    application_id=session.id, seq=seq + 1,
                    role=InterviewTurn.Role.INTERVIEWER,
                    content="".join(chunks),
                    meta={"partial": True, "interrupted": True})
                session.last_turn_seq = seq + 1
                session.save(update_fields=["last_turn_seq", "updated_at"])
                q.put(("done", {"turn": _turn_payload(turn),
                                "state": session.interview_state_json,
                                "status": session.status,
                                "last_turn_seq": session.last_turn_seq,
                                "interrupted": True}))
                return

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
            _turn_cancels.pop((session.user_id, session.id), None)
            connection.close()

    threading.Thread(target=worker, daemon=True).start()

    def event_iter():
        yield sse_event("meta", {"session_id": session.id, "seq": seq,
                                "action": action, "decided": decided,
                                "model": f"{llm.provider}/{llm.model}"})
        try:
            while True:
                kind, data = q.get()
                yield sse_event(kind, data)
                if kind in ("done", "error"):
                    return
        finally:
            cancel.set()  # 客户端断开/生成器关闭也算打断

    return sse_response(event_iter())


@api_view(["POST"])
def application_turn_cancel(request, pk):
    """打断：停止当前正在生成的面试官回复（已流出部分落库）。"""
    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    cancel = _turn_cancels.get((session.user_id, session.id))
    if cancel:
        cancel.set()
        return Response({"ok": True, "interrupted": True})
    return Response({"ok": True, "interrupted": False})


@api_view(["POST"])
def application_review(request, pk):
    """面试后复盘（§5.3③）：整场对话 -> 维度评估 + 逐题复盘，幂等（force 重生成）。

    Phase 5 的 FinalReport 直接消费 review_json，不再重复分析。
    """
    from .interview import generate_review

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    if session.review_json and not request.data.get("force"):
        return Response({"review": session.review_json, "reused": True})
    if not session.turns.exists():
        return Response({"detail": "还没有面试对话，无法复盘"},
                        status=status.HTTP_400_BAD_REQUEST)

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    role_names = {"interviewer": "面试官", "candidate": "候选人", "system": "（系统）"}
    lines = [f"[{role_names.get(t.role, t.role)}] {t.content}"
             for t in session.turns.all()]
    evals = [d for d in (session.interview_state_json or {}).get("evals_digest", [])]
    if evals:
        lines.append("[面试官隐藏评估摘要] " + json.dumps(evals, ensure_ascii=False)[:2000])
    transcript = "\n".join(lines)

    try:
        review = generate_review(llm, session.job_title, transcript)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    review["model_name"] = f"{llm.provider}/{llm.model}"
    review["generated_at"] = timezone.now().isoformat()
    session.review_json = review
    session.save(update_fields=["review_json", "updated_at"])
    return Response({"review": review, "reused": False})


def _quiz_payload(q: ExamQuestion, with_answers: bool = False) -> dict:
    """试卷题目（默认不下发参考答案/评分要点——防作弊）。"""
    payload = {"id": q.id, "seq": q.seq, "type": q.qtype, "difficulty": q.difficulty,
               "stem": q.stem, "options": q.options, "score_full": q.score_full,
               "knowledge_tag": q.knowledge_tag}
    if with_answers:
        payload["reference_answer"] = q.reference_answer
        payload["scoring_points"] = q.scoring_points
        answer = q.answers.order_by("-submitted_at").first()
        payload["my_answer"] = ({"content": answer.content, "score": answer.score,
                                 "judge": answer.judge_json} if answer else None)
    return payload


@api_view(["GET", "POST"])
def application_quiz(request, pk):
    """基础笔试：POST 生成试卷（幂等，force 重出）/ GET 取卷（无参考答案）。"""
    from .exam import generate_quiz

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    existing = session.exam_questions.all()

    if request.method == "GET":
        answered = existing.filter(answers__isnull=False).exists()
        total = sum(q.score_full for q in existing)
        got = sum(q.answers.order_by("-submitted_at").first().score or 0
                  for q in existing if q.answers.exists())
        return Response({"questions": [_quiz_payload(q, with_answers=True) for q in existing],
                         "total_full": total, "total_score": got if answered else None})

    if existing and not request.data.get("force"):
        return Response({"questions": [_quiz_payload(q) for q in existing], "reused": True})
    if existing:
        existing.delete()

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    skills = [s.get("name", "") for s in
              (session.resume_version.structured_json or {}).get("skills", [])
              if isinstance(s, dict) and s.get("name")]
    knowledge_points = list(session.job.knowledge_points) if session.job_id else []
    try:
        questions = generate_quiz(llm, job_title=session.job_title,
                                  knowledge_points=knowledge_points,
                                  resume_skills=skills)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    for i, q in enumerate(questions, 1):
        ExamQuestion.objects.create(
            application=session, seq=i, qtype=q["type"], difficulty=q["difficulty"],
            stem=q["stem"], options=q["options"], reference_answer=q["reference_answer"],
            scoring_points=q["scoring_points"], knowledge_tag=q["knowledge_tag"],
            score_full=q["score_full"])
    return Response({"questions": [_quiz_payload(q) for q in session.exam_questions.all()],
                     "reused": False})


@api_view(["POST"])
def application_quiz_submit(request, pk):
    """交卷判分：客观题确定性比对，简答题 LLM 按要点给分；错题考点汇入 quiz_weak。"""
    from .exam import grade_objective, grade_short

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    questions = list(session.exam_questions.all())
    if not questions:
        return Response({"detail": "还没有试卷，请先生成"},
                        status=status.HTTP_400_BAD_REQUEST)
    answers_in = {int(a["question_id"]): a.get("content")
                  for a in request.data.get("answers", [])
                  if str(a.get("question_id", "")).isdigit()}

    needs_llm = any(q.qtype == ExamQuestion.QType.SHORT for q in questions
                    if q.id in answers_in)
    llm = None
    if needs_llm:
        llm, model, err = _llm_or_400(request)
        if err:
            return err

    results = []
    weak: list[str] = []
    for q in questions:
        q.answers.all().delete()  # 重考覆盖旧作答
        given = answers_in.get(q.id)
        qdict = {"type": q.qtype, "stem": q.stem, "reference_answer": q.reference_answer,
                 "scoring_points": q.scoring_points, "score_full": q.score_full}
        if q.qtype == ExamQuestion.QType.SHORT:
            score, judge = grade_short(llm, qdict, str(given or "")) if llm else (0.0, {"reason": "未配置大模型"})
        else:
            score, judge = grade_objective(qdict, given)
        ExamAnswer.objects.create(question=q, content={"given": given},
                                  score=score, judge_json=judge)
        if score < q.score_full * 0.6 and q.knowledge_tag and q.knowledge_tag not in weak:
            weak.append(q.knowledge_tag)
        results.append({**_quiz_payload(q, with_answers=True),
                        "my_answer": {"content": given, "score": score, "judge": judge}})

    state = session.interview_state_json or {}
    state["quiz_weak"] = weak  # 三段联动：错题考点喂给面试官「恰好」追问
    session.interview_state_json = state
    session.save(update_fields=["interview_state_json", "updated_at"])

    total_full = sum(q.score_full for q in questions)
    total = sum(r["my_answer"]["score"] for r in results)
    return Response({"questions": results, "total_full": total_full,
                     "total_score": total, "quiz_weak": weak})


def _coding_payload(q: CodingQuestion, with_answers: bool = False) -> dict:
    """代码题（参考解不下发——改进版参考代码由评审给出）。"""
    payload = {"id": q.id, "seq": q.seq, "stem": q.stem,
               "function_signature": q.function_signature, "examples": q.examples,
               "constraints": q.constraints, "language_hint": q.language_hint,
               "score_full": q.score_full}
    if with_answers:
        answer = q.answers.order_by("-submitted_at").first()
        payload["my_answer"] = ({"code": answer.code, "language": answer.language,
                                 "score": answer.score, "judge": answer.judge_json}
                                if answer else None)
    return payload


@api_view(["GET", "POST"])
def application_coding(request, pk):
    """代码笔试：POST 生成题目（幂等，force 重出）/ GET 取题。"""
    from .coding import generate_coding

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    existing = session.coding_questions.all()

    if request.method == "GET":
        answered = existing.filter(answers__isnull=False).exists()
        total_full = sum(q.score_full for q in existing)
        got = sum(q.answers.order_by("-submitted_at").first().score or 0
                  for q in existing if q.answers.exists())
        return Response({"questions": [_coding_payload(q, with_answers=True) for q in existing],
                         "total_full": total_full, "total_score": got if answered else None})

    if existing and not request.data.get("force"):
        return Response({"questions": [_coding_payload(q) for q in existing], "reused": True})
    if existing:
        existing.delete()

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    skills = [s.get("name", "") for s in
              (session.resume_version.structured_json or {}).get("skills", [])
              if isinstance(s, dict) and s.get("name")]
    topics = list(session.job.coding_topics) if session.job_id else []
    try:
        questions = generate_coding(llm, job_title=session.job_title,
                                    coding_topics=topics, resume_skills=skills)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    for i, q in enumerate(questions, 1):
        CodingQuestion.objects.create(
            application=session, seq=i, stem=q["stem"],
            function_signature=q["function_signature"], examples=q["examples"],
            constraints=q["constraints"], language_hint=q["language_hint"],
            score_full=q["score_full"], reference_solution=q["reference_solution"])
    return Response({"questions": [_coding_payload(q) for q in session.coding_questions.all()],
                     "reused": False})


@api_view(["POST"])
def application_coding_submit(request, pk):
    """提交代码 → LLM 四维评审（AI 评审，不做在线判题）。"""
    from .coding import review_code

    session = get_object_or_404(ApplicationSession, pk=pk, user=request.user)
    questions = list(session.coding_questions.all())
    if not questions:
        return Response({"detail": "还没有代码题，请先生成"},
                        status=status.HTTP_400_BAD_REQUEST)
    answers_in = {int(a["question_id"]): a
                  for a in request.data.get("answers", [])
                  if str(a.get("question_id", "")).isdigit()}

    llm, model, err = _llm_or_400(request)
    if err:
        return err

    results = []
    for q in questions:
        q.answers.all().delete()  # 重考覆盖
        given = answers_in.get(q.id) or {}
        code = str(given.get("code", ""))
        language = str(given.get("language", q.language_hint or "python"))[:20]
        if not code.strip():
            score, judge = 0.0, {"reason": "未作答"}
        else:
            score, judge = review_code(llm, {"stem": q.stem,
                                             "function_signature": q.function_signature,
                                             "examples": q.examples,
                                             "constraints": q.constraints,
                                             "score_full": q.score_full},
                                       code, language)
        CodingAnswer.objects.create(question=q, code=code, language=language,
                                    score=score, judge_json=judge)
        results.append({**_coding_payload(q, with_answers=True),
                        "my_answer": {"code": code, "language": language,
                                      "score": score, "judge": judge}})

    total_full = sum(q.score_full for q in questions)
    total = sum(r["my_answer"]["score"] for r in results)
    return Response({"questions": results, "total_full": total_full, "total_score": total})
