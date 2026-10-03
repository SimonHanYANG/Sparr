"""Job catalog — one shared definition drives 推荐 / 笔试出题 / 面试重点 (PLAN.md §5.2)."""
from django.conf import settings
from django.db import models


class JobPosition(models.Model):
    class Category(models.TextChoices):
        FRONTEND = "前端", "前端"
        BACKEND = "后端", "后端"
        ALGORITHM = "算法", "算法"
        PRODUCT = "产品", "产品"
        DATA = "数据", "数据"
        QA = "测试", "测试"
        INFRA = "运维", "运维"

    class Level(models.TextChoices):
        INTERN = "实习", "实习"
        CAMPUS = "校招", "校招"
        SOCIAL = "社招", "社招"

    category = models.CharField(max_length=10, choices=Category.choices)
    title = models.CharField(max_length=100)
    level = models.CharField(max_length=10, choices=Level.choices)
    description = models.TextField(blank=True, default="")

    # recommendation scoring (PLAN.md §5.2): weighted skill matrix
    skill_requirements = models.JSONField(
        default=list, help_text='[{"skill": "python", "weight": 5, "required": true}]')
    affinity_tags = models.JSONField(
        default=list, help_text="project-tag affinities, e.g. [高并发, 分布式]")

    # exam/interview blueprints — same JD vocabulary across features
    knowledge_points = models.JSONField(default=list)
    coding_topics = models.JSONField(default=list)
    interview_focus = models.JSONField(default=list)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "level"]
        unique_together = [("category", "title", "level")]

    def __str__(self) -> str:
        return f"{self.title}({self.level})"


class JobProfile(models.Model):
    """User-defined position from a pasted JD — any job, not just the catalog."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="job_profiles")
    title = models.CharField(max_length=200)
    jd_text = models.TextField()
    category = models.CharField(max_length=10, blank=True, default="")
    level = models.CharField(max_length=10, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class JobTarget(models.Model):
    """'My target jobs' — the user's shortlist, wired into the main line."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="job_targets")
    job = models.ForeignKey(JobPosition, null=True, blank=True,
                            on_delete=models.CASCADE, related_name="targets")
    job_profile = models.ForeignKey(JobProfile, null=True, blank=True,
                                    on_delete=models.CASCADE, related_name="targets")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class JobSelfCheck(models.Model):
    """Per-knowledge-point self assessment (掌握/模糊/不会).

    Stored per user+job and FEEDS the mock interviewer (Phase 3): points the
    candidate marks 模糊/不会 become prime interview targets.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="self_checks")
    job = models.ForeignKey(JobPosition, on_delete=models.CASCADE, related_name="self_checks")
    checks_json = models.JSONField(default=dict,
                                   help_text='{"知识点": "掌握|模糊|不会"}')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "job")]


class MatchAnalysis(models.Model):
    """LLM match evaluation of a resume version against one position.

    Score/gaps are grounded in the JD's own requirement clauses (user feedback:
    gaps must map to what the JD asks, not generic skill diffs).
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="match_analyses")
    resume_version = models.ForeignKey("resumes.ResumeVersion", on_delete=models.CASCADE,
                                       related_name="match_analyses")
    job = models.ForeignKey(JobPosition, null=True, blank=True,
                            on_delete=models.CASCADE, related_name="match_analyses")
    job_profile = models.ForeignKey(JobProfile, null=True, blank=True,
                                    on_delete=models.CASCADE, related_name="match_analyses")
    model_name = models.CharField(max_length=100, blank=True, default="")
    score = models.FloatField()
    summary = models.TextField(blank=True, default="")
    matched = models.JSONField(default=list)
    gaps = models.JSONField(default=list)
    advice = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
