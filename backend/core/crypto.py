"""Fernet encryption for user-supplied API keys.

Keys are encrypted at rest and NEVER returned in plaintext to clients
(PLAN.md §5.1). The Fernet key comes from FERNET_KEY env, or is derived
from SECRET_KEY in development.
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if settings.FERNET_KEY:
            key = settings.FERNET_KEY.encode()
        else:
            digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
            key = base64.urlsafe_b64encode(digest)
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def mask(plaintext: str) -> str:
    """Display mask for a secret, e.g. sk-****ab12 — the only form clients see."""
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:3]}****{plaintext[-4:]}"
