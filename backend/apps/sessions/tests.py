"""面试会话域测试（mock LLM）——计划生成/幂等/薄弱项联动/断点状态。

防机械契约（§5.3③-A 机制 1）由 test_plan_validation_drops_questions_without_why 锁定。
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase, APITransactionTestCase

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

    def test_parse_json_repairs_llm_breakage(self):
        """用户现场故障类：字符串内未转义引号（Expecting ',' delimiter）/ 全角逗号 / 截断。"""
        from apps.sessions.interview import _parse_json

        data = _parse_json('{"phases": [{"name": "基础", "why": "JD 要求 "高并发" 经验"}]}')
        self.assertIn("高并发", data["phases"][0]["why"])

        data = _parse_json('{"phases": [{"name": "基础"}]，"briefing": {"persona": "p"}}')
        self.assertEqual(data["briefing"]["persona"], "p")

        data = _parse_json('{"phases": [{"name": "基础", "question_pool": [{"id": "q1", "topic": "TCP')
        self.assertEqual(data["phases"][0]["name"], "基础")

        data = _parse_json('```json\n{"phases": [{"name": "基础"}]}\n```')
        self.assertEqual(data["phases"][0]["name"], "基础")

    def test_generate_plan_bumps_budget_on_truncation(self):
        """截断（尾部未闭合）时重试放宽 max_tokens，而不是同样预算再撞一次。"""
        from apps.sessions.interview import generate_plan

        fake = MagicMock()
        budgets = []

        def _stream(messages, **kwargs):
            budgets.append(kwargs.get("max_tokens"))
            if len(budgets) == 1:
                return iter(['{"phases": [{"name": "基础"'])  # truncated mid-object
            return iter([json.dumps(FAKE_PLAN, ensure_ascii=False)])

        fake.chat_stream.side_effect = _stream
        plan = generate_plan(fake, {"projects": [{"name": "缓存网关"}]},
                             job_title="t", jd_text="jd", weak_points=[])
        self.assertEqual(plan["phases"][0]["name"], "自我介绍")
        self.assertGreater(budgets[1], budgets[0])

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


class InterviewEngineTests(SessionSetupMixin, APITestCase):
    """状态机 / 禁止清单 / EVAL 剥离（§5.3③-A 机制 2/5 纯逻辑）。"""

    def setUp(self):
        self._setup()

    def test_decide_action_mapping(self):
        from apps.sessions.engine import decide_action
        self.assertEqual(decide_action({"rote": True, "understand": 3, "depth": 3}), "follow_up")
        self.assertEqual(decide_action({"flaw": "指标口径不明"}), "dig_deeper")
        self.assertEqual(decide_action({"understand": 5, "depth": 5, "rote": False}), "advance")
        self.assertEqual(decide_action({"off_topic": True}), "pull_back")
        self.assertEqual(decide_action({"understand": 2, "depth": 3}), "follow_up")

    def test_prohibition_hits(self):
        from apps.sessions.engine import prohibition_hits
        self.assertIn("客套八股", prohibition_hits("这是一个很好的问题，你说说 TCP？"))
        self.assertIn("机械报幕", prohibition_hits("下面进入第二题。"))
        self.assertIn("一次抛多个问题", prohibition_hits("为什么？那然后呢？还有吗？"))

    def test_extract_plan_hints(self):
        from apps.sessions.interview import extract_plan_hints
        hints = extract_plan_hints(
            '{"briefing": {"projects": [{"project": "缓存网关"}]}, '
            '"phases": [{"question_pool": [{"id": "q1", "topic": "Redis 一致性"}, '
            '{"id": "q2", "topic": "TCP 三次握手"}]}]}')
        self.assertEqual(hints, ["缓存网关", "Redis 一致性", "TCP 三次握手"])

    def test_generate_reply_strips_eval_marker(self):
        from apps.sessions.engine import generate_reply
        fake = MagicMock()
        fake.chat_stream.return_value = iter([
            "你刚才提到 Redis，", "主从切换时怎么保证一致？\n",
            '[EVAL]{"understand": 3, "depth": 2, "rote": false, "off_topic": false, '
            '"flaw": "", "highlight": "", "next_action": "follow_up", "comment": ""}[/EVAL]',
        ])
        result = {}
        deltas = list(generate_reply(fake, [], result))
        visible = "".join(deltas)
        self.assertNotIn("[EVAL]", visible)
        self.assertIn("Redis", visible)
        self.assertEqual(result["eval"]["next_action"], "follow_up")
        self.assertEqual(result["visible"], visible.strip())

    def test_generate_reply_single_stream_no_ghost_text(self):
        """回归：函数体曾整体重复——每轮两次 LLM 流，第二段像'思考'一样多出来、
        落库又消失。锁死：chat_stream 只调一次，流出内容与落库内容一致。"""
        from apps.sessions.engine import generate_reply
        fake = MagicMock()
        fake.chat_stream.return_value = iter([
            '回答正文。', '[EVAL]{"understand": 3, "depth": 3, "rote": false, '
            '"off_topic": false, "flaw": "", "highlight": "", "next_action": "continue", '
            '"comment": ""}[/EVAL]',
        ])
        result = {}
        streamed = "".join(generate_reply(fake, [], result))
        self.assertEqual(fake.chat_stream.call_count, 1)
        self.assertEqual(streamed.strip(), result["visible"].strip())
        self.assertNotIn("EVAL", streamed)

class InterviewTurnStreamTests(SessionSetupMixin, APITransactionTestCase):
    """SSE 轮次流测试——worker 线程写库需要真实事务（非嵌套），故用
    APITransactionTestCase；生产环境 sqlite 自动提交/postgres 无此问题。"""

    def setUp(self):
        self._setup()
        import copy as _copy

        from apps.sessions.interview import _validate_plan

        sid = self.client.post("/api/applications", {"job_id": self.job.id},
                               format="json").json()["id"]
        plan = _validate_plan(_copy.deepcopy(FAKE_PLAN), ["缓存网关"])
        with patch("apps.sessions.views.generate_plan", return_value=plan):
            self.client.post(f"/api/applications/{sid}/plan")
        self.sid = sid

    def _fake_llm(self):
        fake = MagicMock()
        fake.provider, fake.model = "mimo", "mimo-v2.6-flash"
        fake.chat.return_value = "摘要：聊了缓存网关选型。"

        def _stream(messages, **kwargs):
            return iter([
                "嗯，聊聊你简历里的缓存网关项目吧，", "当时为什么选 Redis？\n",
                '[EVAL]{"understand": 3, "depth": 3, "rote": false, "off_topic": false, '
                '"flaw": "指标口径不明", "highlight": "提到缓存网关", "next_action": "dig_deeper", '
                '"comment": "待核实 QPS"}[/EVAL]',
            ])

        fake.chat_stream.side_effect = _stream  # fresh iterator per call
        return fake

    def _consume(self, resp):
        events = []
        for chunk in resp.streaming_content:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            for block in text.split("\n\n"):
                if block.startswith("event:"):
                    ev = block.split("\n", 1)[0][6:].strip()
                    data = block.split("data: ", 1)[1] if "data: " in block else ""
                    events.append((ev, data))
        return events

    def test_turn_sse_streams_and_persists_state(self):
        fake = self._fake_llm()
        with patch("apps.sessions.views._llm_or_400",
                   return_value=(fake, "mimo-v2.6-flash", None)):
            resp = self.client.post(f"/api/applications/{self.sid}/turns",
                                    {"action": "start"})
        self.assertEqual(resp.status_code, 200)
        events = self._consume(resp)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "meta")
        self.assertIn("delta", kinds)
        self.assertEqual(kinds[-1], "done")
        joined = "".join(d for k, d in events if k == "delta")
        self.assertNotIn("[EVAL]", joined)  # 机制 2：隐藏评估不外泄
        self.assertIn("缓存网关", joined)

        detail = self.client.get(f"/api/applications/{self.sid}").json()
        self.assertEqual(len(detail["turns"]), 2)  # system(start) + interviewer
        interviewer = detail["turns"][-1]
        self.assertEqual(interviewer["role"], "interviewer")
        self.assertTrue(interviewer["has_eval"])
        self.assertIn("指标口径不明", detail["interview_state"]["found_flaws"][0]["text"])
        self.assertEqual(detail["last_turn_seq"], 2)

    def test_answer_turn_uses_state_machine_directive(self):
        fake = self._fake_llm()
        with patch("apps.sessions.views._llm_or_400",
                   return_value=(fake, "mimo-v2.6-flash", None)):
            # consume each SSE response before the next POST — the worker thread
            # must finish persisting before the following turn computes its seq
            self._consume(self.client.post(f"/api/applications/{self.sid}/turns",
                                           {"action": "start"}))
            resp = self.client.post(f"/api/applications/{self.sid}/turns",
                                    {"action": "answer", "content": "我们用了 Redis 主从复制"})
        kinds = [k for k, _ in self._consume(resp)]
        self.assertEqual(kinds[-1], "done")
        # messages received by LLM must carry the state-machine directive
        last_call = fake.chat_stream.call_args[0][0]
        system_texts = [m.content for m in last_call if m.role == "system"]
        self.assertTrue(any("动作" in t for t in system_texts))
        detail = self.client.get(f"/api/applications/{self.sid}").json()
        self.assertEqual(len(detail["turns"]), 4)

    def test_end_action_finishes_session(self):
        """结束即结束：直接收束，不再生成面试官告别语（用户要求）。"""
        fake = self._fake_llm()
        with patch("apps.sessions.views._llm_or_400",
                   return_value=(fake, "mimo-v2.6-flash", None)):
            self._consume(self.client.post(f"/api/applications/{self.sid}/turns",
                                           {"action": "start"}))
            calls_before_end = fake.chat_stream.call_count
            self._consume(self.client.post(f"/api/applications/{self.sid}/turns",
                                           {"action": "end"}))
        # 结束动作零 LLM 调用、零面试官输出
        self.assertEqual(fake.chat_stream.call_count, calls_before_end)
        detail = self.client.get(f"/api/applications/{self.sid}").json()
        self.assertEqual(detail["status"], "finished")
        self.assertIsNotNone(detail["finished_at"])
        self.assertEqual(detail["turns"][-1]["role"], "system")  # 收尾是系统记录
        self.assertEqual(detail["turns"][-1]["meta"]["action"], "end")
        interviewer_turns = [t for t in detail["turns"] if t["role"] == "interviewer"]
        self.assertEqual(len(interviewer_turns), 1)  # 只有开场，没有告别

    def test_plan_stream_live_ticks_then_done(self):
        sid2 = self.client.post("/api/applications", {"job_id": self.job.id},
                                format="json").json()["id"]

        def fake_generate(llm, structured, **kwargs):
            on_tick = kwargs.get("on_tick")
            if on_tick:
                on_tick('{"phases": [{"question_pool": [{"id": "q1", "topic": "Redis 一致性"')
                on_tick('{"phases": [{"question_pool": [{"id": "q1", "topic": "Redis 一致性"}, '
                        '{"id": "q2", "topic": "TCP 三次握手"')
            return FAKE_PLAN

        with patch("apps.sessions.views.generate_plan", side_effect=fake_generate):
            resp = self.client.post(f"/api/applications/{sid2}/plan/stream")
        events = self._consume(resp)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "stage")
        self.assertIn("tick", kinds)
        self.assertEqual(kinds[-1], "done")
        ticks = [d for k, d in events if k == "tick"]
        self.assertIn("Redis 一致性", ticks[0])  # live reveal grows over ticks
        detail = self.client.get(f"/api/applications/{sid2}").json()
        self.assertTrue(detail["has_plan"])

    def test_plan_stream_reuses_existing_without_llm(self):
        with patch("apps.sessions.views.generate_plan") as mock:
            resp = self.client.post(f"/api/applications/{self.sid}/plan/stream")
        events = self._consume(resp)
        self.assertEqual([k for k, _ in events], ["done"])
        self.assertIn('"reused": true', events[0][1])
        self.assertEqual(mock.call_count, 0)

    def test_interrupt_stops_stream_and_persists_partial(self):
        """打断：生成中途停止，已流出部分落库（meta.interrupted），不再有告别。"""
        import time

        fake = MagicMock()
        fake.provider, fake.model = "mimo", "mimo-v2.6-flash"
        fake.chat.return_value = "摘要"

        def _stream(messages, **kwargs):
            def gen():
                for i in range(50):
                    yield f"第{i}段。"
                    time.sleep(0.05)
            return gen()

        fake.chat_stream.side_effect = _stream

        sid2 = self.client.post("/api/applications", {"job_id": self.job.id},
                                format="json").json()["id"]
        with patch("apps.sessions.views.generate_plan", return_value=FAKE_PLAN):
            self.client.post(f"/api/applications/{sid2}/plan")

        with patch("apps.sessions.views._llm_or_400",
                   return_value=(fake, "mimo-v2.6-flash", None)):
            resp = self.client.post(f"/api/applications/{sid2}/turns",
                                    {"action": "answer", "content": "我做过缓存网关"})
            it = resp.streaming_content
            frames = [next(it)]  # meta
            time.sleep(0.25)  # 让几段流出后再打断
            self.client.post(f"/api/applications/{sid2}/turns/cancel")
            frames += list(it)  # 排干到 done

        text = "".join(f.decode() if isinstance(f, bytes) else f for f in frames)
        self.assertIn('"interrupted": true', text)
        detail = self.client.get(f"/api/applications/{sid2}").json()
        last = detail["turns"][-1]
        self.assertEqual(last["role"], "interviewer")
        self.assertTrue(last["meta"].get("interrupted"))
        self.assertIn("第", last["content"])  # 已流出的部分保留
        self.assertLess(last["content"].count("段。"), 50)  # 但没有跑完全部生成


class ReviewTests(SessionSetupMixin, APITestCase):
    """面试后复盘：维度评估 + 逐题复盘，幂等生成（Phase 5 汇入 FinalReport）。"""

    FAKE_REVIEW = {
        "dimensions": {"基础知识": 72, "项目深度": 65, "沟通表达": 80, "岗位匹配": 70},
        "overall": "基础扎实但项目指标口径不清",
        "hire_impression": "待定",
        "highlights": ["提到缓存网关的 QPS 10k"],
        "weaknesses": ["QPS 口径未说清"],
        "per_question": [{"question": "自我介绍", "answer_summary": "三年后端",
                          "evaluation": "过短", "score": 2}],
        "advice": ["准备指标口径"],
    }

    def setUp(self):
        self._setup()
        sid = self.client.post("/api/applications", {"job_id": self.job.id},
                               format="json").json()["id"]
        with patch("apps.sessions.views.generate_plan", return_value=FAKE_PLAN):
            self.client.post(f"/api/applications/{sid}/plan")
        from apps.sessions.models import ApplicationSession, InterviewTurn

        session = ApplicationSession.objects.get(pk=sid)
        InterviewTurn.objects.create(application=session, seq=1, role="interviewer",
                                     content="介绍下自己")
        InterviewTurn.objects.create(application=session, seq=2, role="candidate",
                                     content="三年后端，做过缓存网关")
        session.last_turn_seq = 2
        session.save()
        self.sid = sid

    def test_review_generation_idempotent(self):
        with patch("apps.sessions.interview.generate_review",
                   return_value=dict(self.FAKE_REVIEW)) as mock:
            resp = self.client.post(f"/api/applications/{self.sid}/review")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertFalse(body["reused"])
        self.assertEqual(body["review"]["dimensions"]["基础知识"], 72)
        self.assertIn("model_name", body["review"])

        with patch("apps.sessions.interview.generate_review") as mock2:
            resp = self.client.post(f"/api/applications/{self.sid}/review")
        self.assertTrue(resp.json()["reused"])
        self.assertEqual(mock2.call_count, 0)

        with patch("apps.sessions.interview.generate_review",
                   return_value=dict(self.FAKE_REVIEW)):
            resp = self.client.post(f"/api/applications/{self.sid}/review",
                                    {"force": True}, format="json")
        self.assertFalse(resp.json()["reused"])

    def test_review_requires_turns(self):
        sid2 = self.client.post("/api/applications", {"job_id": self.job.id},
                                format="json").json()["id"]
        resp = self.client.post(f"/api/applications/{sid2}/review")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validate_review_clamps(self):
        from apps.sessions.interview import _validate_review

        data = _validate_review({
            "dimensions": {"基础知识": 150, "项目深度": "x"},
            "per_question": [{"question": "q"}, {"noq": 1}],
            "hire_impression": "乱写"})
        self.assertEqual(data["dimensions"]["基础知识"], 100)
        self.assertEqual(data["dimensions"]["项目深度"], 0)
        self.assertEqual(data["hire_impression"], "待定")
        self.assertEqual(len(data["per_question"]), 1)


FAKE_QUIZ = {"questions": [
    {"id": "q1", "type": "single", "difficulty": 1, "stem": "HTTP 默认端口是？",
     "options": ["80", "443", "22", "3306"], "reference_answer": [0],
     "scoring_points": [], "knowledge_tag": "HTTP", "score_full": 10},
    {"id": "q2", "type": "multi", "difficulty": 3, "stem": "以下哪些是 NoSQL 数据库？",
     "options": ["MySQL", "Redis", "MongoDB", "PostgreSQL"], "reference_answer": [1, 2],
     "scoring_points": [], "knowledge_tag": "NoSQL", "score_full": 10},
    {"id": "q3", "type": "short_answer", "difficulty": 3, "stem": "缓存穿透怎么解决？",
     "options": [], "reference_answer": ["布隆过滤器或空值缓存"],
     "scoring_points": ["布隆过滤器", "空值缓存", "参数校验"],
     "knowledge_tag": "Redis", "score_full": 10},
]}


class QuizTests(SessionSetupMixin, APITestCase):
    """基础笔试：出题/防作弊/判卷/弱项联动（PLAN.md §5.3①）。"""

    def setUp(self):
        self._setup()
        self.sid = self.client.post("/api/applications", {"job_id": self.job.id},
                                    format="json").json()["id"]

    def test_quiz_generation_anticheat_and_idempotent(self):
        with patch("apps.sessions.exam.generate_quiz",
                   return_value=list(FAKE_QUIZ["questions"])) as mock:
            resp = self.client.post(f"/api/applications/{self.sid}/quiz")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertFalse(body["reused"])
        self.assertEqual(len(body["questions"]), 3)
        self.assertNotIn("reference_answer", body["questions"][0])  # 防作弊
        self.assertNotIn("scoring_points", body["questions"][2])

        with patch("apps.sessions.exam.generate_quiz") as mock2:
            resp = self.client.post(f"/api/applications/{self.sid}/quiz")
        self.assertTrue(resp.json()["reused"])
        self.assertEqual(mock2.call_count, 0)

    def test_quiz_submit_grading_and_weak_linkage(self):
        with patch("apps.sessions.exam.generate_quiz",
                   return_value=list(FAKE_QUIZ["questions"])):
            self.client.post(f"/api/applications/{self.sid}/quiz")
        questions = self.client.get(f"/api/applications/{self.sid}/quiz").json()["questions"]
        qids = {q["seq"]: q["id"] for q in questions}

        with patch("apps.sessions.exam.grade_short",
                   return_value=(4.0, {"reason": "要点只中一条"})):
            resp = self.client.post(
                f"/api/applications/{self.sid}/quiz/submit",
                {"answers": [
                    {"question_id": qids[1], "content": [0]},   # 单选对 10
                    {"question_id": qids[2], "content": [1]},   # 多选漏选 5
                    {"question_id": qids[3], "content": "用布隆过滤器"},  # 简答 4
                ]}, format="json")
        body = resp.json()
        self.assertEqual(body["total_full"], 30)
        self.assertEqual(body["total_score"], 19)
        # 错题考点汇入 quiz_weak（三段联动）
        self.assertEqual(sorted(body["quiz_weak"]), ["NoSQL", "Redis"])
        detail = self.client.get(f"/api/applications/{self.sid}").json()
        self.assertEqual(detail["interview_state"]["quiz_weak"], body["quiz_weak"])
        # 重考覆盖旧作答
        resp = self.client.post(f"/api/applications/{self.sid}/quiz/submit",
                                {"answers": [{"question_id": qids[1], "content": [0]}]},
                                format="json")
        self.assertEqual(resp.json()["total_score"], 10)

    def test_grade_objective_rules(self):
        from apps.sessions.exam import grade_objective

        q = {"type": "single", "reference_answer": [0], "score_full": 10}
        self.assertEqual(grade_objective(q, [0])[0], 10.0)
        self.assertEqual(grade_objective(q, [1])[0], 0.0)
        qm = {"type": "multi", "reference_answer": [1, 2], "score_full": 10}
        self.assertEqual(grade_objective(qm, [1, 2])[0], 10.0)
        self.assertEqual(grade_objective(qm, [1])[0], 5.0)   # 漏选半分
        self.assertEqual(grade_objective(qm, [0, 1])[0], 0.0)  # 错选零分
        self.assertEqual(grade_objective(qm, "乱写")[0], 0.0)

    def test_validate_quiz_sorts_easy_to_hard(self):
        """用户要求：由简入深出题——服务端排序保证，不依赖模型自觉。"""
        from apps.sessions.exam import _validate_quiz

        mixed = [
            {**FAKE_QUIZ["questions"][0], "id": "h1", "difficulty": 5},
            {**FAKE_QUIZ["questions"][0], "id": "e1", "difficulty": 1},
            {**FAKE_QUIZ["questions"][1], "id": "m1", "difficulty": 3},
            {**FAKE_QUIZ["questions"][2], "id": "m2", "difficulty": 3},
            {**FAKE_QUIZ["questions"][0], "id": "e2", "difficulty": 2},
        ]
        questions = _validate_quiz({"questions": mixed})
        diffs = [q["difficulty"] for q in questions]
        self.assertEqual(diffs, sorted(diffs))  # 由简入深

    def test_validate_quiz_drops_bad_questions(self):
        from apps.sessions.exam import _validate_quiz

        questions = _validate_quiz({"questions": [
            dict(FAKE_QUIZ["questions"][0]),
            {"id": "bad1", "type": "single", "stem": "缺选项", "options": ["a"],
             "reference_answer": [0], "score_full": 10},
            {"id": "bad2", "type": "multi", "stem": "单答案多选救成单选", "options": ["a", "b"],
             "reference_answer": [0], "score_full": 10},
            *[{**FAKE_QUIZ["questions"][0], "id": f"ok{i}"} for i in range(3, 7)],
        ]})
        self.assertEqual(len(questions), 6)  # 缺选项的丢弃；题型/答案数不符的救题转换
        salvaged = [q for q in questions if q["id"] == "bad2"][0]
        self.assertEqual(salvaged["type"], "single")  # 多选只给 1 个答案 -> 就地转单选


FAKE_CODING = {"questions": [
    {"id": "c1", "stem": "实现一个固定窗口限流器", "function_signature": "def allow(key: str) -> bool",
     "examples": [{"input": "qps=1", "output": "True", "note": ""}],
     "constraints": "1<=qps<=1000", "language_hint": "python", "score_full": 50,
     "reference_solution": "def allow(key): ..."},
    {"id": "c2", "stem": "实现滑动窗口 QPS 统计", "function_signature": "def stat(events: list) -> int",
     "examples": [{"input": "[1,2]", "output": "3", "note": ""}],
     "constraints": "n<=1e5", "language_hint": "python", "score_full": 50,
     "reference_solution": "def stat(events): ..."},
]}

FAKE_JUDGE = {"correctness": {"score": 8, "comment": "思路正确"},
              "edge_cases": {"score": 6, "comment": "边界漏了空输入"},
              "complexity": {"score": 7, "comment": "O(n) 合理"},
              "style": {"score": 8, "comment": "命名清晰"},
              "summary": "整体不错", "improved_solution": "def allow(key): ..."}


class CodingTests(SessionSetupMixin, APITestCase):
    """代码笔试：出题/AI 四维评审（PLAN.md §5.3②）。"""

    def setUp(self):
        self._setup()
        self.sid = self.client.post("/api/applications", {"job_id": self.job.id},
                                    format="json").json()["id"]

    def test_coding_generation_hides_reference_and_idempotent(self):
        with patch("apps.sessions.coding.generate_coding",
                   return_value=list(FAKE_CODING["questions"])):
            resp = self.client.post(f"/api/applications/{self.sid}/coding")
        body = resp.json()
        self.assertFalse(body["reused"])
        self.assertEqual(len(body["questions"]), 2)
        self.assertNotIn("reference_solution", body["questions"][0])  # 防作弊

        with patch("apps.sessions.coding.generate_coding") as mock2:
            resp = self.client.post(f"/api/applications/{self.sid}/coding")
        self.assertTrue(resp.json()["reused"])
        self.assertEqual(mock2.call_count, 0)

    def test_coding_submit_review_and_unanswered(self):
        with patch("apps.sessions.coding.generate_coding",
                   return_value=list(FAKE_CODING["questions"])):
            self.client.post(f"/api/applications/{self.sid}/coding")
        questions = self.client.get(f"/api/applications/{self.sid}/coding").json()["questions"]
        qids = {q["seq"]: q["id"] for q in questions}

        with patch("apps.sessions.coding.review_code",
                   return_value=(32.5, dict(FAKE_JUDGE))) as mock:
            resp = self.client.post(
                f"/api/applications/{self.sid}/coding/submit",
                {"answers": [
                    {"question_id": qids[1], "code": "def allow(key): return True",
                     "language": "python"},
                    {"question_id": qids[2], "code": ""},  # 未作答
                ]}, format="json")
        body = resp.json()
        self.assertEqual(body["total_full"], 100)
        self.assertEqual(body["total_score"], 32.5)
        self.assertEqual(mock.call_count, 1)  # 未作答的不送评审
        answered = body["questions"][0]["my_answer"]
        self.assertEqual(answered["judge"]["correctness"]["score"], 8)
        self.assertIn("improved_solution", answered["judge"])
        self.assertEqual(body["questions"][1]["my_answer"]["score"], 0)

    def test_coding_review_validation_clamps(self):
        from apps.sessions.coding import _validate_review

        judge = _validate_review({"correctness": {"score": 15},
                                  "edge_cases": {"score": "x"},
                                  "complexity": {"score": 7, "comment": "ok"}})
        self.assertEqual(judge["correctness"]["score"], 10)
        self.assertEqual(judge["edge_cases"]["score"], 0)
        self.assertEqual(judge["complexity"]["score"], 7)
        self.assertEqual(judge["style"]["score"], 0)
