"""综合报告生成（PLAN.md §5.4）——三段数据 + 隐藏评估 → FinalReport。

产出：总评分 + 录用建议、五维雷达、分段小结、强项/硬伤/改进计划、
diff 式简历修改建议（原句→建议句→理由，理由要像真实面试官的忠告）。
"""
from core.llm_adapter import ChatMessage, LLMClient, LLMError, fast_completion_kwargs

from apps.sessions.interview import _parse_json

REPORT_PROMPT = """你是这场模拟应聘的主面试官。候选人已完成基础笔试、代码笔试和智能面试，请基于全部数据出一份综合总结报告（严格不讨好，像真实面试官的结论）。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "overall_score": 0-100的整数,
  "hire_recommendation": "强推|推荐|待定|不推荐",
  "dimension_radar": {"基础知识": 0-100, "编码能力": 0-100, "项目深度": 0-100, "沟通表达": 0-100, "岗位匹配": 0-100},
  "per_stage_summary": [
    {"stage": "基础笔试", "score": "得分/满分", "summary": "一段小结（含错题知识点）"},
    {"stage": "代码笔试", "score": "得分/满分", "summary": "一段小结（含分项表现）"},
    {"stage": "智能面试", "score": "表现概括", "summary": "一段小结（含追问/拔高/卡壳点）"}
  ],
  "highlights": ["强项（引用具体表现/数据）", "..."],
  "weaknesses": ["硬伤（引用具体表现）", "..."],
  "improvement_plan": [
    {{"area": "改进方向", "action": "下次面试怎么答 + 练习清单（具体可执行）"}}
  ],
  "resume_suggestions": [
    {{"field_path": "projects[0].metrics", "original_text": "简历里的原句（必须逐字来自简历数据）", "suggested_text": "建议改成的句子", "reason": "为什么要改（如：这个指标没写来源，面试必被追问）"}}
  ]
}

硬性要求：
1. 总评分与五维雷达基于证据（笔试得分、代码评审、面试隐藏评估），不讨好；
2. improvement_plan 3-5 条，每条必须给出「下次怎么答」的具体话术方向或练习清单；
3. resume_suggestions 2-5 条：original_text 必须逐字取自「候选人结构化简历」的字段值（改起来才准，禁止取自面试对话），suggested_text 给出更经得起追问的写法，reason 说清面试风险；
4. JSON 严格合法（字符串值内禁英文双引号，引用用「」）；除 JSON 外不要输出任何多余文字。

目标岗位：{job_title}

候选人结构化简历（resume_suggestions 的 original_text 必须逐字取自这里）：
{resume_data}

三段数据：
【基础笔试】
{quiz_data}

【代码笔试】
{coding_data}

【智能面试（含面试官隐藏评估摘要）】
{interview_data}
"""


def _fmt_quiz(questions: list, total_score, total_full) -> str:
    if not questions:
        return "（未作答）"
    lines = [f"得分 {total_score}/{total_full}"]
    for q in questions:
        ans = q.answers.order_by("-submitted_at").first()
        mark = "✓" if ans and ans.score >= q.score_full * 0.6 else "✗"
        lines.append(f"{mark} [{q.knowledge_tag or '通用'}] {q.stem[:60]} "
                     f"({ans.score if ans else 0}/{q.score_full})")
    return "\n".join(lines)


def _fmt_coding(questions: list, total_score, total_full) -> str:
    if not questions:
        return "（未作答）"
    lines = [f"得分 {total_score}/{total_full}"]
    for q in questions:
        ans = q.answers.order_by("-submitted_at").first()
        if not ans:
            lines.append(f"✗ {q.stem[:60]} (未作答)")
            continue
        judge = ans.judge_json or {}
        dims = " ".join(f"{d}:{(judge.get(d) or {}).get('score', 0)}" for d in
                        ("correctness", "edge_cases", "complexity", "style"))
        lines.append(f"~ {q.stem[:60]} ({ans.score}/{q.score_full}) {dims} "
                     f"评语摘要：{judge.get('summary', '')[:60]}")
    return "\n".join(lines)


