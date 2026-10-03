"""面试对话引擎（PLAN.md §5.3③-A/B）——五层上下文组装 + 隐藏评估状态机。

机制落地对照：
- 机制 2 隐藏评估驱动状态机：interviewer 输出 [EVAL] 标记行 → 本模块解析出
  eval_json → decide_action() 由后端决定下一步动作并注入下一轮 prompt
  （题池是弹药库不是剧本）；
- 机制 3 引用原话：候选人关键句保留在滑动窗口里，directive 要求引用；
- 机制 4 动态计划：action=advance 时状态机推进 phase，变更记入 plan_adjustments；
- 机制 5 禁止清单：prohibition_hits() 后端正则初筛，命中记入 turn.meta；
- 机制 6 长程一致性：滚动摘要压缩时保留已问清单/未兑现线索/破绽/亮点。
"""
import json
import re

from core.llm_adapter import ChatMessage, LLMClient

from .interview import INTERVIEWER_SYSTEM, parse_eval_tag

WINDOW_TURNS = 16      # 滑动窗口（最近 N 轮原文）
SUMMARY_EVERY = 6      # 每 K 轮生成一次滚动摘要
TAIL_HOLD = 64         # 流式尾部缓冲：[EVAL] 前缀最长 6 字符，防止隐藏评估泄露
EVALS_DIGEST_MAX = 20

# 机制 5 禁止清单的后端正则初筛（面试官自查兜底之外的第一道闸）
PROHIBITION_PATTERNS = [
    (r"这是一个很好的问题|很好的问题", "客套八股"),
    (r"下面进入第.{1,3}题|接下来是第.{1,3}题", "机械报幕"),
    (r"您(真是|确实)太(棒|厉害)了|非常棒的(回答|想法)", "脱离上下文的夸奖"),
]


def decide_action(eval_data: dict | None) -> str:
    """隐藏评估 → 后端状态机动作（不是线性念题池，§5.3③-A 机制 2）。"""
    if not eval_data:
        return "continue"
    if eval_data.get("off_topic"):
        return "pull_back"
    if (eval_data.get("rote") or (eval_data.get("depth") or 3) <= 2
            or (eval_data.get("understand") or 3) <= 2):
        return "follow_up"
    if eval_data.get("flaw"):
        return "dig_deeper"
    if (eval_data.get("understand") or 3) >= 4 and (eval_data.get("depth") or 3) >= 4:
        return "advance"
    return "continue"


ACTION_DIRECTIVES = {
    "follow_up": "动作：回答偏浅/像背书，沿当前话题深挖追问一层（必须引用候选人刚说的具体内容）。",
    "dig_deeper": "动作：回答里有破绽，抓住这个破绽继续追问核实，不要轻易放过。",
    "advance": "动作：这个话题候选人掌握扎实——快速切换到下一个计划话题，或拔高成开放性难题。",
    "give_hint": "动作：候选人卡壳，给一个方向性提示（只给方向不给答案）后继续。",
    "pull_back": "动作：候选人跑题了，礼貌拉回当前话题再继续。",
    "wrap_up": "动作：时间/进度原因，收敛当前问题并进入下一环节。",
    "switch_topic": "动作：候选人要求换一题，自然过渡到下一个计划话题（不要报幕）。",
    "farewell": "动作：面试结束，简短自然地收尾（可以问候选人有没有想问的，然后道别）。",
    "continue": "动作：按候选人回答自然推进（追问或进入下一话题）。",
}


def prohibition_hits(text: str) -> list[str]:
    """机制 5：禁止清单正则初筛——返回命中的禁止项描述。"""
    hits = []
    for pattern, label in PROHIBITION_PATTERNS:
        if re.search(pattern, text):
            hits.append(label)
    if text.count("？") + text.count("?") >= 3:
        hits.append("一次抛多个问题")
    return hits


def _next_phase(plan_json: dict, state: dict) -> str | None:
    phases = [p.get("name", "") for p in (plan_json.get("phases") or [])]
    if not phases:
        return None
    current = state.get("phase")
    if current in phases:
        idx = phases.index(current)
        return phases[min(idx + 1, len(phases) - 1)]
    return phases[0]


