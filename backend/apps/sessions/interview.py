"""面试计划生成 + 面试官对话 prompt 组装（PLAN.md §5.3③-A/B）。

防机械六机制里由本模块直接承担的：
- 机制 1 因人出题：计划里每道题必须带 `why` 证据（简历项目/技能、JD 要求、
  自评薄弱考点、笔试错题），校验时无 `why` 的题直接丢弃；
- 机制 5 语态真实 + 禁止清单：面试官 system prompt 含真实面试口吻要求与明令禁止项；
- §5.3③-B 静态层：briefing（InterviewBriefing 弹药卡）随计划一次生成、永久复用。
"""
import json
import re

from core.llm_adapter import ChatMessage, LLMClient, LLMError

PLAN_PROMPT = """你是某大厂资深技术面试官。请为「候选人」定制一场 {duration_min} 分钟的面试计划（严格模式：{strict_mode}）。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "briefing": {
    "persona": "面试官人设一句话（方向/资历/风格）",
    "projects": [
      {"project": "简历中的项目名", "attack_angles": ["预判攻击角度（具体到该项目的技术栈/指标）"],
        "metrics_to_verify": ["面试中要核实的指标或说法"], "clues": ["值得深挖的线索"]}
    ],
    "self_check_weak": ["候选人自评模糊/不会、应重点考察的考点"],
    "quiz_weak": ["前序笔试错题知识点（没有则空数组）"]
  },
  "phases": [
    {"name": "自我介绍", "target_min": 3},
    {"name": "基础知识", "target_min": 10,
      "question_pool": [
        {"id": "q1", "topic": "考点（简短）", "difficulty": 3,
          "why": "为什么问这个——必须可追溯到简历某段项目/技能、岗位 JD 要求、自评薄弱考点或笔试错题",
          "followups": ["追问1（引用可能的回答细节）", "追问2"]}
      ]},
    {"name": "项目深挖", "target_min": 20,
      "targets": [
        {"project": "简历项目X", "angles": ["技术选型依据", "最难的点", "指标怎么来的", "量级翻10倍怎么办", "你负责的具体边界"]}
      ]},
    {"name": "场景/系统设计", "target_min": 12, "question_pool": [同上格式]},
    {"name": "候选人提问", "target_min": 5}
  ]
}

硬性规则（违反即作废）：
1. 每道题（含 followups 所属的题）必须有 `why` 证据：可追溯到候选人简历里的具体项目/技能、岗位 JD 的具体要求、自评薄弱考点或笔试错题；不允许通用题库题。
2. 因人出题：题目必须针对这份简历的真实内容定制（项目名、技术栈、指标要出现在题目或 why 里）。
3. 候选人自评「模糊/不会」的考点与笔试错题必须安排进「基础知识」题池或项目深挖追问。
4. 项目深挖 targets 只能取自简历里的真实项目；angles 要具体到该项目。
5. 各 phase 的 target_min 之和 ≈ {duration_min}；difficulty 取 1-5。
6. 题目 id 全局唯一（q1、q2…）。

候选人结构化简历：
{resume}

目标岗位（{job_title}）JD：
{jd}

候选人考点自评薄弱项（模糊/不会）：
{weak_points}

前序笔试错题知识点：
{quiz_weak}
"""

INTERVIEWER_SYSTEM = """你是这场模拟面试的面试官，正在与候选人实时对话。你的口吻要像真实大厂面试官的录音：简短、有停顿感、会说"嗯，你继续""这个你说说看"，不要书面语。

面试计划与弹药（按计划推进，但题池是弹药库不是剧本——根据候选人的回答现场决定追问/拔高/换题/给台阶/收敛）：
{plan_briefing}

已问过的问题（绝不重复）：{asked_questions}
未兑现的线索（之前说过"待会儿聊"，时机到了要兑现）：{dangling_threads}
已发现的破绽（值得打击/核实）：{found_flaws}
已发现的亮点（可拔高或跳过其基础题）：{found_highlights}

自适应规则：
- 回答浅/像背书 → 沿 followups 追一层（"为什么是这样？换成 XX 场景呢？"）
- 回答有破绽 → 抓住追问，不轻易放过
- 回答扎实 → 快速切下一话题，或拔高到开放性难题
- 完全卡壳 → 给台阶/换同主题题{strict_clause}
- 跑题 → 礼貌拉回
- 时间超支 → 收敛问题，进入下一环节

明令禁止（违反即失败）：一次抛多个问题；复读题目；客套八股（"这是一个很好的问题"）；脱离上下文的夸奖；机械报幕（"下面进入第二题"）。

追问必须引用候选人刚说的具体内容（如"你刚才提到用了 Redis 做缓存，为什么不用本地缓存？"），禁止脱离回答的模板式反问。

每次回答候选人后，在你的输出末尾另起一行输出标记行（不要给候选人看的内容写在标记行里）：
[EVAL]{"understand": 1-5, "depth": 1-5, "rote": true/false, "off_topic": true/false, "flaw": "发现的破绽或空字符串", "highlight": "意外亮点或空字符串", "next_action": "follow_up|dig_deeper|switch_topic|give_hint|wrap_up", "comment": "一句话内部备注"}[/EVAL]
标记行是你的隐藏评估，驱动下一步动作，正常输出正文时不要提及它。"""

