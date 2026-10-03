"""面试会话域测试（mock LLM）——计划生成/幂等/薄弱项联动/断点状态。

防机械契约（§5.3③-A 机制 1）由 test_plan_validation_drops_questions_without_why 锁定。
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.jobs.models import JobPosition, JobProfile, JobSelfCheck
from apps.resumes.models import Resume, ResumeVersion
from apps.sessions.interview import _validate_plan, parse_eval_tag

SAMPLE = {
    "basics": {"name": "张三", "intent_role": "后端", "contact": "x", "years_exp": "3 年"},
    "education": [], "skills": [{"name": "Python", "level": "熟练"}],
    "projects": [{"name": "缓存网关", "role": "后端", "tech_stack": ["Redis"],
                  "bullets": ["QPS 提升"], "metrics": "QPS 10k"}],
    "work_experiences": [], "awards": [],
}

FAKE_PLAN = {
    "briefing": {"persona": "资深后端面试官", "projects": [], "self_check_weak": [], "quiz_weak": []},
    "phases": [
        {"name": "自我介绍", "target_min": 3},
        {"name": "基础知识", "target_min": 10, "question_pool": [
            {"id": "q1", "topic": "Redis 一致性", "difficulty": 3,
             "why": "自评模糊考点", "followups": ["主从切换怎么办？"]},
            {"id": "q2", "topic": "通用八股题", "difficulty": 3,
             "why": "", "followups": []},
        ]},
        {"name": "项目深挖", "target_min": 12, "targets": [
            {"project": "缓存网关", "angles": ["技术选型依据"]},
            {"project": "不存在的项目", "angles": []},
        ]},
    ],
}


class SessionSetupMixin:
    def _setup(self):
        from apps.accounts.models import ProviderCredential

        self.user = User.objects.create_user("s1", password="pw12345678")
        self.client.force_authenticate(self.user)
        self.resume = Resume.objects.create(
            user=self.user, title="r", source_path="x", source_filename="x.pdf",
            parse_status="parsed")
        self.version = ResumeVersion.objects.create(
            resume=self.resume, version_no=1, structured_json=SAMPLE)
        self.resume.current_version = self.version
        self.resume.save()
        self.job = JobPosition.objects.create(
            category="后端", title="后端开发", level="校招", description="后端",
            skill_requirements=[{"skill": "Python", "weight": 5, "required": True}],
            knowledge_points=["Redis"], coding_topics=["缓存"],
            interview_focus=["分布式"])
        cred = ProviderCredential(user=self.user, provider="mimo")
        cred.set_api_key("k")
        cred.save()


class ApplicationSessionTests(SessionSetupMixin, APITestCase):
    def setUp(self):
        self._setup()

    def test_create_session_and_list(self):
        resp = self.client.post("/api/applications", {"job_id": self.job.id},
                                format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertEqual(body["job_title"], "后端开发（校招）")
        self.assertEqual(body["status"], "created")
        self.assertEqual(body["interview_state"]["asked_question_ids"], [])
        resp = self.client.get("/api/applications")
        self.assertEqual(len(resp.json()), 1)
        self.assertFalse(resp.json()[0]["has_plan"])

    def test_create_requires_target_and_resume(self):
        resp = self.client.post("/api/applications", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plan_generation_idempotent_and_force(self):
        sid = self.client.post("/api/applications", {"job_id": self.job.id},
                               format="json").json()["id"]
        with patch("apps.sessions.views.generate_plan", return_value=FAKE_PLAN) as mock:
            resp = self.client.post(f"/api/applications/{sid}/plan")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.json()["reused"])
        self.assertEqual(resp.json()["plan"]["phases"][0]["name"], "自我介绍")
        self.assertEqual(mock.call_count, 1)

        # idempotent: second call returns stored plan without LLM
        with patch("apps.sessions.views.generate_plan") as mock2:
            resp = self.client.post(f"/api/applications/{sid}/plan")
        self.assertTrue(resp.json()["reused"])
        self.assertEqual(mock2.call_count, 0)

        # force regenerates
        with patch("apps.sessions.views.generate_plan", return_value=FAKE_PLAN):
            resp = self.client.post(f"/api/applications/{sid}/plan",
                                    {"force": True}, format="json")
        self.assertFalse(resp.json()["reused"])

    def test_plan_feeds_self_check_weak_points(self):
        JobSelfCheck.objects.create(
            user=self.user, job=self.job,
            checks_json={"Redis 一致性": "不会", "TCP": "模糊", "HTTP": "掌握"})
        sid = self.client.post("/api/applications", {"job_id": self.job.id},
                               format="json").json()["id"]
        with patch("apps.sessions.views.generate_plan", return_value=FAKE_PLAN) as mock:
            self.client.post(f"/api/applications/{sid}/plan")
        kwargs = mock.call_args.kwargs
        self.assertEqual(sorted(kwargs["weak_points"]), ["Redis 一致性", "TCP"])

    def test_detail_returns_plan_and_session_marks_interview_done(self):
        sid = self.client.post("/api/applications", {"job_id": self.job.id},
                               format="json").json()["id"]
        with patch("apps.sessions.views.generate_plan", return_value=FAKE_PLAN):
            self.client.post(f"/api/applications/{sid}/plan")
        resp = self.client.get(f"/api/applications/{sid}")
        body = resp.json()
        self.assertTrue(body["has_plan"])
        self.assertEqual(body["plan"]["phases"][1]["question_pool"][0]["id"], "q1")
        self.assertEqual(body["turns"], [])
        self.assertEqual(body["status"], "in_progress")

        # journey step 3 lights up once a session exists (flow.py probe)
        from apps.profiling.flow import flow_state
        state = flow_state(self.user)
        interview_step = [s for s in state["steps"] if s["key"] == "interview"][0]
        self.assertEqual(interview_step["status"], "done")


class PlanValidationTests(SessionSetupMixin, APITestCase):
    def test_plan_validation_drops_questions_without_why(self):
        """§5.3③-A 机制 1：无 `why` 证据的题不得进入题池；虚构项目不得进 targets（契约锁定）。"""
        import copy

        data = _validate_plan(copy.deepcopy(FAKE_PLAN), ["缓存网关"])
        pool = data["phases"][1]["question_pool"]
        self.assertEqual([q["id"] for q in pool], ["q1"])  # q2 (why="") dropped
        targets = data["phases"][2]["targets"]
        self.assertEqual([t["project"] for t in targets], ["缓存网关"])

    def test_parse_eval_tag_splits_hidden_eval(self):
        visible, ev = parse_eval_tag(
            '你刚才提到 Redis 做缓存，主从切换时怎么保证一致？\n'
            '[EVAL]{"understand": 3, "depth": 2, "rote": false, "off_topic": false, '
            '"flaw": "", "highlight": "提到缓存", "next_action": "follow_up", "comment": "ok"}[/EVAL]')
        self.assertNotIn("[EVAL]", visible)
        self.assertIn("Redis", visible)
        self.assertEqual(ev["next_action"], "follow_up")

        visible, ev = parse_eval_tag("普通回答，没有评估标记")
        self.assertIsNone(ev)
