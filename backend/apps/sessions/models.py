"""模拟应聘会话域（PLAN.md §5.3③，核心聚合根）。

ApplicationSession = 一场模拟应聘；Phase 3 先落面试问答（InterviewPlan +
InterviewTurn），Phase 4 再挂笔试/代码题，Phase 5 挂 FinalReport。
"""
from django.conf import settings
from django.db import models


class ApplicationSession(models.Model):
    """一场模拟应聘（核心聚合根）——三段式各阶段共享的会话与断点状态。"""

    class Status(models.TextChoices):
        CREATED = "created", "created"
        IN_PROGRESS = "in_progress", "in_progress"
        FINISHED = "finished", "finished"

    class Stage(models.TextChoices):
        QUIZ = "quiz", "quiz"
        CODING = "coding", "coding"
        INTERVIEW = "interview", "interview"
        SUMMARY = "summary", "summary"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="application_sessions")
    job = models.ForeignKey("jobs.JobPosition", null=True, blank=True,
                            on_delete=models.CASCADE, related_name="application_sessions")
    job_profile = models.ForeignKey("jobs.JobProfile", null=True, blank=True,
                                    on_delete=models.CASCADE,
                                    related_name="application_sessions")
    resume_version = models.ForeignKey("resumes.ResumeVersion",
                                       on_delete=models.CASCADE,
                                       related_name="application_sessions")

    provider = models.CharField(max_length=64, blank=True, default="")
    model_name = models.CharField(max_length=100, blank=True, default="")

    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.CREATED)
    # Phase 3 only ships the interview stage; quiz/coding arrive in Phase 4.
    current_stage = models.CharField(max_length=20, choices=Stage.choices,
                                     default=Stage.INTERVIEW)
    settings_json = models.JSONField(default=dict,
                                     help_text='{"strict_mode": false, "duration_min": 30}')

    # 断点续面状态（§5.3③-B 状态层）——每轮由状态机更新
    interview_state_json = models.JSONField(
        default=dict,
        help_text='{"phase", "time_used_min", "asked_question_ids", "evals_digest", '
                  '"dangling_threads", "found_flaws", "found_highlights", "plan_adjustments"}')
    # 滚动摘要（每 K 轮压缩早期对话）
    context_summary = models.TextField(blank=True, default="")
    context_summary_turn_seq = models.IntegerField(default=0)
    last_turn_seq = models.IntegerField(default=0)

    # 面试后复盘（§5.3③ 面试后：维度评估 + 逐题复盘；Phase 5 汇入 FinalReport）
    review_json = models.JSONField(null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        target = self.job.title if self.job_id else (
            self.job_profile.title if self.job_profile_id else "?")
        return f"面试@{target}#{self.id}"

    @property
    def job_title(self) -> str:
        if self.job_id:
            return f"{self.job.title}（{self.job.level}）"
        if self.job_profile_id:
            return self.job_profile.title
        return ""


class InterviewPlan(models.Model):
    """面试计划（环节 + 题池 + 追问树 + 弹药卡 briefing）。

    plan_json = {"briefing": {...InterviewBriefing...}, "phases": [...]}
    每道题必须带 `why` 证据（因人出题，§5.3③-A 机制 1），校验时无 why 的题直接丢弃。
    """

    application = models.OneToOneField(ApplicationSession, on_delete=models.CASCADE,
                                       related_name="plan")
    plan_json = models.JSONField(default=dict)
    model_name = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"面试计划#{self.application_id}"


class InterviewTurn(models.Model):
    """面试对话轮次——逐轮落库，断点续面的事实来源。"""

    class Role(models.TextChoices):
        INTERVIEWER = "interviewer", "interviewer"
        CANDIDATE = "candidate", "candidate"
        SYSTEM = "system", "system"

    application = models.ForeignKey(ApplicationSession, on_delete=models.CASCADE,
                                    related_name="turns")
    seq = models.PositiveIntegerField()
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    # 面试官隐藏评估（对候选人上一回答的 eval_json，§5.3③-A 机制 2）
    eval_json = models.JSONField(null=True, blank=True)
    meta = models.JSONField(default=dict,
                            help_text='{"phase", "question_id", "depth", "interrupted", '
                                      '"partial", "plan_adjustment"}')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seq"]
        unique_together = [("application", "seq")]

    def __str__(self) -> str:
        return f"turn#{self.seq}({self.role})"


class ExamQuestion(models.Model):
    """基础笔试题（PLAN.md §5.3①）——单选/多选/简答，同一岗位定义驱动出题。

    参考答案与评分要点只留在服务端，试卷 API 不下发（防作弊）。
    """

    class QType(models.TextChoices):
        SINGLE = "single", "single"
        MULTI = "multi", "multi"
        SHORT = "short_answer", "short_answer"

    application = models.ForeignKey(ApplicationSession, on_delete=models.CASCADE,
                                    related_name="exam_questions")
    seq = models.PositiveIntegerField()
    qtype = models.CharField(max_length=16, choices=QType.choices)
    difficulty = models.PositiveSmallIntegerField(default=3)
    stem = models.TextField()
    options = models.JSONField(default=list)          # ["A文本", ...]
    reference_answer = models.JSONField(default=list) # 选择题: 选项序号数组; 简答: ["参考表述"]
    scoring_points = models.JSONField(default=list)   # 简答评分要点
    knowledge_tag = models.CharField(max_length=100, blank=True, default="")
    score_full = models.PositiveSmallIntegerField(default=10)

    class Meta:
        ordering = ["seq"]
        unique_together = [("application", "seq")]


class ExamAnswer(models.Model):
    """笔试作答与判卷结果。content: 选择题=选项序号数组；简答=文本。"""

    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE,
                                 related_name="answers")
    content = models.JSONField(default=dict)
    score = models.FloatField(default=0)
    judge_json = models.JSONField(default=dict)  # {"reason": ...}
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["question__seq"]
