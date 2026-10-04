from django.urls import path

from . import views

urlpatterns = [
    path("applications", views.application_list, name="application-list"),
    path("applications/<int:pk>", views.application_detail, name="application-detail"),
    path("applications/<int:pk>/plan", views.application_plan, name="application-plan"),
    path("applications/<int:pk>/plan/stream", views.application_plan_stream,
         name="application-plan-stream"),
    path("applications/<int:pk>/turns", views.application_turn, name="application-turn"),
    path("applications/<int:pk>/turns/cancel", views.application_turn_cancel,
         name="application-turn-cancel"),
    path("applications/<int:pk>/review", views.application_review,
         name="application-review"),
    path("applications/<int:pk>/quiz", views.application_quiz, name="application-quiz"),
    path("applications/<int:pk>/quiz/submit", views.application_quiz_submit,
         name="application-quiz-submit"),
    path("applications/<int:pk>/coding", views.application_coding, name="application-coding"),
    path("applications/<int:pk>/coding/submit", views.application_coding_submit,
         name="application-coding-submit"),
]
