"""Shared LLM credential/model selection (user preference -> site default mimo flash)."""
from django.conf import settings


def pick_llm(user):
    """Pick (credential, model_name) honoring the user's UI preference.

    Order: explicit UserPreference -> site default (mimo / mimo-v2.6-flash) ->
    any stored LLM credential. Returns (cred, model) or (None, None).
    """
    from .models import ProviderCredential, UserPreference

    creds = {c.provider: c for c in user.credentials.all()}
    pref = getattr(user, "llm_preference", None)
    if pref and pref.llm_provider and pref.llm_provider in creds:
        cred = creds[pref.llm_provider]
        return cred, (pref.llm_model or cred.model_name or None)

    default_provider = settings.DEFAULT_LLM_PROVIDER
    if default_provider in creds:
        cred = creds[default_provider]
        model = settings.DEFAULT_LLM_MODEL or cred.model_name or None
        return cred, model

    for provider in ("mimo", "deepseek"):
        if provider in creds:
            return creds[provider], (creds[provider].model_name or None)
    return None, None
