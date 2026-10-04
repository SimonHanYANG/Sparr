"""基础笔试（PLAN.md §5.3①）——出题 + 判卷。

出题：岗位考点大纲 + 简历技能加权，难度分布 3:5:2，因人因岗定制；
判卷：客观题按选项集合确定性比对；简答题 LLM 按 scoring_points 给分 + 评语。
答错题的 knowledge_tag 汇入 quiz_weak，喂给面试官「恰好」追问（三段联动）。
"""
import json
import re

from core.llm_adapter import ChatMessage, LLMClient, LLMError, fast_completion_kwargs

from .interview import _parse_json

EXAM_PROMPT = """你是资深笔试出题人。请为报考「{job_title}」的候选人出一份基础笔试（共 {total} 题：单选 {n_single}、多选 {n_multi}、简答 {n_short}，每题 score_full 一律 10 分）。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "questions": [
    {
      "id": "q1",
      "type": "single",
      "difficulty": 1,
      "stem": "题干",
      "options": ["选项A文本", "选项B文本", "选项C文本", "选项D文本"],
      "reference_answer": [0],
      "scoring_points": [],
      "knowledge_tag": "考点（取自考点大纲）",
      "score_full": 10
    },
    {
      "id": "q7",
      "type": "short_answer",
      "difficulty": 3,
      "stem": "简答题干",
      "options": [],
      "reference_answer": ["参考答案要点表述"],
      "scoring_points": ["评分要点1", "评分要点2", "评分要点3"],
      "knowledge_tag": "考点",
      "score_full": 10
    }
  ]
}

硬性规则（违反即作废）：
1. 难度分布严格由简入深、3:5:2（difficulty 1-2 : 3 : 4-5）；题目按难度从易到难组织；score_full 一律 10；单选 reference_answer 恰好 1 个选项、多选恰好 2-3 个选项（不得只给 1 个）；reference_answer 对选择题是正确选项的序号数组（单选一个、多选两到三个，序号从 0 开始）；简答题是 ["参考表述"]；
2. 考点覆盖岗位考点大纲：{knowledge_points}；候选人简历里写到的技术点适当加权：{resume_skills}；
3. 题目因人因岗定制，选择题干扰项要可信、无明显凑数项；同一考点不出重复题；
4. 简答题 scoring_points 3-5 条，每条可独立判分；
5. JSON 严格合法（字符串值内禁英文双引号，引用用「」）；除 JSON 外不要输出任何多余文字。
"""

SHORT_JUDGE_PROMPT = """你是笔试阅卷人。请按评分要点为这道简答题打分。

只输出一个 JSON 对象（不要解释、不要代码块）：
{"score": 0到满分的数字, "reason": "评分说明（引用要点逐条对照，50字内）"}

题干：{stem}
评分要点（每条独立判分）：{scoring_points}
参考答案：{reference_answer}
满分：{score_full}
候选人作答：{answer}

评分要求：严格按要点给分，答到一条给一条的分；与要点矛盾或明显错误不给分；不讨好。
"""


def generate_quiz(llm: LLMClient, *, job_title: str, knowledge_points: list[str],
                  resume_skills: list[str], duration_min: int = 20,
                  max_retries: int = 1) -> list[dict]:
    """一份笔试卷目：validated question dicts（含参考答案，服务端持有）。"""
    prompt = (EXAM_PROMPT
              .replace("{total}", "20")
              .replace("{n_single}", "11")
              .replace("{n_multi}", "5")
              .replace("{n_short}", "4")
              .replace("{job_title}", job_title)
              .replace("{knowledge_points}", "、".join(knowledge_points[:12]) or "（通用）")
              .replace("{resume_skills}", "、".join(resume_skills[:15]) or "（无）"))
    messages = [
        ChatMessage(role="system", content="你是严谨的笔试出题引擎，只输出合法 JSON。"),
        ChatMessage(role="user", content=prompt),
    ]
    last_err = None
    for _ in range(max_retries + 1):
        try:
            data = _parse_json(llm.chat(messages, temperature=0.3, max_tokens=7000,
                                          **fast_completion_kwargs(llm)))
            return _validate_quiz(data)
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            last_err = exc
    raise ValueError(f"笔试出题失败：{last_err}")


