from django.test import TestCase

# Create your tests here.


"""Job APIs tests: custom JD profiles + LLM match analysis (mocked)."""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.resumes.models import Resume, ResumeVersion

SAMPLE = {
    "basics": {"name": "张三", "intent_role": "后端", "contact": "x", "years_exp": "3 年"},
    "education": [], "skills": [{"name": "Python", "level": "熟练"}],
    "projects": [], "work_experiences": [], "awards": [],
}


class JobProfileAndAnalyzeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("j1", password="pw12345678")
        self.client.force_authenticate(self.user)
        self.resume = Resume.objects.create(
            user=self.user, title="r", source_path="x", source_filename="x.pdf",
            parse_status="parsed")
        self.version = ResumeVersion.objects.create(
            resume=self.resume, version_no=1, structured_json=SAMPLE)
        self.resume.current_version = self.version
        self.resume.save()

    def test_custom_jd_profile_crud(self):
        resp = self.client.post("/api/jobs/profiles",
                                {"title": "某厂后端", "jd_text": "要求熟悉 Python、分布式系统"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        pid = resp.json()["id"]
        resp = self.client.get("/api/jobs/profiles")
        self.assertEqual(len(resp.json()), 1)
        resp = self.client.delete(f"/api/jobs/profiles/{pid}")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_analyze_requires_llm_key(self):
        self.client.post("/api/jobs/profiles", {"title": "t", "jd_text": "jd"})
        resp = self.client.post("/api/jobs/analyze", {"job_profile_id": 999})
        self.assertIn(resp.status_code, (400, 404))

    def test_analyze_custom_jd_with_mock_llm(self):
        from apps.accounts.models import ProviderCredential

        cred = ProviderCredential(user=self.user, provider="mimo")
        cred.set_api_key("k")
        cred.save()
        profile = self.client.post("/api/jobs/profiles",
                                   {"title": "某厂后端", "jd_text": "要求 Python 分布式"}).json()
        fake = {"score": 72, "summary": "基本匹配", "matched": [{"requirement": "Python", "evidence": "技能栏"}],
                "gaps": [{"requirement": "分布式", "status": "未体现", "advice": "补项目"}], "advice": ["改简历"]}
        with patch("apps.jobs.views.analyze_match", return_value=fake):
            resp = self.client.post("/api/jobs/analyze",
                                    {"job_profile_id": profile["id"]})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertEqual(body["score"], 72)
        self.assertEqual(body["gaps"][0]["requirement"], "分布式")
        self.assertEqual(body["model_name"], "mimo/mimo-v2.6-flash")
