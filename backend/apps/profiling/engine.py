"""Deterministic portrait & recommendation engine (PLAN.md §5.2).

No LLM: results must be reproducible and every score traceable to evidence
("准" via 样本集回归测试, see tests.py). LLM is used elsewhere (extraction /
interviews) with the site default model.

Pipeline: structured resume -> normalize skills -> tag projects -> experience
level -> direction scores -> per-job scoring with matched/gaps/reasons.
"""
import re

from .taxonomy import DEFAULT_LEVEL_SCORE, LEVEL_SCORES, SYNONYMS, TAG_KEYWORDS

# ---------------------------------------------------------------------------
# skill normalization
# ---------------------------------------------------------------------------

def _tokenize_skill_text(*texts: str) -> list[str]:
    """Split skill name/desc fields into lowercase tokens."""
    tokens: list[str] = []
    for text in texts:
        for part in re.split(r"[、，,;；/|（）()【】\[\]\s]+", (text or "").lower()):
            part = part.strip(" .·+")
            # "react.js" / "vue.js" / "python3" style forms -> base token
            part = re.sub(r"\.(js|py|ts|net)$", "", part)
            part = re.sub(r"\d+$", "", part) if part not in ("c++", "3d") else part
            if len(part) >= 2:
                tokens.append(part)
    return tokens


def _match_canonical(token: str) -> str | None:
    # pass 1: exact match (canonical name or alias) — always wins
    for canonical, aliases in SYNONYMS.items():
        if token == canonical or token in aliases:
            return canonical
    # pass 2: substring match, only for longer aliases/tokens ("py"/"js" style
    # short aliases must NOT swallow "pytorch"/"react.js")
    for canonical, aliases in SYNONYMS.items():
        for alias in aliases:
            if len(alias) >= 3 and len(token) >= 3 and (alias in token or token in alias):
                return canonical
    return None


def normalize_skills(skills: list[dict]) -> dict[str, float]:
    """[{name, level, desc}] -> {canonical_skill: level_score 0..3}."""
    result: dict[str, float] = {}
    for item in skills:
        level_score = LEVEL_SCORES.get((item.get("level") or "").strip(), DEFAULT_LEVEL_SCORE)
        tokens = _tokenize_skill_text(item.get("name"), item.get("desc"))
        for token in tokens:
            canonical = _match_canonical(token)
            if canonical:
                result[canonical] = max(result.get(canonical, 0.0), level_score)
    return result


# ---------------------------------------------------------------------------
# project tagging
# ---------------------------------------------------------------------------

def tag_projects(projects: list[dict], work: list[dict]) -> list[str]:
    """Match TAG_KEYWORDS against project/work names + bullets + tech_stack."""
    corpus_parts: list[str] = []
    for group in (projects, work):
        for item in group:
            for key in ("name", "company", "role"):
                corpus_parts.append(item.get(key) or "")
            corpus_parts.extend(item.get("bullets") or [])
            corpus_parts.extend(item.get("tech_stack") or [])
            corpus_parts.extend(item.get("metrics") or [])
    corpus = " ".join(corpus_parts).lower()

    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw.lower() in corpus for kw in keywords):
            tags.append(tag)
    return tags


# ---------------------------------------------------------------------------
# experience level
# ---------------------------------------------------------------------------

def experience_level(basics: dict) -> str:
    years_exp = (basics.get("years_exp") or "").strip()
    match = re.search(r"(\d+)\s*年", years_exp)
    if "应届" in years_exp or "实习" in years_exp or "在校" in years_exp:
        return "校招"
    if match:
        return "社招" if int(match.group(1)) >= 1 else "校招"
    return "校招" if not years_exp else "社招"


# ---------------------------------------------------------------------------
# portrait
# ---------------------------------------------------------------------------

