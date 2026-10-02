"""Profiling engine tests — the 'must be accurate' guarantee (PLAN.md §5.2).

Standard resume samples per direction with expected top recommendation.
If engine weights are tuned, these MUST keep passing (regression gate).
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.jobs.management.commands.seed_jobs import JOBS
from apps.jobs.models import JobPosition
from apps.resumes.models import Resume, ResumeVersion

from .engine import compute_portrait, experience_level, normalize_skills, recommend, tag_projects


def seed_jobs():
    for spec in JOBS:
        JobPosition.objects.update_or_create(
            category=spec["category"], title=spec["title"], level=spec["level"],
            defaults={k: spec[k] for k in
                      ("description", "skill_requirements", "affinity_tags",
                       "knowledge_points", "coding_topics", "interview_focus")},
        )


# --- standard resume samples (structured extraction output shape) -------------

def sample_backend():
    return {
        "basics": {"name": "张后端", "intent_role": "后端开发", "contact": "x@y.z", "years_exp": "3 年"},
        "education": [{"school": "某大学", "degree": "本科", "major": "CS", "period": "", "desc": ""}],
        "skills": [
            {"name": "编程语言", "level": "熟练", "desc": "Python、Java、Go"},
            {"name": "后端框架", "level": "熟练", "desc": "Django、Spring Boot"},
            {"name": "数据存储", "level": "熟练", "desc": "MySQL、Redis、消息队列 Kafka"},
            {"name": "计算机基础", "level": "熟练", "desc": "计算机网络、操作系统、Linux"},
        ],
        "projects": [
            {"name": "高并发订单系统", "role": "后端开发", "period": "2022.01 - 2022.06",
             "tech_stack": ["Django", "Redis", "Kafka"],
             "bullets": ["设计幂等下单接口，支撑秒杀峰值流量", "分库分表改造订单库"],
             "metrics": ["QPS 3000"]},
        ],
        "work_experiences": [{"company": "某互联网公司", "role": "后端工程师", "period": "2020 - 至今",
                              "bullets": ["负责用户中心与鉴权服务"]}],
        "awards": [],
    }


def sample_algorithm():
    return {
        "basics": {"name": "李算法", "intent_role": "算法工程师", "contact": "x@y.z", "years_exp": "应届"},
        "education": [{"school": "某大学", "degree": "硕士", "major": "AI", "period": "", "desc": ""}],
        "skills": [
            {"name": "机器学习", "level": "熟练", "desc": "深度学习、强化学习、PyTorch"},
            {"name": "大模型", "level": "熟悉", "desc": "Transformer、LLM、多模态、VLA"},
            {"name": "编程", "level": "熟练", "desc": "Python、C++"},
        ],
        "projects": [
            {"name": "机器人视觉感知系统", "role": "算法研究", "period": "2023.01 - 2024.01",
             "tech_stack": ["PyTorch", "3D Gaussian Splatting"],
             "bullets": ["3D 重建与深度估计", "具身机器人抓取策略，Sim-to-Real 迁移"],
             "metrics": ["CVPR 论文一篇"]},
        ],
        "work_experiences": [],
        "awards": ["国家奖学金"],
    }


def sample_product():
    return {
        "basics": {"name": "王产品", "intent_role": "产品经理", "contact": "x@y.z", "years_exp": "2 年"},
        "education": [{"school": "某大学", "degree": "本科", "major": "信息管理", "period": "", "desc": ""}],
        "skills": [
            {"name": "产品能力", "level": "熟练", "desc": "需求分析、产品设计、PRD 文档、原型设计"},
            {"name": "数据能力", "level": "熟悉", "desc": "数据分析、指标体系、竞品分析、用户研究"},
        ],
        "projects": [
            {"name": "增长活动产品设计", "role": "产品经理", "period": "2022.03 - 2022.09",
             "tech_stack": [],
             "bullets": ["主导拉新裂变活动需求分析与 PRD", "搭建数据看板与埋点指标体系", "推动跨部门协作上线"],
             "metrics": ["DAU 提升 15%"]},
        ],
        "work_experiences": [{"company": "某公司", "role": "产品经理", "period": "2021 - 至今",
                              "bullets": ["负责用户增长方向，用户调研与可用性测试"]}],
        "awards": [],
    }


def sample_frontend():
    return {
        "basics": {"name": "赵前端", "intent_role": "前端开发", "contact": "x@y.z", "years_exp": "3 年"},
        "education": [{"school": "某大学", "degree": "本科", "major": "软件工程", "period": "", "desc": ""}],
        "skills": [
            {"name": "前端技术", "level": "熟练", "desc": "JavaScript、TypeScript、React、Vue"},
            {"name": "基础与工程", "level": "熟练", "desc": "CSS、浏览器渲染原理、Webpack、Vite 工程化"},
        ],
        "projects": [
            {"name": "数据可视化组件库", "role": "前端负责人", "period": "2022.01 - 2023.01",
             "tech_stack": ["React", "TypeScript", "ECharts"],
             "bullets": ["封装 30+ 可视化组件", "首屏渲染性能优化，FCP 降低 40%", "小程序与 H5 多端适配"],
             "metrics": ["FCP 降低 40%"]},
        ],
        "work_experiences": [{"company": "某公司", "role": "前端工程师", "period": "2020 - 至今",
                              "bullets": ["主导组件库与前端工程化建设"]}],
        "awards": [],
    }


class EngineUnitTests(TestCase):
    def test_normalize_skills_handles_aliases(self):
        vector = normalize_skills([
            {"name": "编程", "level": "熟练", "desc": "PyTorch、React.js、计算机视觉"},
        ])
        self.assertIn("pytorch", vector)
        self.assertIn("react", vector)
        self.assertIn("cv", vector)
        self.assertGreaterEqual(vector["pytorch"], 2.0)

    def test_tag_projects_matches_keywords(self):
        tags = tag_projects(
            [{"name": "秒杀系统", "bullets": ["限流降级，QPS 峰值"], "tech_stack": []}], [])
        self.assertIn("高并发", tags)

    def test_experience_level(self):
        self.assertEqual(experience_level({"years_exp": "应届"}), "校招")
        self.assertEqual(experience_level({"years_exp": "3 年"}), "社招")
        self.assertEqual(experience_level({"years_exp": ""}), "校招")


class RecommendationRegressionTests(TestCase):
    """Standard samples must land their own direction at rank 1."""

    @classmethod
    def setUpTestData(cls):
        seed_jobs()

    def _top_category(self, structured):
        portrait = compute_portrait(structured)
        jobs = list(JobPosition.objects.filter(is_active=True))
        recs = recommend(jobs, portrait, top_n=12)
        best: dict[str, float] = {}
        for r in recs:
            best[r["job"].category] = max(best.get(r["job"].category, 0), r["score"])
        return max(best, key=best.get), recs[0]

    def test_backend_resume_recommends_backend(self):
        top_cat, first = self._top_category(sample_backend())
        self.assertEqual(top_cat, "后端")
        self.assertEqual(first["job"].category, "后端")
        self.assertTrue(first["reasons"])

    def test_algorithm_resume_recommends_algorithm(self):
        top_cat, first = self._top_category(sample_algorithm())
        self.assertEqual(top_cat, "算法")
        self.assertEqual(first["job"].category, "算法")

    def test_product_resume_recommends_product(self):
        top_cat, first = self._top_category(sample_product())
        self.assertEqual(top_cat, "产品")
        self.assertEqual(first["job"].category, "产品")

    def test_frontend_resume_recommends_frontend(self):
        top_cat, first = self._top_category(sample_frontend())
        self.assertEqual(top_cat, "前端")
        self.assertEqual(first["job"].category, "前端")


class ProfilingApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        seed_jobs()

    def setUp(self):
        self.user = User.objects.create_user("p1", password="pw12345678")
        self.client.force_authenticate(self.user)
        self.resume = Resume.objects.create(
            user=self.user, title="测试", source_path="x", source_filename="x.pdf",
            parse_status="parsed")
        self.version = ResumeVersion.objects.create(
            resume=self.resume, version_no=1, structured_json=sample_backend())
        self.resume.current_version = self.version
        self.resume.save()

    def test_compute_and_fetch(self):
        resp = self.client.post("/api/profiling/compute", {"resume_id": self.resume.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["portrait"]["experience_level"], "社招")
        self.assertEqual(body["recommendations"][0]["job"]["category"], "后端")
        self.assertIn("direction_scores", body["portrait"])

        resp = self.client.get(f"/api/profiling/portrait?resume_id={self.resume.pk}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_jobs_list_filter(self):
        resp = self.client.get("/api/jobs?category=算法")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(j["category"] == "算法" for j in resp.json()))
        self.assertGreater(len(resp.json()), 0)
