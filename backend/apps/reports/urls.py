from django.urls import path

from . import views

urlpatterns = [
    path("applications/<int:pk>/report", views.application_report, name="application-report"),
    path("applications/<int:pk>/report/suggestions/<int:suggestion_id>/accept",
         views.suggestion_accept, name="suggestion-accept"),
    path("applications/<int:pk>/report/suggestions/<int:suggestion_id>/reject",
         views.suggestion_reject, name="suggestion-reject"),
]
