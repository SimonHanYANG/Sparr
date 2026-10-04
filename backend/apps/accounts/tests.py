"""Accounts tests: registration, JWT auth, credential encryption/masking."""
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from core.crypto import decrypt, encrypt, mask


class CryptoTests(APITestCase):
    def test_encrypt_roundtrip(self):
        token = "sk-abc123secret"
        self.assertEqual(decrypt(encrypt(token)), token)

    def test_mask_hides_plaintext(self):
        masked = mask("sk-abc123secret")
        self.assertNotIn("abc123secret", masked)
        self.assertTrue(masked.startswith("sk-"))
        self.assertEqual(mask("short"), "****")


class AuthFlowTests(APITestCase):
    def test_register_login_me(self):
        resp = self.client.post("/api/auth/register", {
            "username": "han", "password": "Str0ng!Pass", "nickname": "涵哥",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.post("/api/auth/login", {
            "username": "han", "password": "Str0ng!Pass",
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        token = resp.json()["access"]

        resp = self.client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["username"], "han")

    def test_me_requires_auth(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordPolicyTests(APITestCase):
    """core.validators.SparrPasswordValidator: 8-64 chars, upper, lower, special."""

    def _register(self, password):
        return self.client.post("/api/auth/register", {
            "username": "pwuser", "password": password,
        })

    def test_weak_passwords_rejected(self):
        resp = self._register("abc1!")  # too short
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", resp.json())

        for pw in ["nouppercase1!", "NOLOWERCASE1!", "NoSpecial123"]:
            resp = self._register(pw)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, pw)
            self.assertIn("password", resp.json())

    def test_strong_password_accepted(self):
        resp = self._register("Str0ng!Pass")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class CredentialTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="pw12345678")
        self.client.force_authenticate(self.user)

    def test_create_masks_key_and_encrypts_at_rest(self):
        resp = self.client.post("/api/auth/credentials", {
            "provider": "deepseek", "api_key": "sk-verysecretkey1234",
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertNotIn("sk-verysecretkey1234", str(body))
        self.assertIn("****", body["api_key_masked"])

        cred = self.user.credentials.get(provider="deepseek")
        self.assertNotIn("verysecretkey1234", cred.api_key_encrypted)  # not plaintext at rest
        self.assertEqual(cred.reveal_api_key(), "sk-verysecretkey1234")  # server-side only

    def test_duplicate_provider_rejected(self):
        self.client.post("/api/auth/credentials", {"provider": "mimo", "api_key": "k1k1k1k1k1"})
        resp = self.client.post("/api/auth/credentials", {"provider": "mimo", "api_key": "k2k2k2k2k2"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_key_and_never_read_plaintext(self):
        self.client.post("/api/auth/credentials", {"provider": "deepseek", "api_key": "k1k1k1k1k1"})
        cred = self.user.credentials.get(provider="deepseek")
        resp = self.client.patch(f"/api/auth/credentials/{cred.id}", {"api_key": "newkey9999"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cred.refresh_from_db()
        self.assertEqual(cred.reveal_api_key(), "newkey9999")

        # list endpoint only ever returns the mask
        resp = self.client.get("/api/auth/credentials")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("newkey9999", str(resp.json()))


class ValidateKeyTests(APITestCase):
    """验证探活：思考模型小预算导致空正文 ≠ key 无效（用户现场问题回归）。"""

    def test_validate_key_tolerates_thinking_model_empty_content(self):
        from unittest.mock import MagicMock, patch

        from core.llm_adapter import LLMClient, LLMError

        client = LLMClient(provider="mimo", api_key="tp-test", model="mimo-v2.6-flash",
                           base_url="https://token-plan-cn.xiaomimimo.com/v1")

        # 思考模型把预算吞掉 → 空正文 → 仍应判定可用
        with patch.object(LLMClient, "chat",
                          side_effect=LLMError("LLM mimo returned empty content (finish_reason=length)")):
            ok, _ = client.validate_key()
        self.assertTrue(ok)

        # 真正的认证/网络错误 → 失败
        with patch.object(LLMClient, "chat",
                          side_effect=LLMError("LLM mimo HTTP 401: unauthorized")):
            ok, msg = client.validate_key()
        self.assertFalse(ok)
        self.assertIn("401", msg)

        # 正常返回 → 可用
        with patch.object(LLMClient, "chat", return_value="ok"):
            ok, _ = client.validate_key()
        self.assertTrue(ok)
