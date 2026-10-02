"""Celery application. Only used when TASK_MODE=celery (see core.tasks)."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("sparr")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
