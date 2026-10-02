from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ResumeViewSet, create_blank_resume, replace_resume_pdf, upload_resume

router = DefaultRouter(trailing_slash=False)
router.register("resumes", ResumeViewSet, basename="resume")

urlpatterns = [
    path("resumes/upload", upload_resume, name="resume-upload"),
    path("resumes/blank", create_blank_resume, name="resume-blank"),
    path("resumes/<int:pk>/replace", replace_resume_pdf, name="resume-replace"),
    path("", include(router.urls)),
]
