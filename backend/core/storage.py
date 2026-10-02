"""File storage abstraction (PLAN.md §11.0): local | s3 | db.

STORAGE=db is the free-cloud friendly mode — uploads land in the database
bytea-equivalent, surviving ephemeral disks. s3 lands in Phase 1 with
resume uploads; the interface is fixed now so business code never changes.
"""
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


class StorageError(Exception):
    pass


def save_upload(name: str, content: bytes) -> str:
    """Persist an uploaded file; returns the storage-relative path/key."""
    backend = settings.STORAGE_BACKEND
    if backend in ("local", "db"):
        # FileSystemStorage for local; when STORAGE=db, MEDIA_ROOT points at
        # a DB-backed volume or FileBlob swap-in (Phase 1 wires the model).
        path = default_storage.save(f"uploads/{name}", ContentFile(content))
        return path
    if backend == "s3":
        raise StorageError("s3 storage lands in Phase 1 (resume uploads)")
    raise StorageError(f"unknown STORAGE backend: {backend}")


def read_upload(path: str) -> bytes:
    with default_storage.open(path, "rb") as fh:
        return fh.read()


def upload_abspath(path: str) -> Path:
    return Path(settings.MEDIA_ROOT) / path