def compute_portrait(structured: dict) -> dict:
    skills = normalize_skills(structured.get("skills") or [])
    tags = tag_projects(structured.get("projects") or [],
                        structured.get("work_experiences") or [])
    level = experience_level(structured.get("basics") or {})

    # direction scores: best matching jobs per category (computed lazily by caller
    # via score_jobs to avoid circular data); here we only derive raw signals.
    return {
        "skill_vector": skills,
        "project_tags": tags,
        "experience_level": level,
        "strengths": sorted(skills, key=lambda s: -skills[s])[:5],
        "skill_count": len(skills),
        "tag_count": len(tags),
    }


# ---------------------------------------------------------------------------
# job scoring
# ---------------------------------------------------------------------------

def _skill_match_score(skill_reqs: list[dict], skill_vector: dict[str, float]) -> tuple[float, list, list]:
    """Weighted skill score in 0..1 + matched/gap evidence lists."""
    if not skill_reqs:
        return 0.5, [], []
    total_weight = 0.0
    earned = 0.0
    matched, gaps = [], []
    for req in skill_reqs:
        name, weight = req["skill"], float(req.get("weight", 3))
        total_weight += weight
        if name in skill_vector:
            ratio = min(skill_vector[name] / 3.0, 1.0)
            earned += weight * (0.6 + 0.4 * ratio)  # presence dominates, level refines
            matched.append({"skill": name, "weight": weight,
                            "level": round(skill_vector[name], 1)})
        elif req.get("required"):
            gaps.append({"skill": name, "weight": weight, "required": True})
        else:
            gaps.append({"skill": name, "weight": weight, "required": False})
    return earned / total_weight if total_weight else 0.5, matched, gaps


def _tag_score(tags: list[str], affinity: list[str]) -> tuple[float, list]:
    if not affinity:
        return 0.5, []
    hit = [t for t in affinity if t in tags]
    return min(len(hit) / max(len(affinity) * 0.5, 1), 1.0), hit


def _exp_score(job_level: str, portrait_level: str) -> float:
    if job_level == portrait_level:
        return 1.0
    adjacent = {("实习", "校招"), ("校招", "实习"), ("校招", "社招"), ("社招", "校招")}
    return 0.7 if (job_level, portrait_level) in adjacent else 0.4


def score_job(job, portrait: dict) -> dict:
    skill_score, matched, gaps = _skill_match_score(
        job.skill_requirements, portrait["skill_vector"])
    tag_score, tag_hits = _tag_score(portrait["project_tags"], job.affinity_tags)
    exp = _exp_score(job.level, portrait["experience_level"])

    required_missing = [g for g in gaps if g["required"]]
    penalty = 0.12 * len(required_missing)

    total = 0.55 * skill_score + 0.30 * tag_score + 0.15 * exp - penalty
    total = max(0.0, min(1.0, total))

    reasons = []
    if matched:
        top = sorted(matched, key=lambda m: -m["weight"])[:4]
        reasons.append("技能匹配：" + "、".join(m["skill"] for m in top))
    if tag_hits:
        reasons.append("项目方向契合：" + "、".join(tag_hits[:4]))
    if exp == 1.0:
        reasons.append(f"经验级别一致（{job.level}）")
    elif exp == 0.7:
        reasons.append(f"经验级别相邻（画像 {portrait['experience_level']} / 岗位 {job.level}）")

    return {
        "job": job,
        "score": round(total, 4),
        "matched_skills": matched,
        "gap_skills": gaps,
        "required_missing": [g["skill"] for g in required_missing],
        "reasons": reasons,
        "sub_scores": {"skill": round(skill_score, 3), "tag": round(tag_score, 3),
                       "experience": exp},
    }


def recommend(jobs, portrait: dict, top_n: int = 8) -> list[dict]:
    scored = [score_job(job, portrait) for job in jobs]
    scored.sort(key=lambda r: -r["score"])
    return scored[:top_n]


def direction_scores(jobs, portrait: dict) -> dict[str, float]:
    """Average best-score per category -> 0..100 display score."""
    by_cat: dict[str, list[float]] = {}
    for job in jobs:
        by_cat.setdefault(job.category, []).append(score_job(job, portrait)["score"])
    return {cat: round(max(scores) * 100) for cat, scores in sorted(by_cat.items())}
