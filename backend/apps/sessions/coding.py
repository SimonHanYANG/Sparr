"""代码笔试（PLAN.md §5.3②）——出题 + 大模型检查判卷。

出题：岗位代码题方向 + 简历技术栈，场景化（不出 LeetCode 原题），难度递进 2 题；
判卷：LLM 四维评审（正确性思路/边界处理/复杂度/代码风格）+ 逐条批注 + 改进版参考代码，
UI 明示「AI 评审」，不做在线运行判题。
"""
from core.llm_adapter import ChatMessage, LLMClient, LLMError, fast_completion_kwargs

from .interview import _parse_json

CODING_PROMPT = """你是资深笔试出题人。请为报考「{job_title}」的候选人出 2 道代码笔试题（难度递进：第 1 题中等、第 2 题较难）。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "questions": [
    {
      "id": "c1",
      "stem": "题目描述（真实业务场景 + 功能要求）",
      "function_signature": "def solution(packages: list[dict]) -> list[int]:",
      "examples": [{"input": "示例输入", "output": "期望输出", "note": "补充说明（可空）"}],
      "constraints": "数据规模与复杂度要求",
      "language_hint": "python",
      "score_full": 50,
      "reference_solution": "正确可运行的参考实现（含关键注释）"
    }
  ]
}

硬性规则（违反即作废）：
1. 题目结合岗位代码题方向：{coding_topics} 与候选人技术栈：{resume_skills}，场景化定制（像真实业务题），不出 LeetCode 原题；
2. function_signature 用 Python 风格签名（允许换语言作答）；examples 2-3 个；constraints 写清数据规模；
3. reference_solution 必须正确且能处理 examples；
4. JSON 严格合法（字符串值内禁英文双引号，引用用「」）；除 JSON 外不要输出任何多余文字。
"""

CODING_REVIEW_PROMPT = """你是资深代码评审。请对候选人提交的代码做四维评审（严格不讨好，comment 要指出具体逻辑/行）。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "correctness": {"score": 0-10, "comment": "正确性与解题思路评估"},
  "edge_cases": {"score": 0-10, "comment": "边界处理评估"},
  "complexity": {"score": 0-10, "comment": "时间/空间复杂度评估"},
  "style": {"score": 0-10, "comment": "代码风格与可读性评估"},
  "summary": "一句话总评（50字内）",
  "improved_solution": "改进版参考代码（若提交已足够好，给精简版）"
}

题目：{stem}
函数签名：{signature}
示例与约束：{examples_constraints}
候选人代码（语言 {language}）：
{code}

评分要求：跑不通或思路错误 correctness 直接 ≤3 分；每维 score 是 0-10 整数；JSON 严格合法。
"""

DIMS = ("correctness", "edge_cases", "complexity", "style")


def generate_coding(llm: LLMClient, *, job_title: str, coding_topics: list[str],
                    resume_skills: list[str], max_retries: int = 1) -> list[dict]:
    """两道递进代码题：validated question dicts（含参考解，服务端持有）。"""
    prompt = (CODING_PROMPT
              .replace("{job_title}", job_title)
              .replace("{coding_topics}", "、".join(coding_topics[:8]) or "（通用编程）")
              .replace("{resume_skills}", "、".join(resume_skills[:12]) or "（无）"))
    messages = [
        ChatMessage(role="system", content="你是严谨的代码出题引擎，只输出合法 JSON。"),
        ChatMessage(role="user", content=prompt),
    ]
    last_err = None
    for _ in range(max_retries + 1):
        try:
            data = _parse_json(llm.chat(messages, temperature=0.3, max_tokens=6000,
                                        **fast_completion_kwargs(llm)))
            return _validate_coding(data)
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            last_err = exc
    raise ValueError(f"代码题生成失败：{last_err}")


def _validate_coding(data: dict) -> list[dict]:
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise ValueError("missing questions")
    kept = []
    for q in questions:
        if not isinstance(q, dict) or not q.get("stem"):
            continue
        examples = [e for e in (q.get("examples") or [])
                    if isinstance(e, dict) and e.get("input") is not None]
        try:
            score_full = max(10, min(100, int(q.get("score_full", 50))))
        except (TypeError, ValueError):
            score_full = 50
        kept.append({"id": str(q.get("id") or f"c{len(kept) + 1}"),
                     "stem": str(q["stem"]),
                     "function_signature": str(q.get("function_signature", "")),
                     "examples": [{"input": str(e.get("input", "")),
                                   "output": str(e.get("output", "")),
                                   "note": str(e.get("note", ""))} for e in examples[:3]],
                     "constraints": str(q.get("constraints", "")),
                     "language_hint": str(q.get("language_hint", "python"))[:20],
                     "score_full": score_full,
                     "reference_solution": str(q.get("reference_solution", ""))})
    if not kept:
        raise ValueError("no valid coding question")
    return kept[:2]  # 两题封顶


def review_code(llm: LLMClient, question: dict, code: str, language: str,
                max_retries: int = 1) -> tuple[float, dict]:
    """AI 评审：四维分项 + 批注 + 改进版参考代码。返回 (折算到 score_full 的分, judge_json)。"""
    examples_constraints = "；".join(
        f"例{i + 1}: {e['input']} → {e['output']}" for i, e in enumerate(question["examples"]))
    if question.get("constraints"):
        examples_constraints += f"；约束：{question['constraints']}"
    prompt = (CODING_REVIEW_PROMPT
              .replace("{stem}", question["stem"][:800])
              .replace("{signature}", question["function_signature"][:300])
              .replace("{examples_constraints}", examples_constraints[:600])
              .replace("{language}", language or "python")
              .replace("{code}", (code or "")[:6000]))
    messages = [ChatMessage(role="user", content=prompt)]
    last_err = None
    for _ in range(max_retries + 1):
        try:
            data = _parse_json(llm.chat(messages, temperature=0.1, max_tokens=3000,
                                        **fast_completion_kwargs(llm)))
            judge = _validate_review(data)
            raw = sum(judge[d]["score"] for d in DIMS)  # 0-40
            score = round(raw / 40 * question["score_full"], 1)
            return score, judge
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            last_err = exc
    raise ValueError(f"代码评审失败：{last_err}")


def _validate_review(data: dict) -> dict:
    judge = {}
    for dim in DIMS:
        item = data.get(dim)
        if not isinstance(item, dict):
            item = {}
        try:
            score = max(0, min(10, int(item.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        judge[dim] = {"score": score, "comment": str(item.get("comment", ""))[:300]}
    judge["summary"] = str(data.get("summary", ""))[:120]
    judge["improved_solution"] = str(data.get("improved_solution", ""))[:4000]
    return judge
