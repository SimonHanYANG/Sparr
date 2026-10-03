"""LLM-powered match analysis (PLAN.md §5.2, revised per user feedback).

规则引擎只负责快速信号（方向倾向）；**评分、匹配点、待补强由大模型评估**
（站点默认 mimo-v2.6-flash），且每条 gap 必须锚定 JD 原文要求——这是"准"的来源。
支持任意粘贴的 JD，不再局限于预置岗位库。
"""
import json
import re

from core.llm_adapter import ChatMessage, LLMClient, LLMError

ANALYZE_PROMPT = """你是资深招聘专家。请严格评估「候选人简历」与「目标岗位 JD」的匹配度。

只输出一个 JSON 对象（不要解释、不要代码块）：
{
  "score": 0到100的整数,
  "summary": "一句话结论（30字内）",
  "matched": [
    {"requirement": "JD 中的一条要求（贴近原文）", "evidence": "简历中支撑该要求的具体证据"}
  ],
  "gaps": [
    {"requirement": "JD 中的一条要求（贴近原文）", "status": "未体现 或 部分体现", "advice": "针对这条缺口的具体补强建议"}
  ],
  "advice": ["给候选人的整体建议（改简历/补能力/面试准备），2-4条"]
}

评分标准（严格执行，保证分数可信）：
- 90-100：核心要求几乎全部满足且证据扎实，可直接面试
- 75-89：核心要求大部分满足，有少量可补强缺口
- 60-74：满足主要要求，但有明显缺口需要补
- 40-59：仅满足部分要求，缺口较多
- 0-39：方向或经验明显不匹配
打分必须基于证据，不得讨好；gaps 必须逐条引用 JD 的要求条目，不得泛泛列技能名；
简历中没有的信息不得编造。matched 与 gaps 覆盖 JD 的所有核心要求（必读要求逐条判断）。

候选人简历：
{resume}

目标岗位（{job_title}）JD：
{jd}
"""

def _parse_json(raw: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[start:end + 1])


def _resume_text(structured: dict) -> str:
    return json.dumps(structured, ensure_ascii=False)[:12000]


def _validate_eval(data: dict) -> dict:
    if not isinstance(data.get("score"), (int, float)):
        raise ValueError("missing score")
    data["score"] = max(0, min(100, float(data["score"])))
    data.setdefault("summary", "")
    for key in ("matched", "gaps", "advice"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data


def analyze_match(llm: LLMClient, structured_resume: dict, *, job_title: str,
                  jd_text: str, max_retries: int = 2) -> dict:
    """One position (custom JD or preset) vs one resume version -> eval dict."""
    messages = [
        ChatMessage(role="system", content="你是严谨的招聘评估引擎，只输出合法 JSON。"),
        ChatMessage(role="user", content=ANALYZE_PROMPT
                    .replace("{resume}", _resume_text(structured_resume))
                    .replace("{job_title}", job_title)
                    .replace("{jd}", jd_text[:8000])),
    ]
    last_err = None
    for _ in range(max_retries + 1):
        try:
            data = _validate_eval(_parse_json(llm.chat(messages, temperature=0.2)))
            return data
        except (LLMError, ValueError, KeyError) as exc:
            last_err = exc
    raise ValueError(f"岗位匹配分析失败：{last_err}")


def analyze_catalog(llm: LLMClient, structured_resume: dict, jobs: list, on_result=None) -> list[dict]:
    """Evaluate catalog jobs one-by-one in PARALLEL (one giant batch call took
    minutes; per-job calls with a thread pool are much faster overall and let
    callers stream results as they finish).

    Returns [{job_id, score, ...}] sorted by score desc. on_result callback
    (optional) fires per completed job for streaming.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: list[dict] = []

    def _one(job):
        ev = analyze_match(llm, structured_resume,
                           job_title=f"{job.title}（{job.level}）",
                           jd_text=_job_to_jd(job))
        ev["job_id"] = job.id
        return ev

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_one, j): j for j in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                ev = fut.result()
            except Exception:  # noqa: BLE001 — one bad job shouldn't kill the batch
                continue
            results.append(ev)
            if on_result:
                on_result(ev)
    results.sort(key=lambda e: -e["score"])
    return results


def _job_to_jd(job) -> str:
    return (f"{job.description}\n岗位要求："
            + "；".join(f"{r['skill']}({'必会' if r.get('required') else '加分'})"
                       for r in job.skill_requirements)
            + f"\n面试重点：{'、'.join(job.interview_focus)}")