def apply_eval_to_state(state: dict, eval_data: dict | None, *, seq: int,
                        plan_json: dict, visible: str) -> dict:
    """状态层（§5.3③-B）每轮更新：已问/评估摘要/破绽/亮点/线索/计划调整。"""
    state.setdefault("asked_question_ids", [])
    state.setdefault("evals_digest", [])
    state.setdefault("dangling_threads", [])
    state.setdefault("found_flaws", [])
    state.setdefault("found_highlights", [])
    state.setdefault("plan_adjustments", [])

    digest = {"seq": seq, "asked": visible[:40]}
    if eval_data:
        digest.update({k: eval_data.get(k)
                       for k in ("understand", "depth", "rote", "next_action")})
        flaw = (eval_data.get("flaw") or "").strip()
        if flaw and flaw not in [f["text"] for f in state["found_flaws"]]:
            state["found_flaws"].append({"text": flaw, "seq": seq})
        highlight = (eval_data.get("highlight") or "").strip()
        if highlight and highlight not in [h["text"] for h in state["found_highlights"]]:
            state["found_highlights"].append({"text": highlight, "seq": seq})
    state["evals_digest"] = (state["evals_digest"] + [digest])[-EVALS_DIGEST_MAX:]

    # 未兑现线索：面试官说"待会儿/稍后再聊"时记下，后期 prompt 提醒兑现（机制 6）
    for m in re.finditer(r"(?:待会儿|稍后|回头|一会儿)(?:我们)?(?:再|接着)?(?:聊|说|讨论)([^。？!?！\n]{2,30})", visible):
        thread = m.group(1).strip()
        if thread and thread not in state["dangling_threads"]:
            state["dangling_threads"].append(thread)
    state["dangling_threads"] = state["dangling_threads"][-5:]

    # 机制 4：wrap_up/advance 推进 phase，记入计划调整
    action = decide_action(eval_data)
    if action in ("advance", "wrap_up"):
        new_phase = _next_phase(plan_json, state)
        if new_phase and new_phase != state.get("phase"):
            state["phase"] = new_phase
            state["plan_adjustments"].append(
                {"seq": seq, "change": f"进入环节「{new_phase}」"})
            state["plan_adjustments"] = state["plan_adjustments"][-10:]
    return state


def _render_plan(plan_json: dict) -> str:
    lines = []
    briefing = plan_json.get("briefing") or {}
    if briefing.get("persona"):
        lines.append(f"人设：{briefing['persona']}")
    for p in briefing.get("projects", []):
        if not isinstance(p, dict):
            continue
        lines.append(f"· 项目「{p.get('project', '')}」"
                     f" 攻击角度：{'；'.join(p.get('attack_angles', []))}"
                     f"｜待核实：{'；'.join(p.get('metrics_to_verify', []))}"
                     f"｜线索：{'；'.join(p.get('clues', []))}")
    weak = briefing.get("self_check_weak") or []
    if weak:
        lines.append(f"自评薄弱考点（重点考察）：{'、'.join(weak)}")
    lines.append("环节计划：")
    for phase in plan_json.get("phases", []):
        lines.append(f"- {phase.get('name')}（{phase.get('target_min')} 分钟）")
        for q in phase.get("question_pool", []):
            lines.append(f"  · [{q.get('id')}] {q.get('topic')}（难度{q.get('difficulty')}，"
                         f"出题理由：{q.get('why')}）追问：{'；'.join(q.get('followups', []))}")
        for t in phase.get("targets", []):
            lines.append(f"  · 项目深挖「{t.get('project')}」角度：{'、'.join(t.get('angles', []))}")
    return "\n".join(lines)


