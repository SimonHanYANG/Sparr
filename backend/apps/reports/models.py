"""综合总结报告域（PLAN.md §5.4 F4）——三段汇总 + 简历修改建议闭环。

FinalReport 聚合笔试/代码/面试三段数据与隐藏评估；ResumeEditSuggestion 为
diff 式修改建议（原句→建议句→理由），逐条 accept/reject，采纳生成新 ResumeVersion，
形成「面试 → 改简历 → 再面试」的成长闭环。
"""
from django.conf import settings
from django.db import models


class FinalReport(models.Model):
    """一场模拟应聘的综合报告（LLM 汇总三段 + 隐藏评估）。"""

    class Recommendation(models.TextChoices):
        STRONG = "强推", "强推"
        HIRE = "推荐", "推荐"
        MAYBE = "待定", "待定"
        NO = "不推荐", "不推荐"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="final_reports")  # flow.py 状态机探测用
    application = models.OneToOneField("sparr_sessions.ApplicationSession",
                                       on_delete=models.CASCADE,
                                       related_name="final_report")
    overall_score = models.FloatField(default=0)
    hire_recommendation = models.CharField(max_length=10,
                                           choices=Recommendation.choices,
                                           default=Recommendation.MAYBE)
    dimension_radar = models.JSONField(
        default=dict,
        help_text='{"基础知识": 0-100, "编码能力", "项目深度", "沟通表达", "岗位匹配"}')
    stage_scores = models.JSONField(default=dict)       # {"quiz": x, "coding": y, "interview": z}
    per_stage_summary = models.JSONField(default=list)  # [{"stage", "score", "summary"}]
    highlights = models.JSONField(default=list)
    weaknesses = models.JSONField(default=list)
    improvement_plan = models.JSONField(default=list)   # [{"area", "action"}]
    model_name = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"报告#{self.application_id}({self.overall_score})"


class ResumeEditSuggestion(models.Model):
    """diff 式简历修改建议：原句 → 建议句 → 理由；逐条采纳/忽略。"""

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        ACCEPTED = "accepted", "accepted"
        REJECTED = "rejected", "rejected"

    report = models.ForeignKey(FinalReport, on_delete=models.CASCADE,
                               related_name="suggestions")
    field_path = models.CharField(max_length=200, blank=True, default="",
                                  help_text="如 projects[0].metrics（展示定位用）")
    original_text = models.TextField()
    suggested_text = models.TextField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.PENDING)
    apply_note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
