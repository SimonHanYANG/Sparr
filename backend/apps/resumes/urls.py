from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ResumeViewSet, upload_resume

router = DefaultRouter(trailing_slash=False)
router.register("resumes", ResumeViewSet, basename="resume")

urlpatterns = [
    path("resumes/upload", upload_resume, name="resume-upload"),
    path("", include(router.urls)),
]
