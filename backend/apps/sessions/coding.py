"""代码笔试（PLAN.md §5.3②）——出题 + 大模型检查判卷。

出题：岗位代码题方向 + 简历技术栈，场景化（不出 LeetCode 原题），难度递进 2 题；
判卷：先优点后不足的四维评审（正确性/边界/复杂度/风格）+ 参考答案三件套
（解题思路 + 参考代码 + 逐段解释），UI 明示「AI 评审」，不做在线运行判题。
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

CODING_REVIEW_PROMPT = """你是资深代码评审。请对候选人提交的代码做评审——**先肯定优点，再指不足**（哪怕代码很差也要找出可取之处，禁止一棒子打死），并给出带讲解的参考答案。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "strengths": ["优点1（引用候选人代码里的具体写法）", "优点2"],
  "weaknesses": ["不足1（指出具体逻辑/行，说清影响）", "不足2"],
  "correctness": {"score": 0-10, "comment": "正确性与解题思路评估"},
  "edge_cases": {"score": 0-10, "comment": "边界处理评估"},
  "complexity": {"score": 0-10, "comment": "时间/空间复杂度评估"},
  "style": {"score": 0-10, "comment": "代码风格与可读性评估"},
  "summary": "一句话总评（50字内，客观中性）",
  "solution": {
    "approach": "解题思路讲解：为什么这么做、用什么数据结构/算法、复杂度分析、有哪些变体或取舍",
    "code": "正确可运行的参考实现（带关键注释）",
    "explanation": "逐段代码解释：每个关键步骤为什么这么写、对应题目要求的哪一点"
  }
}

题目：{stem}
函数签名：{signature}
示例与约束：{examples_constraints}
候选人代码（语言 {language}）：
{code}

评分要求：每维 score 是 0-10 整数，严格但公平；strengths 至少 1 条、weaknesses 指出问题要具体；solution.approach 和 solution.explanation 要写成教学讲解（读者能学明白这题怎么做）；JSON 严格合法。
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
    """AI 评审：优缺点 + 四维分项 + 解题思路/参考代码/逐段解释。返回 (折算分, judge_json)。"""
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
    for key in ("strengths", "weaknesses"):
        items = data.get(key)
        judge[key] = [str(x)[:300] for x in items][:5] if isinstance(items, list) else []
    judge["summary"] = str(data.get("summary", ""))[:120]
    solution = data.get("solution")
    if not isinstance(solution, dict):
        solution = {}
    judge["solution"] = {
        "approach": str(solution.get("approach", ""))[:1500],
        "code": str(solution.get("code", ""))[:4000],
        "explanation": str(solution.get("explanation", ""))[:2000],
    }
    return judge
