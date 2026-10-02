"""Background task dispatch with switchable backend (PLAN.md §11.0).

TASK_MODE=celery : real queue via Celery worker (local / full deployment)
TASK_MODE=lite   : in-process daemon thread (free-cloud deployment, no Redis)

Business code only calls dispatch("task_name", *args, **kwargs) — never
touches Celery or threads directly.
"""
import logging
import threading

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)

_registry: dict[str, callable] = {}


def background(fn):
    """Register fn as a background task callable via dispatch(fn.__name__, ...)."""
    @shared_task(bind=True, name=f"sparr.{fn.__name__}", max_retries=3)
    def _celery_task(self, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — retry then raise
            logger.exception("background task %s failed", fn.__name__)
            raise self.retry(exc=exc, countdown=10) from exc

    _registry[fn.__name__] = (fn, _celery_task)
    return fn


def dispatch(name: str, *args, **kwargs) -> None:
    """Run a registered background task per TASK_MODE."""
    if name not in _registry:
        raise KeyError(f"unknown background task: {name}")
    fn, celery_task = _registry[name]

    if settings.TASK_MODE == "celery" and not settings.CELERY_TASK_ALWAYS_EAGER:
        celery_task.delay(*args, **kwargs)
    else:
        # lite / eager: run in a daemon thread (or inline when eager)
        if settings.CELERY_TASK_ALWAYS_EAGER:
            fn(*args, **kwargs)
        else:
            threading.Thread(target=_safe_run, args=(fn, args, kwargs), daemon=True).start()


def _safe_run(fn, args, kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("lite background task %s failed", fn.__name__)
