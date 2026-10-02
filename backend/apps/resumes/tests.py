"""Resumes tests: upload validation, parse pipeline (mocked MinerU/LLM), versions."""
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .extraction import _parse_json, _validate
from .models import Resume

TMP_MEDIA = tempfile.mkdtemp()

SAMPLE_STRUCTURED = {
    "basics": {"name": "张三", "intent_role": "后端开发", "contact": "a@b.c", "years_exp": "3 年"},
    "education": [{"school": "某大学", "degree": "本科", "major": "CS", "period": "2016-2020", "desc": ""}],
    "skills": [{"name": "Python", "level": "熟练"}],
    "projects": [{"name": "项目A", "role": "开发", "period": "2022.01 - 2022.06",
                   "tech_stack": ["Django"], "bullets": ["做了啥"], "metrics": ["QPS 1000"]}],
    "work_experiences": [],
    "awards": [],
}


def pdf_bytes():
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class UploadTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u1", password="pw12345678")
        self.client.force_authenticate(self.user)

    def test_upload_pdf_dispatches_parse(self):
        with patch("apps.resumes.views.dispatch") as mock_dispatch:
            resp = self.client.post("/api/resumes/upload", {
                "file": SimpleUploadedFile("简历.pdf", pdf_bytes(), content_type="application/pdf"),
            })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["parse_status"], "uploaded")
        mock_dispatch.assert_called_once_with("parse_resume_task", resp.json()["id"])

    def test_upload_rejects_non_pdf(self):
        with patch("apps.resumes.views.dispatch"):
            resp = self.client.post("/api/resumes/upload", {
                "file": SimpleUploadedFile("a.txt", b"x"),
            })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_requires_file(self):
        resp = self.client.post("/api/resumes/upload", {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class ParsePipelineTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u2", password="pw12345678")
        self.resume = Resume.objects.create(
            user=self.user, title="测试简历",
            source_path="resumes/1/a.pdf", source_filename="a.pdf",
        )

    def _mineru_credential(self):
        from apps.accounts.models import ProviderCredential

        cred = ProviderCredential(user=self.user, provider="mineru")
        cred.set_api_key("mk-test")
        cred.save()
        return cred

    def test_parse_happy_path_creates_v1(self):
        self._mineru_credential()
        with patch("apps.resumes.tasks.read_upload", return_value=pdf_bytes()), \
             patch("apps.resumes.tasks.MinerUClient") as MockMinerU, \
             patch("apps.resumes.tasks._pick_llm") as mock_pick, \
             patch("apps.resumes.extraction.extract_structured",
                   return_value=SAMPLE_STRUCTURED) as mock_extract:
            MockMinerU.return_value.submit_pdf.return_value = "batch-1"
            MockMinerU.return_value.wait_for_result.return_value = {"state": "done"}
            MockMinerU.return_value.fetch_markdown.return_value = "# 简历"
            mock_pick.return_value = (MagicMock(provider="deepseek", reveal_api_key=lambda: "k",
                                                  model_name="", base_url=""), "deepseek-chat")
            from .tasks import parse_resume_task

            parse_resume_task(self.resume.pk)

        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, "parsed")
        self.assertEqual(self.resume.mineru_markdown, "# 简历")
        self.assertEqual(self.resume.mineru_batch_id, "accurate:batch-1")
        self.assertEqual(self.resume.current_version.version_no, 1)
        self.assertEqual(self.resume.current_version.structured_json["basics"]["name"], "张三")
        mock_extract.assert_called_once()

    def test_accurate_timeout_falls_back_to_agent_parse(self):
        self._mineru_credential()
        with patch("apps.resumes.tasks.read_upload", return_value=pdf_bytes()), \
             patch("apps.resumes.tasks.MinerUClient") as MockMinerU, \
             patch("apps.resumes.tasks._pick_llm") as mock_pick, \
             patch("apps.resumes.extraction.extract_structured",
                   return_value=SAMPLE_STRUCTURED):
            from core.mineru_client import MinerUTimeout

            inst = MockMinerU.return_value
            inst.submit_pdf.return_value = "batch-1"
            inst.wait_for_result.side_effect = MinerUTimeout("slow")
            inst.submit_pdf_agent.return_value = "task-9"
            inst.wait_for_agent_result.return_value = {"state": "done"}
            inst.fetch_agent_markdown.return_value = "# 轻量解析"
            mock_pick.return_value = (MagicMock(provider="deepseek", reveal_api_key=lambda: "k",
                                                  model_name="", base_url=""), "deepseek-chat")
            from .tasks import parse_resume_task

            parse_resume_task(self.resume.pk)

        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, "parsed")
        self.assertEqual(self.resume.mineru_markdown, "# 轻量解析")
        self.assertEqual(self.resume.mineru_batch_id, "agent:task-9")

    def test_parse_without_mineru_key_fails_clearly(self):
        from .tasks import parse_resume_task

        parse_resume_task(self.resume.pk)
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, "failed")
        self.assertIn("MinerU", self.resume.parse_error)

    def test_reparse_appends_new_version_number(self):
        """Re-parsing must create v2+, never collide with existing v1 (regression)."""
        from .models import ResumeVersion

        self._mineru_credential()
        ResumeVersion.objects.create(resume=self.resume, version_no=1,
                                     structured_json=SAMPLE_STRUCTURED, change_note="v1")
        with patch("apps.resumes.tasks.read_upload", return_value=pdf_bytes()), \
             patch("apps.resumes.tasks.MinerUClient") as MockMinerU, \
             patch("apps.resumes.tasks._pick_llm",
                   return_value=(MagicMock(provider="mimo", reveal_api_key=lambda: "k",
                                           model_name="", base_url=""), "mimo-v2.6-pro")), \
             patch("apps.resumes.extraction.extract_structured",
                   return_value=SAMPLE_STRUCTURED):
            MockMinerU.return_value.submit_pdf.return_value = "batch-1"
            MockMinerU.return_value.wait_for_result.return_value = {"state": "done"}
            MockMinerU.return_value.fetch_markdown.return_value = "# 简历"
            from .tasks import parse_resume_task

            parse_resume_task(self.resume.pk)
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, "parsed")
        self.assertEqual(self.resume.current_version.version_no, 2)
        self.assertIn("mimo/mimo-v2.6-pro", self.resume.current_version.change_note)

    def test_parse_without_llm_key_saves_markdown_but_fails_extraction(self):
        self._mineru_credential()
        with patch("apps.resumes.tasks.read_upload", return_value=pdf_bytes()), \
             patch("apps.resumes.tasks.MinerUClient") as MockMinerU, \
             patch("apps.resumes.tasks._pick_llm", return_value=(None, None)):
            MockMinerU.return_value.submit_pdf.return_value = "batch-1"
            MockMinerU.return_value.wait_for_result.return_value = {"state": "done"}
            MockMinerU.return_value.fetch_markdown.return_value = "# 简历"
            from .tasks import parse_resume_task

            parse_resume_task(self.resume.pk)
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.parse_status, "failed")
        self.assertEqual(self.resume.mineru_markdown, "# 简历")
        self.assertIn("大模型", self.resume.parse_error)


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class VersionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u3", password="pw12345678")
        self.client.force_authenticate(self.user)
        self.resume = Resume.objects.create(
            user=self.user, title="测试", source_path="x", source_filename="x.pdf")

    def test_save_creates_new_version_and_rollback(self):
        r1 = self.client.post(f"/api/resumes/{self.resume.pk}/versions",
                              {"structured_json": SAMPLE_STRUCTURED, "change_note": "v1"},
                              format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.json()["version_no"], 1)

        edited = dict(SAMPLE_STRUCTURED, awards=["奖学金"])
        r2 = self.client.post(f"/api/resumes/{self.resume.pk}/versions",
                              {"structured_json": edited, "change_note": "加了奖项"},
                              format="json")
        self.assertEqual(r2.json()["version_no"], 2)

        r3 = self.client.post(f"/api/resumes/{self.resume.pk}/versions/1/rollback")
        self.assertEqual(r3.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r3.json()["version_no"], 3)
        self.assertEqual(r3.json()["structured_json"]["awards"], [])

    def test_version_requires_all_fields(self):
        resp = self.client.post(f"/api/resumes/{self.resume.pk}/versions",
                                {"structured_json": {"basics": {}}}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class ExtractionHelpersTests(APITestCase):
    def test_parse_resume_task_registered(self):
        """Web-process regression: dispatch must find the task (upload 500 bug)."""
        from core.tasks import _registry

        self.assertIn("parse_resume_task", _registry)
    def test_parse_json_strips_fences(self):
        raw = "```json\n{\"a\": 1}\n```"
        self.assertEqual(_parse_json(raw), {"a": 1})

    def test_parse_json_finds_object_in_noise(self):
        self.assertEqual(_parse_json("说明：\n{\"a\": 1}\n完毕"), {"a": 1})

    def test_validate_requires_keys(self):
        with self.assertRaises(ValueError):
            _validate({"basics": {}})
        _validate(SAMPLE_STRUCTURED)  # full schema passes
