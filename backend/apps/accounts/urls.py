from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import CredentialViewSet, MeView, RegisterView, TokenObtainPairView

router = DefaultRouter(trailing_slash=False)  # consistent slash-less REST style (PLAN.md §6)
router.register("credentials", CredentialViewSet, basename="credential")

urlpatterns = [
    path("register", RegisterView.as_view(), name="register"),
    path("login", TokenObtainPairView.as_view(), name="login"),
    path("refresh", TokenRefreshView.as_view(), name="refresh"),
    path("me", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
