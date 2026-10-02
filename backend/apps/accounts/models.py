"""User-facing account models.

ProviderCredential stores user-supplied API keys (DeepSeek / MiMo / MinerU)
Fernet-encrypted at rest; plaintext is write-only and never read back
(PLAN.md §5.1).
"""
from django.conf import settings
from django.db import models

from core.crypto import encrypt, mask


class ProviderCredential(models.Model):
    class Provider(models.TextChoices):
        DEEPSEEK = "deepseek", "DeepSeek"
        MIMO = "mimo", "Xiaomi MiMo"
        MINERU = "mineru", "MinerU"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="credentials")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    api_key_encrypted = models.TextField()
    model_name = models.CharField(max_length=100, blank=True, default="")
    base_url = models.URLField(blank=True, default="",
                               help_text="Optional base_url override for self-hosted gateways")
    is_valid = models.BooleanField(null=True, blank=True,
                                   help_text="Last validation result; null = never validated")
    last_validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "provider")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.provider}"

    @property
    def api_key_masked(self) -> str:
        """Display form for clients — the plaintext never leaves the server."""
        from core.crypto import decrypt

        try:
            return mask(decrypt(self.api_key_encrypted))
        except Exception:  # noqa: BLE001 — corrupted key shows as unknown
            return "****"

    def set_api_key(self, plaintext: str) -> None:
        self.api_key_encrypted = encrypt(plaintext)

    def reveal_api_key(self) -> str:
        """Server-side only: plaintext for outbound LLM/MinerU calls."""
        from core.crypto import decrypt

        return decrypt(self.api_key_encrypted)
