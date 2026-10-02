"""Seed ProviderCredentials from environment variables (local testing only).

Reads MINERU_API_KEY / DEEPSEEK_API_KEY / MIMO_API_KEY (and MIMO_BASE_URL)
from .env and upserts them for a user — so local dev is test-ready without
keys ever touching the codebase (PLAN.md §5.1 privacy stance).

Usage: uv run python manage.py seed_credentials --username demo
"""
import os

import environ
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import ProviderCredential

environ.Env.read_env(settings.BASE_DIR.parent / ".env")


class Command(BaseCommand):
    help = "Seed provider API keys from env (.env) for a user — local testing only"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(f"user not found: {options['username']}") from exc

        mapping = {
            ProviderCredential.Provider.MINERU: ("MINERU_API_KEY", ""),
            ProviderCredential.Provider.DEEPSEEK: ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"),
            ProviderCredential.Provider.MIMO: ("MIMO_API_KEY", "MIMO_BASE_URL"),
        }
        seeded = []
        for provider, (key_env, url_env) in mapping.items():
            key = os.environ.get(key_env, "").strip()
            if not key:
                continue
            base_url = os.environ.get(url_env, "").strip() if url_env else ""
            model = os.environ.get(f"{provider.upper()}_DEFAULT_MODEL", "").strip()
            cred, _ = ProviderCredential.objects.get_or_create(
                user=user, provider=provider,
                defaults={"base_url": base_url, "model_name": model},
            )
            cred.set_api_key(key)
            if base_url:
                cred.base_url = base_url
            if model:
                cred.model_name = model
            cred.is_valid = None
            cred.save()
            seeded.append(provider)
        self.stdout.write(self.style.SUCCESS(f"seeded credentials for {user.username}: {seeded}"))
