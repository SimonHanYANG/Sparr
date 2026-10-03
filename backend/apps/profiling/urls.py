from django.urls import path

from .views import compute, flow, portrait

urlpatterns = [
    path("profiling/compute", compute, name="profiling-compute"),
    path("profiling/portrait", portrait, name="profiling-portrait"),
    path("flow/state", flow, name="flow-state"),
]
