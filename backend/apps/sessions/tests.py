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
