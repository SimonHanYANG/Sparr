"""Job catalog — one shared definition drives 推荐 / 笔试出题 / 面试重点 (PLAN.md §5.2)."""
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
