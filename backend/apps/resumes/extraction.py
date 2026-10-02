"""LLM structured extraction: MinerU markdown -> ResumeVersion.structured_json.

Strict schema + parse retry (PLAN.md §5.1). The schema is the contract for
every downstream feature (画像/推荐、面试弹药卡、简历优化).
"""
import json
import re

from core.llm_adapter import ChatMessage, LLMClient, LLMError

SCHEMA_PROMPT = """你是一个简历结构化抽取引擎。从用户给的简历 Markdown 中抽取信息，\
只输出一个 JSON 对象（不要任何解释、不要 markdown 代码块），结构必须是：

{
  "basics": {
    "name": "姓名",
    "intent_role": "意向岗位，如 后端开发工程师",
    "contact": "邮箱/电话等联系方式字符串",
    "years_exp": "经验年限描述，如 3 年 / 应届"
  },
  "education": [
    {"school": "学校", "degree": "学位", "major": "专业", "period": "时间段", "desc": "补充描述"}
  ],
  "skills": [{"name": "技能名", "level": "熟悉程度，如 熟练/了解/精通"}],
  "projects": [
    {
      "name": "项目名",
      "role": "担任角色",
      "period": "时间段",
      "tech_stack": ["技术1", "技术2"],
      "bullets": ["项目描述要点（尽量保留原文措辞）"],
      "metrics": ["可量化的成果指标"]
    }
  ],
  "work_experiences": [
    {"company": "公司", "role": "职位", "period": "时间段", "bullets": ["工作要点"]}
  ],
  "awards": ["奖项/证书"]
}

要求：
1. 忠实原文，不要编造；简历里没有的字段用空字符串或空数组；
2. bullets 尽量保留简历原文语句（可轻微精简）；
3. 时间段统一为 "YYYY.MM - YYYY.MM" 或 "YYYY.MM - 至今" 风格；
4. 输出必须是合法 JSON；
5. skills 必须完整抽取（编程语言/框架/工具/软技能等，宁多勿漏），除非原文确实没有技能信息，否则不得为空数组；
6. projects 和 work_experiences 的 bullets 同理：正文提到的要点都要抽出来。"""


def extract_structured(markdown: str, client: LLMClient, max_retries: int = 2) -> dict:
    """Markdown -> structured dict. Retries on JSON parse/validation failure."""
    messages = [
        ChatMessage(role="system", content=SCHEMA_PROMPT),
        ChatMessage(role="user", content=f"简历 Markdown 如下：\n\n{markdown[:20000]}"),
    ]
    last_err = None
    for _ in range(max_retries + 1):
        try:
            raw = client.chat(messages, temperature=0.1)
            data = _parse_json(raw)
            _validate(data)
            return data
        except (LLMError, ValueError, KeyError) as exc:
            last_err = exc
    raise ValueError(f"简历结构化抽取失败：{last_err}")


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    # strip ```json fences if the model added them anyway
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in LLM output")
    return json.loads(text[start : end + 1])


def _validate(data: dict) -> None:
    """Light structural check — every key must exist with the right type."""
    required = {
        "basics": dict, "education": list, "skills": list,
        "projects": list, "work_experiences": list, "awards": list,
    }
    for key, typ in required.items():
        if key not in data or not isinstance(data[key], typ):
            raise ValueError(f"missing or wrong-typed field: {key}")
    if "name" not in data["basics"]:
        raise ValueError("basics.name missing")