def _fmt_interview(session) -> str:
    review = session.review_json or {}
    state = session.interview_state_json or {}
    lines = []
    if review:
        dims = review.get("dimensions", {})
        lines.append("面试复盘维度：" + "，".join(f"{k}{v}" for k, v in dims.items()))
        if review.get("overall"):
            lines.append(f"复盘总评：{review['overall']}")
        for w in (review.get("weaknesses") or [])[:3]:
            lines.append(f"不足：{w}")
        for h in (review.get("highlights") or [])[:3]:
            lines.append(f"亮点：{h}")
    evals = state.get("evals_digest", [])[-8:]
    if evals:
        lines.append("隐藏评估摘要：" + json_dumps(evals))
    turns = list(session.turns.filter(role="interviewer")[:10])
    for t in turns:
        lines.append(f"面试官提问：{t.content[:80]}")
    return "\n".join(lines) or "（未进行）"


def json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)[:800]


def generate_report(llm: LLMClient, *, job_title: str, quiz_data: str,
                    coding_data: str, interview_data: str, resume_data: str = "",
                    max_retries: int = 1) -> dict:
    """三段数据 → validated report dict（含 resume_suggestions）。"""
    prompt = (REPORT_PROMPT
              .replace("{job_title}", job_title)
              .replace("{resume_data}", resume_data[:6000])
              .replace("{quiz_data}", quiz_data[:3000])
              .replace("{coding_data}", coding_data[:3000])
              .replace("{interview_data}", interview_data[:5000]))
    messages = [
        ChatMessage(role="system", content="你是严谨的综合评估引擎，只输出合法 JSON。"),
        ChatMessage(role="user", content=prompt),
    ]
    last_err = None
    for _ in range(max_retries + 1):
        try:
            data = _parse_json(llm.chat(messages, temperature=0.2, max_tokens=6000))
            return _validate_report(data)
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            last_err = exc
    raise ValueError(f"综合报告生成失败：{last_err}")


RADAR_DIMS = ("基础知识", "编码能力", "项目深度", "沟通表达", "岗位匹配")


def _validate_report(data: dict) -> dict:
    try:
        data["overall_score"] = max(0, min(100, float(data.get("overall_score", 0))))
    except (TypeError, ValueError):
        data["overall_score"] = 0
    rec = str(data.get("hire_recommendation", "待定"))
    data["hire_recommendation"] = rec if rec in ("强推", "推荐", "待定", "不推荐") else "待定"
    radar = data.get("dimension_radar")
    radar = radar if isinstance(radar, dict) else {}
    clean = {}
    for dim in RADAR_DIMS:
        try:
            clean[dim] = max(0, min(100, int(radar.get(dim, 0))))
        except (TypeError, ValueError):
            clean[dim] = 0
    data["dimension_radar"] = clean
    for key in ("per_stage_summary", "highlights", "weaknesses", "improvement_plan"):
        if not isinstance(data.get(key), list):
            data[key] = []
    data["improvement_plan"] = [
        {"area": str(i.get("area", ""))[:60], "action": str(i.get("action", ""))[:300]}
        for i in data["improvement_plan"] if isinstance(i, dict)]
    suggestions = data.get("resume_suggestions")
    if not isinstance(suggestions, list):
        suggestions = []
    data["resume_suggestions"] = [
        {"field_path": str(s.get("field_path", ""))[:200],
         "original_text": str(s.get("original_text", ""))[:500],
         "suggested_text": str(s.get("suggested_text", ""))[:500],
         "reason": str(s.get("reason", ""))[:300]}
        for s in suggestions
        if isinstance(s, dict) and str(s.get("original_text", "")).strip()]
    return data


def apply_suggestion_to_structured(structured: dict, original: str,
                                   suggested: str) -> tuple[dict, int]:
    """把采纳的建议替换进结构化简历（原文子串匹配；返回 (新结构, 替换处数)）。

    只动在线结构化数据、绝不触碰 PDF——符合解析缓存契约（在线编辑生成新版本）。
    """
    hits = [0]

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and original and original in node:
            hits[0] += node.count(original)
            return node.replace(original, suggested)
        return node

    updated = walk(structured)
    return updated, hits[0]
