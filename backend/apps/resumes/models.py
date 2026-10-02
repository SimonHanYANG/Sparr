"""Resume storage: original PDF + MinerU markdown + structured versions (PLAN.md §5.1)."""
from django.conf import settings
from django.db import models


class Resume(models.Model):
    class ParseStatus(models.TextChoices):
        UPLOADED = "uploaded", "已上传"
        PARSING = "parsing", "解析中"
        PARSED = "parsed", "已解析"
        FAILED = "failed", "解析失败"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="resumes")
    title = models.CharField(max_length=200)
    source_path = models.CharField(max_length=500, help_text="storage key of the original PDF")
    source_filename = models.CharField(max_length=255)
    mineru_markdown = models.TextField(blank=True, default="")
    mineru_batch_id = models.CharField(max_length=100, blank=True, default="")
    parse_status = models.CharField(max_length=20, choices=ParseStatus.choices,
                                    default=ParseStatus.UPLOADED)
    parse_error = models.TextField(blank=True, default="")
    current_version = models.ForeignKey("ResumeVersion", null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.title} (user {self.user_id})"


class ResumeVersion(models.Model):
    """One editable snapshot of the structured resume; saving creates a new version."""

    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="versions")
    version_no = models.PositiveIntegerField()
    structured_json = models.JSONField()
    change_note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version_no"]
        unique_together = [("resume", "version_no")]

    def __str__(self) -> str:
        return f"{self.resume_id} v{self.version_no}"
