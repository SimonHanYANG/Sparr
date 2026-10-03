"""Portrait & recommendation persistence (PLAN.md §4) — computed deterministically."""
from django.conf import settings
from django.db import models


class UserPortrait(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="portraits")
    resume_version = models.ForeignKey("resumes.ResumeVersion", on_delete=models.CASCADE,
                                       related_name="portraits")
    profile_json = models.JSONField()
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-computed_at"]
        unique_together = [("user", "resume_version")]

    def __str__(self) -> str:
        return f"portrait(user {self.user_id}, v{self.resume_version_id})"


class JobRecommendation(models.Model):
    portrait = models.ForeignKey(UserPortrait, on_delete=models.CASCADE,
                                 related_name="recommendations")
    job = models.ForeignKey("jobs.JobPosition", on_delete=models.CASCADE)
    score = models.FloatField()
    matched_skills = models.JSONField(default=list)
    gap_skills = models.JSONField(default=list)
    reasons = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]
