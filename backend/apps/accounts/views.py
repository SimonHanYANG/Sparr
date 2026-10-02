"""Auth + API-Key management endpoints (PLAN.md §6)."""
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import ProviderCredential
from .serializers import (
    CredentialSerializer,
    RegisterSerializer,
    UserSerializer,
    validate_credential,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class CredentialViewSet(viewsets.ModelViewSet):
    """CRUD for provider credentials; keys are masked on read, write-only plaintext."""

    serializer_class = CredentialSerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return ProviderCredential.objects.filter(user=self.request.user).order_by("provider")

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        cred = self.get_object()
        ok, message = validate_credential(cred)
        return Response({"is_valid": ok, "message": message},
                        status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST)
