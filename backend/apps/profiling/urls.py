from django.urls import path

from .views import compute, portrait

urlpatterns = [
    path("profiling/compute", compute, name="profiling-compute"),
    path("profiling/portrait", portrait, name="profiling-portrait"),
]
