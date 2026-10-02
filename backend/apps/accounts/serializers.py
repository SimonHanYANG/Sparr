from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import serializers

from core.llm_adapter import LLMClient, LLMError

from .models import ProviderCredential


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    nickname = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "nickname"]

    def create(self, validated_data):
        nickname = validated_data.pop("nickname", "")
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
            first_name=nickname,
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(source="first_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "nickname"]


class CredentialSerializer(serializers.ModelSerializer):
    """Read: masked key + validation state. Write: plaintext key (write-only)."""

    api_key = serializers.CharField(write_only=True, required=False)
    api_key_masked = serializers.CharField(read_only=True)
    provider_label = serializers.CharField(source="get_provider_display", read_only=True)

    class Meta:
        model = ProviderCredential
        fields = ["id", "provider", "provider_label", "api_key", "api_key_masked",
                  "model_name", "base_url", "is_valid", "last_validated_at",
                  "created_at", "updated_at"]
        read_only_fields = ["id", "is_valid", "last_validated_at", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context["request"]
        provider = attrs.get("provider") or (self.instance.provider if self.instance else None)
        if provider not in ProviderCredential.Provider.values:
            raise serializers.ValidationError({"provider": "unknown provider"})

        # api_key required on create; on update only when replacing
        if self.instance is None and not attrs.get("api_key"):
            raise serializers.ValidationError({"api_key": "required"})
        if provider == ProviderCredential.Provider.MINERU and attrs.get("base_url"):
            raise serializers.ValidationError({"base_url": "mineru uses the platform endpoint"})
        if attrs.get("api_key") and not self.instance:
            if ProviderCredential.objects.filter(user=request.user, provider=provider).exists():
                raise serializers.ValidationError(
                    {"provider": "credential already exists for this provider — update it instead"})
        return attrs

    def create(self, validated_data):
        plaintext = validated_data.pop("api_key")
        cred = ProviderCredential(user=self.context["request"].user, **validated_data)
        cred.set_api_key(plaintext)
        cred.save()
        return cred

    def update(self, instance, validated_data):
        plaintext = validated_data.pop("api_key", None)
        if plaintext:
            instance.set_api_key(plaintext)
            instance.is_valid = None
            instance.last_validated_at = None
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


def validate_credential(cred: ProviderCredential) -> tuple[bool, str]:
    """Live-check a stored key against its provider (PLAN.md §5.1)."""
    from core.mineru_client import MinerUClient

    ok, message = False, "unsupported provider"
    try:
        if cred.provider == ProviderCredential.Provider.MINERU:
            ok, message = MinerUClient(cred.reveal_api_key()).validate_key()
        else:
            client = LLMClient(
                provider=cred.provider,
                api_key=cred.reveal_api_key(),
                model=cred.model_name or None,
                base_url=cred.base_url or None,
            )
            ok, message = client.validate_key()
    except LLMError as exc:
        ok, message = False, str(exc)
    cred.is_valid = ok
    cred.last_validated_at = timezone.now()
    cred.save(update_fields=["is_valid", "last_validated_at", "updated_at"])
    return ok, message