FOLLOWUP_SYSTEM = """你是这场模拟面试的面试官。候选人刚回答了你的上一个问题，请根据回答内容决定下一步（追问/拔高/换题/给台阶/收敛），并自然地说出来。

要求：引用候选人回答里的具体内容再提问；一次只问一个问题；口吻像真实面试官，禁止客套八股与机械报幕。

在输出末尾另起一行输出隐藏评估标记行：
[EVAL]{"understand": 1-5, "depth": 1-5, "rote": true/false, "off_topic": true/false, "flaw": "", "highlight": "", "next_action": "follow_up|dig_deeper|switch_topic|give_hint|wrap_up", "comment": ""}[/EVAL]"""


def _parse_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[start:end + 1])


def _validate_plan(data: dict, resume_projects: list[str] | None = None) -> dict:
    """Enforce the anti-mechanical contract: questions WITHOUT `why` evidence
    are DROPPED (§5.3③-A 机制 1); project-dig targets must trace back to a real
    resume project when the resume's project names are known."""
    phases = data.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("missing phases")

    def _real_project(name: str) -> bool:
        if not resume_projects:
            return True  # unknown resume -> keep (prompt rule 4 is the guard)
        norm = name.replace(" ", "").lower()
        return any(norm in p.replace(" ", "").lower()
                   or p.replace(" ", "").lower() in norm
                   for p in resume_projects)

    seen_ids: set[str] = set()
    kept_total = 0
    for phase in phases:
        if not isinstance(phase, dict) or not phase.get("name"):
            raise ValueError("bad phase")
        try:
            phase["target_min"] = max(1, int(phase.get("target_min", 5)))
        except (TypeError, ValueError):
            phase["target_min"] = 5
        pool = phase.get("question_pool")
        if isinstance(pool, list):
            kept = []
            for q in pool:
                if not isinstance(q, dict) or not q.get("topic"):
                    continue
                if not (q.get("why") or "").strip():
                    continue  # 机制 1：没有证据的题不许进场
                qid = str(q.get("id") or f"q{len(seen_ids) + 1}")
                if qid in seen_ids:
                    qid = f"{qid}_{len(seen_ids) + 1}"
                q["id"] = qid
                seen_ids.add(qid)
                try:
                    q["difficulty"] = max(1, min(5, int(q.get("difficulty", 3))))
                except (TypeError, ValueError):
                    q["difficulty"] = 3
                if not isinstance(q.get("followups"), list):
                    q["followups"] = []
                kept.append(q)
            phase["question_pool"] = kept
            kept_total += len(kept)
        targets = phase.get("targets")
        if isinstance(targets, list):
            phase["targets"] = [t for t in targets
                                if isinstance(t, dict) and t.get("project")
                                and _real_project(str(t["project"]))]
        else:
            phase["targets"] = []

    if kept_total == 0 and not any(p.get("targets") for p in phases):
        raise ValueError("no question survived `why` validation")

    briefing = data.get("briefing")
    if not isinstance(briefing, dict):
        briefing = {}
    briefing.setdefault("persona", "")
    for key in ("projects", "self_check_weak", "quiz_weak"):
        if not isinstance(briefing.get(key), list):
            briefing[key] = []
    data["briefing"] = briefing
    return data


def generate_plan(llm: LLMClient, structured_resume: dict, *, job_title: str,
                  jd_text: str, weak_points: list[str], quiz_weak: list[str] | None = None,
                  duration_min: int = 30, strict_mode: bool = False,
                  max_retries: int = 2) -> dict:
    """One LLM call -> validated plan_json (briefing + phases)."""
    prompt = (PLAN_PROMPT
              .replace("{duration_min}", str(duration_min))
              .replace("{strict_mode}", "开启（卡壳不给台阶）" if strict_mode else "关闭（卡壳可给台阶）")
              .replace("{resume}", json.dumps(structured_resume, ensure_ascii=False)[:12000])
              .replace("{job_title}", job_title)
              .replace("{jd}", jd_text[:8000])
              .replace("{weak_points}", "、".join(weak_points) if weak_points else "（无）")
              .replace("{quiz_weak}", "、".join(quiz_weak or []) if quiz_weak else "（无）"))
    messages = [
        ChatMessage(role="system", content="你是严谨的面试计划生成引擎，只输出合法 JSON。"),
        ChatMessage(role="user", content=prompt),
    ]
    last_err = None
    resume_projects = [str(p.get("name", "")) for p in
                       (structured_resume.get("projects") or [])
                       if isinstance(p, dict) and p.get("name")]
    for _ in range(max_retries + 1):
        try:
            return _validate_plan(_parse_json(llm.chat(messages, temperature=0.3)),
                                  resume_projects)
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            last_err = exc
    raise ValueError(f"面试计划生成失败：{last_err}")


def parse_eval_tag(content: str) -> tuple[str, dict | None]:
    """Split an interviewer reply into (visible_text, hidden_eval).

    The [EVAL]...[/EVAL] marker line is stripped from what the candidate sees.
    """
    match = re.search(r"\[EVAL\](.*?)\[/EVAL\]", content, re.S)
    if not match:
        return content.strip(), None
    visible = (content[:match.start()] + content[match.end():]).strip()
    try:
        eval_data = json.loads(match.group(1).strip())
    except (ValueError, TypeError):
        return visible, None
    return visible, eval_data if isinstance(eval_data, dict) else None
