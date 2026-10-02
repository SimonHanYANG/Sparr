"""Gunicorn config — threaded workers so SSE streams stay concurrent (PLAN.md §11.0)."""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
# SSE connections are long-lived; keep worker timeout generous and buffering off at the proxy.
