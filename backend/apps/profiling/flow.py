"""Main-line journey state machine (user UX redesign).

四步主线：简历 → 画像与岗位 → 模拟应聘 → 总结提升。
宽松跳转：状态只驱动引导提示，不限制访问任何页面。
完成判定（动作完成制）：简历=解析出版本；画像=做过评估；
应聘=完成一场三段模拟应聘；总结=看过总结报告（后两步的模型在 Phase 3/5 接入，
此处以存在性探测动态接线）。
"""
from apps.jobs.models import MatchAnalysis
from apps.resumes.models import Resume


def _try_done(app_label: str, model_name: str, user) -> bool:
    """Future-proof existence probe for models not yet built (Phase 3/5)."""
    from django.apps import apps

    try:
        model = apps.get_model(app_label, model_name)
    except LookupError:
        return False
    return model.objects.filter(user=user).exists()


def flow_state(user) -> dict:
    latest_resume = (Resume.objects.filter(user=user)
                     .order_by("-updated_at").first())
    has_parsed = bool(latest_resume and latest_resume.current_version)
    has_analysis = MatchAnalysis.objects.filter(user=user).exists()

    # Phase 3/5 models — probed dynamically once they exist
    has_interview = _try_done("sparr_sessions", "ApplicationSession", user)
    has_report = _try_done("reports", "FinalReport", user)

    def step(key, label, url, action, desc, done, ready):
        status = "done" if done else ("active" if ready else "todo")
        return {"key": key, "label": label, "url": url, "action": action,
                "desc": desc, "status": status}

    steps = [
        step("resume", "简历", "/resumes",
             "上传简历或手动填写", "解析并整理你的项目与能力",
             done=has_parsed,
             ready=True),
        step("profile", "画像与岗位", "/profiling",
             "生成画像与岗位匹配", "看看你适合哪些岗位、差距在哪",
             done=has_analysis,
             ready=has_parsed),
        step("interview", "模拟应聘", "/applications",
             "开始模拟应聘", "笔试 · 代码 · 智能面试问答",
             done=has_interview,
             ready=has_parsed),
        step("summary", "总结提升", "/applications",
             "查看总结报告", "综合评估 + 简历优化，形成成长闭环",
             done=has_report,
             ready=has_interview),
    ]

    next_step = next((s for s in steps if s["status"] != "done"), None)
    current_step = next((s for s in steps if s["status"] == "active"), None)

    meta = {}
    if latest_resume:
        meta["resume_title"] = latest_resume.title
        meta["resume_status"] = latest_resume.parse_status

    return {"steps": steps, "next": next_step, "current": current_step, "meta": meta}
