"""Django settings for Sparr backend.

All deployment-sensitive values come from environment variables (see PLAN.md §11.0).
Use .env in development; see .env.example at repo root.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    TASK_MODE=(str, "celery"),      # celery | lite
    STORAGE=(str, "local"),         # local | s3 | db
    DJANGO_SECURE_SSL_REDIRECT=(bool, False),
)
environ.Env.read_env(BASE_DIR.parent / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-secret-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    # Sparr apps
    "apps.accounts",
    "apps.resumes",
    "apps.profiling",
    "apps.jobs",
    "apps.sessions",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database — DATABASE_URL, e.g. postgres://user:pass@host:5432/db or sqlite:///db.sqlite3
# ---------------------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Auth / i18n / static
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "core.validators.SparrPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Media / resume file storage (PLAN.md §11.0: local | s3 | db)
MEDIA_URL = "media/"
MEDIA_ROOT = env.path("MEDIA_ROOT", default=BASE_DIR / "media")
STORAGE_BACKEND = env("STORAGE")

# ---------------------------------------------------------------------------
# DRF / JWT / CORS
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=6),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
}

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)

# ---------------------------------------------------------------------------
# Sparr specifics
# ---------------------------------------------------------------------------
# Background tasks: celery (worker needed) | lite (in-process thread pool, free-cloud mode)
TASK_MODE = env("TASK_MODE")

# Redis (only used when TASK_MODE=celery)
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_TRACK_STARTED = True

# Fernet key for encrypting user API keys (FERNET_KEY, or derived from SECRET_KEY in dev)
FERNET_KEY = env("FERNET_KEY", default="")

# LLM providers registry: OpenAI-compatible chat completions (PLAN.md §2)
LLM_PROVIDERS = {
    "deepseek": {
        "base_url": env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com/v1"),
        "models": env.list("DEEPSEEK_MODELS", default=["deepseek-chat", "deepseek-reasoner"]),
        "default_model": env("DEEPSEEK_DEFAULT_MODEL", default="deepseek-chat"),
    },
    "mimo": {
        "base_url": env("MIMO_BASE_URL", default="https://api.xiaomimimo.com/v1"),
        "models": env.list("MIMO_MODELS", default=["mimo-2.5", "mimo-2.6"]),
        "default_model": env("MIMO_DEFAULT_MODEL", default="mimo-2.6"),
    },
}
LLM_REQUEST_TIMEOUT = env.int("LLM_REQUEST_TIMEOUT", default=120)

# MinerU open API for resume PDF parsing
MINERU_BASE_URL = env("MINERU_BASE_URL", default="https://mineru.net/api/v4")

# Security hardening in production (behind HTTPS)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env("DJANGO_SECURE_SSL_REDIRECT")
