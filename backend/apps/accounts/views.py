"""Auth + API-Key management endpoints (PLAN.md §6)."""
from django.conf import settings
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import ProviderCredential, UserPreference
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
    pagination_class = None  # plain array — only 3 rows per user

    def get_queryset(self):
        return ProviderCredential.objects.filter(user=self.request.user).order_by("provider")

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        cred = self.get_object()
        ok, message = validate_credential(cred)
        return Response({"is_valid": ok, "message": message},
                        status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
def provider_registry(request):
    """Provider metadata for UI dropdowns (models, default base_url) — no secrets."""
    return Response({
        name: {"models": conf.get("models", []),
               "default_model": conf.get("default_model", ""),
               "base_url": conf.get("base_url", "")}
        for name, conf in settings.LLM_PROVIDERS.items()
    })


class PreferenceView(APIView):
    """GET/PUT the user's chosen default LLM (provider + model)."""

    def get(self, request):
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        return Response({"llm_provider": pref.llm_provider, "llm_model": pref.llm_model})

    def put(self, request):
        provider = request.data.get("llm_provider", "")
        model = request.data.get("llm_model", "")
        if provider and provider not in settings.LLM_PROVIDERS:
            return Response({"llm_provider": ["unknown provider"]},
                            status=status.HTTP_400_BAD_REQUEST)
        pref, _ = UserPreference.objects.get_or_create(user=request.user)
        pref.llm_provider = provider
        pref.llm_model = model
        pref.save()
        return Response({"llm_provider": pref.llm_provider, "llm_model": pref.llm_model})
