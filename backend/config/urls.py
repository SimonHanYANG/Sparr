"""Root URL configuration — API under /api/, health check at /api/healthz/."""
from django.contrib import admin
from django.urls import include, path

from core.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/healthz", healthz, name="healthz"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.resumes.urls")),
    path("api/", include("apps.jobs.urls")),
    path("api/", include("apps.profiling.urls")),
    path("api/", include("apps.sessions.urls")),
]
