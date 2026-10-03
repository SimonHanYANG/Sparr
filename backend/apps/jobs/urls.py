from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    analyses_list,
    job_self_check,
    job_target,
    job_targets,
    JobProfileViewSet,
    analyze,
    analyze_catalog_stream,
    analyze_catalog_view,
    job_list,
)

router = DefaultRouter(trailing_slash=False)
router.register("jobs/profiles", JobProfileViewSet, basename="job-profile")

urlpatterns = [
    path("jobs/analyses", analyses_list, name="job-analyses"),
    path("jobs/targets", job_targets, name="job-targets"),
    path("jobs/<int:job_id>/target", job_target, name="job-target"),
    path("jobs/<int:job_id>/self-check", job_self_check, name="job-self-check"),
    path("jobs/analyze-catalog/stream", analyze_catalog_stream, name="job-analyze-catalog-stream"),
    path("jobs/analyze-catalog", analyze_catalog_view, name="job-analyze-catalog"),
    path("jobs/analyze", analyze, name="job-analyze"),
    path("jobs", job_list, name="job-list"),
    path("", include(router.urls)),
]