def build_messages(session, plan_json: dict, candidate_text: str, *,
                   directive: str = "", exclude_seq: int = 0) -> list[ChatMessage]:
    """五层上下文 → chat messages（静态层/状态层/滚动摘要/近期窗口）。

    exclude_seq：本轮候选人发言已先行落库，窗口里要跳过它（末尾统一以
    user 消息注入，避免同一内容出现两次）。"""
    state = session.interview_state_json or {}
    settings_json = session.settings_json or {}
    strict_clause = "（严格模式开启：卡壳也不给台阶）" if settings_json.get("strict_mode") else ""

    system_text = INTERVIEWER_SYSTEM
    for key, value in (
        ("{plan_briefing}", _render_plan(plan_json)),
        ("{asked_questions}", "；".join(d["asked"] for d in state.get("evals_digest", [])) or "（还没有）"),
        ("{dangling_threads}", "、".join(state.get("dangling_threads", [])) or "（无）"),
        ("{found_flaws}", "；".join(f["text"] for f in state.get("found_flaws", [])) or "（无）"),
        ("{found_highlights}", "；".join(h["text"] for h in state.get("found_highlights", [])) or "（无）"),
        ("{strict_clause}", strict_clause),
    ):
        system_text = system_text.replace(key, value)

    messages = [ChatMessage(role="system", content=system_text)]

    # 状态层补充：时间预算 + 当前环节 + 下一步动作（后端状态机的决定）
    used_min = state.get("time_used_min", 0)
    budget = settings_json.get("duration_min", 30)
    notes = [f"进度：已用约 {used_min} 分钟 / 总预算 {budget} 分钟；当前环节：{state.get('phase') or '开场'}。"]
    if directive:
        notes.append(directive)
    messages.append(ChatMessage(role="system", content="\n".join(notes)))

    # 滚动摘要（机制 6：压缩早期对话但保留已问/线索/破绽/亮点）
    if session.context_summary:
        messages.append(ChatMessage(
            role="system",
            content=f"此前对话的压缩摘要（不要重复摘要里已问过的问题）：\n{session.context_summary}"))

    # 近期原文滑动窗口
    window = [t for t in session.turns.all().order_by("-seq")[:WINDOW_TURNS]
              if t.seq < exclude_seq]
    for turn in reversed(window):
        if turn.role == "system":
            continue
        role = "assistant" if turn.role == "interviewer" else "user"
        messages.append(ChatMessage(role=role, content=turn.content))

    # 本轮候选人发言（start 开场时为空，用系统 cue 代替）
    if candidate_text.strip():
        messages.append(ChatMessage(role="user", content=candidate_text.strip()))
    else:
        messages.append(ChatMessage(
            role="user",
            content="（面试开始。请按计划的自我介绍环节开场，自然地说出开场白并提出第一个问题。）"))
    return messages


def generate_reply(llm: LLMClient, messages: list[ChatMessage], result: dict):
    """Yield visible deltas while withholding the tail so the hidden [EVAL]
    marker never leaks to the candidate. Fills result["visible"] and
    result["eval"] when the stream completes.
    """
    buf = ""
    emitted = 0
    for delta in llm.chat_stream(messages, temperature=0.7):
        buf += delta
        idx = buf.find("[EVAL")
        if idx != -1:
            safe_end = idx
        else:
            safe_end = len(buf)
            for k in range(1, 6):  # hold back a partial marker prefix at the tail
                if buf.endswith("[EVAL"[:k]):
                    safe_end = len(buf) - k
                    break
        if safe_end > emitted:
            chunk = buf[emitted:safe_end]
            emitted = safe_end
            yield chunk
    visible, eval_data = parse_eval_tag(buf)
    tail = visible[emitted:] if len(visible) > emitted else ""
    if tail:
        yield tail
    result["visible"] = visible
    result["eval"] = eval_data
    result = {}
    buf = ""
    emitted = 0
    for delta in llm.chat_stream(messages, temperature=0.7):
        buf += delta
        idx = buf.find("[EVAL")
        if idx != -1:
            safe_end = idx
        else:
            safe_end = len(buf)
            for k in range(1, 6):
                if buf.endswith("[EVAL"[:k]):
                    safe_end = len(buf) - k
                    break
        if safe_end > emitted:
            chunk = buf[emitted:safe_end]
            emitted = safe_end
            yield chunk
    visible, eval_data = parse_eval_tag(buf)
    tail = visible[emitted:] if len(visible) > emitted else ""
    if tail:
        yield tail
    result["visible"] = visible
    result["eval"] = eval_data


def summarize_history(llm: LLMClient, session) -> str:
    """滚动摘要（机制 6）：压缩窗口之前的对话为一段摘要，保留关键状态。"""
    state = session.interview_state_json or {}
    turns = list(session.turns.all().order_by("seq"))
    covered = session.context_summary_turn_seq
    old = [t for t in turns if t.seq > covered and t.seq <= session.last_turn_seq]
    if len(old) < SUMMARY_EVERY:
        return session.context_summary
    convo = "\n".join(f"[{'面试官' if t.role == 'interviewer' else '候选人'}] {t.content[:200]}"
                      for t in old[:SUMMARY_EVERY * 2])
    prompt = (
        "把下面这段面试对话压缩成 200 字以内的中文摘要，保留：已问主题清单、"
        "候选人关键回答要点、埋下但未兑现的线索。只输出摘要正文。\n\n" + convo)
    try:
        summary = llm.chat([ChatMessage(role="user", content=prompt)], temperature=0.2)
    except Exception:  # noqa: BLE001 — 摘要失败不影响面试本身
        return session.context_summary
    merged = (session.context_summary + "\n" if session.context_summary else "") + summary.strip()
    session.context_summary = merged[-4000:]
    session.context_summary_turn_seq = old[-1].seq
    session.save(update_fields=["context_summary", "context_summary_turn_seq"])
    return session.context_summary