def _validate_quiz(data: dict) -> list[dict]:
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("missing questions")
    kept = []
    seen = set()
    for q in questions:
        if not isinstance(q, dict) or not q.get("stem"):
            continue
        qtype = q.get("type")
        if qtype not in ("single", "multi", "short_answer"):
            continue
        try:
            difficulty = max(1, min(5, int(q.get("difficulty", 3))))
        except (TypeError, ValueError):
            difficulty = 3
        options = q.get("options") if isinstance(q.get("options"), list) else []
        ref = q.get("reference_answer")
        if not isinstance(ref, list):
            ref = [str(ref)] if ref is not None else []
        if qtype in ("single", "multi"):
            if len(options) < 2 or not ref:
                continue
            try:
                ref = sorted({int(i) for i in ref})
            except (TypeError, ValueError):
                continue
            if any(i < 0 or i >= len(options) for i in ref):
                continue
            # 智能救题：题型与答案个数不符时就地转换而不是丢弃
            if qtype == "single" and len(ref) > 1:
                qtype = "multi"
            if qtype == "multi" and len(ref) == 1:
                qtype = "single"
            if not ref:
                continue
            points = []
        else:
            if not ref:
                ref = ["（无参考答案）"]
            points = [str(p) for p in q.get("scoring_points", []) if str(p).strip()]
        try:
            score_full = max(1, min(30, int(q.get("score_full", 10))))
        except (TypeError, ValueError):
            score_full = 10
        qid = str(q.get("id") or f"q{len(kept) + 1}")
        if qid in seen:
            qid = f"{qid}_{len(kept) + 1}"
        seen.add(qid)
        kept.append({"id": qid, "type": qtype, "difficulty": difficulty,
                     "stem": str(q["stem"]), "options": [str(o) for o in options],
                     "reference_answer": ref, "scoring_points": points,
                     "knowledge_tag": str(q.get("knowledge_tag", ""))[:60],
                     "score_full": score_full})
    if len(kept) < 5:
        raise ValueError("valid questions < 5")
    # 由简入深：按难度升序组织（同难度先选择后简答），服务端排序不依赖模型自觉
    type_rank = {"single": 0, "multi": 1, "short_answer": 2}
    kept.sort(key=lambda q: (q["difficulty"], type_rank.get(q["type"], 9)))
    return kept


def grade_objective(question: dict, given) -> tuple[float, dict]:
    """客观题：选项序号集合确定性比对。"""
    try:
        given_set = sorted({int(i) for i in (given or [])})
    except (TypeError, ValueError):
        return 0.0, {"reason": "作答格式无效", "correct": False}
    ref_set = sorted(int(i) for i in question["reference_answer"])
    if given_set == ref_set:
        return float(question["score_full"]), {"reason": "回答正确", "correct": True}
    if question["type"] == "multi" and set(given_set) < set(ref_set) and given_set:
        half = question["score_full"] * 0.5
        return half, {"reason": "部分正确（漏选）", "correct": False}
    return 0.0, {"reason": "回答错误", "correct": False}


def grade_short(llm: LLMClient, question: dict, answer: str) -> tuple[float, dict]:
    """简答题：LLM 按评分要点给分 + 评语。"""
    prompt = (SHORT_JUDGE_PROMPT
              .replace("{stem}", question["stem"][:500])
              .replace("{scoring_points}", "；".join(question["scoring_points"]) or "（无）")
              .replace("{reference_answer}", str(question["reference_answer"][0])[:500])
              .replace("{score_full}", str(question["score_full"]))
              .replace("{answer}", str(answer or "")[:2000]))
    messages = [ChatMessage(role="user", content=prompt)]
    last_err = None
    for _ in range(2):
        try:
            data = _parse_json(llm.chat(messages, temperature=0.1, max_tokens=1500,
                                          **fast_completion_kwargs(llm)))
            score = max(0.0, min(float(question["score_full"]), float(data.get("score", 0))))
            return score, {"reason": str(data.get("reason", ""))[:300]}
        except (LLMError, ValueError, KeyError, TypeError) as exc:
            last_err = exc
    return 0.0, {"reason": f"判卷失败：{last_err}"}
