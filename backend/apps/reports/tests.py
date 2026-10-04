"""综合报告域测试（mock LLM）——生成/幂等/简历建议采纳闭环（PLAN.md §5.4）。"""
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.jobs.models import JobPosition
from apps.resumes.models import Resume, ResumeVersion
from apps.sessions.models import ApplicationSession, InterviewTurn

FAKE_REPORT = {
    "overall_score": 72,
    "hire_recommendation": "待定",
    "dimension_radar": {"基础知识": 65, "编码能力": 70, "项目深度": 60, "沟通表达": 80, "岗位匹配": 75},
    "per_stage_summary": [{"stage": "基础笔试", "score": "70/100", "summary": "基础尚可"}],
    "highlights": ["提到 QPS 10k"],
    "weaknesses": ["指标口径不清"],
    "improvement_plan": [{"area": "项目表达", "action": "按 STAR 准备深挖材料"}],
    "resume_suggestions": [
        {"field_path": "projects[0].metrics",
         "original_text": "QPS 提升",
         "suggested_text": "QPS 提升 3 倍（压测口径：wrk 60s 并发 256）",
         "reason": "指标没写来源，面试必被追问"},
    ],
}


class ReportTests(APITestCase):
    def setUp(self):
        from apps.accounts.models import ProviderCredential

        self.user = User.objects.create_user("r1", password="pw12345678")
        self.client.force_authenticate(self.user)
        cred = ProviderCredential(user=self.user, provider="mimo")
        cred.set_api_key("k")
        cred.save()
        self.resume = Resume.objects.create(
            user=self.user, title="r", source_path="x", source_filename="x.pdf",
            parse_status="parsed")
        self.version = ResumeVersion.objects.create(
            resume=self.resume, version_no=1,
            structured_json={"basics": {"name": "张三"},
                             "projects": [{"metrics": ["QPS 提升"]}]})
        self.resume.current_version = self.version
        self.resume.save()
        self.job = JobPosition.objects.create(
            category="后端", title="后端开发", level="校招", description="d",
            skill_requirements=[], knowledge_points=[], coding_topics=[],
            interview_focus=[])
        self.session = ApplicationSession.objects.create(
            user=self.user, job=self.job, resume_version=self.version,
            status=ApplicationSession.Status.FINISHED,
            review_json={"dimensions": {"基础知识": 60}, "overall": "一般"})
        InterviewTurn.objects.create(application=self.session, seq=1,
                                     role="interviewer", content="介绍下自己")

    def test_report_generation_idempotent(self):
        with patch("apps.reports.views.generate_report",
                   return_value=dict(FAKE_REPORT)) as mock:
            resp = self.client.post(f"/api/applications/{self.session.id}/report")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertFalse(body["reused"])
        self.assertEqual(body["report"]["overall_score"], 72)
        self.assertEqual(len(body["report"]["suggestions"]), 1)

        with patch("apps.reports.views.generate_report") as mock2:
            resp = self.client.post(f"/api/applications/{self.session.id}/report")
        self.assertTrue(resp.json()["reused"])
        self.assertEqual(mock2.call_count, 0)

    def test_report_requires_finished_session(self):
        self.session.status = ApplicationSession.Status.IN_PROGRESS
        self.session.save()
        resp = self.client.post(f"/api/applications/{self.session.id}/report")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_suggestion_accept_creates_new_resume_version(self):
        """闭环：采纳建议 → 结构化简历更新 → 新版本（不触碰 PDF）。"""
        with patch("apps.reports.views.generate_report", return_value=dict(FAKE_REPORT)):
            body = self.client.post(f"/api/applications/{self.session.id}/report").json()
        sug = body["report"]["suggestions"][0]
        resp = self.client.post(
            f"/api/applications/{self.session.id}/report/suggestions/{sug['id']}/accept")
        applied = resp.json()["suggestion"]
        self.assertEqual(applied["status"], "accepted")
        self.assertIn("v2", applied["apply_note"])

        new_version = ResumeVersion.objects.get(resume=self.resume, version_no=2)
        self.assertIn("压测口径", new_version.structured_json["projects"][0]["metrics"][0])
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.current_version_id, new_version.id)
        self.assertIn("采纳面试修改建议", new_version.change_note)

        # 再次决策不重复应用
        resp = self.client.post(
            f"/api/applications/{self.session.id}/report/suggestions/{sug['id']}/accept")
        self.assertEqual(resp.json()["suggestion"]["status"], "accepted")
        self.assertEqual(ResumeVersion.objects.filter(resume=self.resume).count(), 2)

    def test_suggestion_reject(self):
        with patch("apps.reports.views.generate_report", return_value=dict(FAKE_REPORT)):
            body = self.client.post(f"/api/applications/{self.session.id}/report").json()
        sug = body["report"]["suggestions"][0]
        resp = self.client.post(
            f"/api/applications/{self.session.id}/report/suggestions/{sug['id']}/reject")
        self.assertEqual(resp.json()["suggestion"]["status"], "rejected")
        self.assertEqual(ResumeVersion.objects.filter(resume=self.resume).count(), 1)

    def test_apply_suggestion_replace_and_missing(self):
        from apps.reports.report import apply_suggestion_to_structured

        structured = {"projects": [{"metrics": ["QPS 提升", "延迟降低"]}]}
        updated, hits = apply_suggestion_to_structured(structured, "QPS 提升", "QPS 提升 3 倍")
        self.assertEqual(hits, 1)
        self.assertEqual(updated["projects"][0]["metrics"][0], "QPS 提升 3 倍")
        self.assertEqual(updated["projects"][0]["metrics"][1], "延迟降低")
        _, misses = apply_suggestion_to_structured(structured, "不存在的原文", "x")
        self.assertEqual(misses, 0)

    def test_report_lights_up_flow_summary_step(self):
        from apps.profiling.flow import flow_state

        with patch("apps.reports.views.generate_report", return_value=dict(FAKE_REPORT)):
            self.client.post(f"/api/applications/{self.session.id}/report")
        state = flow_state(self.user)
        summary_step = [s for s in state["steps"] if s["key"] == "summary"][0]
        self.assertEqual(summary_step["status"], "done")
