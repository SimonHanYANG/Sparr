"""Seed the shared job catalog (PLAN.md §5.2) — idempotent upsert by (category, title, level)."""
from django.core.management.base import BaseCommand

from apps.jobs.models import JobPosition

# skill names are canonical taxonomy keys (see apps/profiling/taxonomy.py)
JOBS = [
    # ================= 后端 =================
    {
        "category": "后端", "title": "后端开发工程师", "level": "校招",
        "description": "负责服务端核心链路开发，保障高可用与性能。",
        "skill_requirements": [
            {"skill": "python", "weight": 5, "required": False},
            {"skill": "java", "weight": 5, "required": False},
            {"skill": "golang", "weight": 3, "required": False},
            {"skill": "计算机网络", "weight": 5, "required": True},
            {"skill": "操作系统", "weight": 4, "required": True},
            {"skill": "mysql", "weight": 5, "required": True},
            {"skill": "redis", "weight": 4, "required": False},
            {"skill": "消息队列", "weight": 3, "required": False},
            {"skill": "linux", "weight": 3, "required": False},
            {"skill": "git", "weight": 2, "required": False},
        ],
        "affinity_tags": ["高并发", "分布式", "微服务", "用户中心", "订单系统", "API 设计"],
        "knowledge_points": ["TCP/HTTP 协议", "进程/线程/内存", "MySQL 索引与事务", "锁与并发",
                             "Redis 缓存与一致性", "消息队列", "分布式基础", "RESTful 设计"],
        "coding_topics": ["线程安全数据结构", "SQL 场景题", "接口幂等设计", "缓存穿透/雪崩方案"],
        "interview_focus": ["基础八股", "项目深挖", "场景设计", "追问数据指标"],
    },
    {
        "category": "后端", "title": "后端开发工程师", "level": "社招",
        "description": "主导复杂系统设计与演进，解决高并发高可用难题。",
        "skill_requirements": [
            {"skill": "java", "weight": 5, "required": False},
            {"skill": "golang", "weight": 4, "required": False},
            {"skill": "python", "weight": 4, "required": False},
            {"skill": "分布式", "weight": 5, "required": True},
            {"skill": "高并发", "weight": 5, "required": True},
            {"skill": "mysql", "weight": 5, "required": True},
            {"skill": "redis", "weight": 5, "required": True},
            {"skill": "消息队列", "weight": 4, "required": False},
            {"skill": "kubernetes", "weight": 3, "required": False},
            {"skill": "spring", "weight": 3, "required": False},
        ],
        "affinity_tags": ["高并发", "分布式", "微服务", "订单系统", "性能优化", "架构设计"],
        "knowledge_points": ["分布式事务与一致性", "分库分表", "高可用架构", "性能调优",
                             "缓存体系设计", "消息可靠投递", "容量规划"],
        "coding_topics": ["限流器实现", "分布式 ID 生成", "热点账户设计", "延迟队列设计"],
        "interview_focus": ["系统设计", "架构决策复盘", "故障处理经历", "技术视野"],
    },
    {
        "category": "后端", "title": "后端开发实习生", "level": "实习",
        "description": "参与服务端功能开发，配合完成接口与数据层工作。",
        "skill_requirements": [
            {"skill": "python", "weight": 4, "required": False},
            {"skill": "java", "weight": 4, "required": False},
            {"skill": "计算机网络", "weight": 4, "required": True},
            {"skill": "mysql", "weight": 4, "required": True},
            {"skill": "linux", "weight": 2, "required": False},
            {"skill": "git", "weight": 2, "required": False},
            {"skill": "django", "weight": 3, "required": False},
            {"skill": "spring", "weight": 3, "required": False},
        ],
        "affinity_tags": ["API 设计", "CRUD", "用户中心", "数据管道"],
        "knowledge_points": ["HTTP 基础", "SQL 基础", "一门后端框架", "Git 协作"],
        "coding_topics": ["简单 SQL", "接口设计", "字符串/数组题"],
        "interview_focus": ["基础扎实度", "学习能力", "项目真实性"],
    },
    # ================= 前端 =================
    {
        "category": "前端", "title": "前端开发工程师", "level": "校招",
        "description": "负责 Web/移动端界面开发与交互体验优化。",
        "skill_requirements": [
            {"skill": "javascript", "weight": 5, "required": True},
            {"skill": "typescript", "weight": 4, "required": False},
            {"skill": "react", "weight": 5, "required": False},
            {"skill": "vue", "weight": 5, "required": False},
            {"skill": "css", "weight": 4, "required": True},
            {"skill": "浏览器原理", "weight": 4, "required": True},
            {"skill": "工程化", "weight": 3, "required": False},
            {"skill": "git", "weight": 2, "required": False},
        ],
        "affinity_tags": ["组件库", "可视化", "小程序", "H5", "交互体验", "性能优化"],
        "knowledge_points": ["JS 事件循环与作用域", "CSS 布局与响应式", "浏览器渲染原理",
                             "框架状态管理", "前端性能优化", "工程化与构建"],
        "coding_topics": ["手写防抖/节流", "手写 Promise/深拷贝", "组件封装题", "布局实现题"],
        "interview_focus": ["JS 基础", "框架原理", "项目深挖（交互/性能）", "工程化实践"],
    },
    {
        "category": "前端", "title": "前端开发工程师", "level": "社招",
        "description": "主导前端架构与体验建设，解决复杂交互与性能问题。",
        "skill_requirements": [
            {"skill": "javascript", "weight": 5, "required": True},
            {"skill": "typescript", "weight": 5, "required": True},
            {"skill": "react", "weight": 5, "required": False},
            {"skill": "vue", "weight": 5, "required": False},
            {"skill": "工程化", "weight": 5, "required": True},
            {"skill": "浏览器原理", "weight": 4, "required": True},
            {"skill": "css", "weight": 4, "required": False},
        ],
        "affinity_tags": ["组件库", "可视化", "性能优化", "架构设计", "交互体验"],
        "knowledge_points": ["框架源码级理解", "渲染性能", "微前端", "构建优化", "监控与稳定性"],
        "coding_topics": ["虚拟列表实现", "框架状态管理设计", "首屏优化方案", "错误边界设计"],
        "interview_focus": ["架构能力", "性能攻坚经历", "工程化体系", "带人/推动经历"],
    },
    # ================= 算法 =================
    {
        "category": "算法", "title": "算法工程师（机器学习/深度学习）", "level": "校招",
        "description": "负责模型研发与落地，覆盖 CV/NLP/多模态等方向。",
        "skill_requirements": [
            {"skill": "python", "weight": 5, "required": True},
            {"skill": "机器学习", "weight": 5, "required": True},
            {"skill": "深度学习", "weight": 5, "required": True},
            {"skill": "pytorch", "weight": 4, "required": True},
            {"skill": "c++", "weight": 2, "required": False},
            {"skill": "nlp", "weight": 3, "required": False},
            {"skill": "cv", "weight": 3, "required": False},
            {"skill": "强化学习", "weight": 3, "required": False},
        ],
        "affinity_tags": ["大模型", "视觉感知", "推荐系统", "医学图像", "机器人", "论文/竞赛"],
        "knowledge_points": ["深度学习基础（CNN/RNN/Transformer）", "训练调参与正则化",
                             "损失函数与评估指标", "经典模型对比", "数据处理与增强", "数学基础"],
        "coding_topics": ["手写注意力机制", "数据加载与预处理", "模型训练脚本", "指标实现"],
        "interview_focus": ["论文/项目深挖", "模型选型理由", "实验设计", "复现能力"],
    },
    {
        "category": "算法", "title": "算法工程师（大模型/多模态）", "level": "社招",
        "description": "负责大模型训练/推理/应用落地，解决实际业务问题。",
        "skill_requirements": [
            {"skill": "python", "weight": 5, "required": True},
            {"skill": "深度学习", "weight": 5, "required": True},
            {"skill": "llm", "weight": 5, "required": True},
            {"skill": "transformer", "weight": 5, "required": True},
            {"skill": "pytorch", "weight": 4, "required": True},
            {"skill": "分布式", "weight": 3, "required": False},
            {"skill": "强化学习", "weight": 3, "required": False},
        ],
        "affinity_tags": ["大模型", "多模态", "视觉感知", "机器人", "论文/竞赛", "落地应用"],
        "knowledge_points": ["Transformer 全家桶", "预训练/微调/对齐", "推理加速与量化",
                             "RAG 与应用架构", "评测体系", "分布式训练"],
        "coding_topics": ["手写 KV Cache", "推理服务设计", "数据管道实现", "训练超参排查"],
        "interview_focus": ["大模型项目深挖", "落地效果与指标", "技术判断力", "论文/专利"],
    },
    # ================= 产品 =================
    {
        "category": "产品", "title": "产品经理", "level": "校招",
        "description": "负责需求洞察与产品设计，推动产品迭代落地。",
        "skill_requirements": [
            {"skill": "需求分析", "weight": 5, "required": True},
            {"skill": "产品设计", "weight": 5, "required": True},
            {"skill": "数据分析", "weight": 4, "required": True},
            {"skill": "竞品分析", "weight": 4, "required": False},
            {"skill": "用户研究", "weight": 3, "required": False},
            {"skill": "文档能力", "weight": 4, "required": False},
        ],
        "affinity_tags": ["需求文档", "用户研究", "增长", "产品设计", "数据分析", "项目推动"],
        "knowledge_points": ["需求分析方法", "产品设计流程", "数据指标体系", "竞品分析框架",
                             "用户体验原则", "项目推动与协作"],
        "coding_topics": ["需求拆解题（给场景出方案）", "指标设计题", "优先级排序题"],
        "interview_focus": ["产品 sense", "需求案例深挖", "数据驱动", "沟通与推动"],
    },
    {
        "category": "产品", "title": "高级产品经理", "level": "社招",
        "description": "主导产品线规划与增长，对业务结果负责。",
        "skill_requirements": [
            {"skill": "需求分析", "weight": 5, "required": True},
            {"skill": "产品设计", "weight": 5, "required": True},
            {"skill": "数据分析", "weight": 5, "required": True},
            {"skill": "用户研究", "weight": 4, "required": True},
            {"skill": "竞品分析", "weight": 4, "required": False},
        ],
        "affinity_tags": ["增长", "商业化", "项目推动", "数据分析", "产品设计"],
        "knowledge_points": ["产品战略与路线图", "增长模型", "商业化设计", "组织协作", "风险控制"],
        "coding_topics": ["从 0 到 1 方案题", "增长实验设计", "数据归因题"],
        "interview_focus": ["业务结果复盘", "决策过程", "带团队/跨部门推动", "行业洞察"],
    },
    # ================= 数据 =================
    {
        "category": "数据", "title": "数据开发工程师", "level": "校招",
        "description": "负责数据仓库与数据管道建设，支撑业务分析。",
        "skill_requirements": [
            {"skill": "sql", "weight": 5, "required": True},
            {"skill": "python", "weight": 4, "required": True},
            {"skill": "数仓", "weight": 4, "required": True},
            {"skill": "etl", "weight": 3, "required": False},
            {"skill": "spark", "weight": 3, "required": False},
            {"skill": "flink", "weight": 2, "required": False},
            {"skill": "linux", "weight": 2, "required": False},
        ],
        "affinity_tags": ["数据管道", "数仓建设", "数据分析", "ETL", "指标体系"],
        "knowledge_points": ["SQL 进阶（窗口函数）", "数仓分层与建模", "ETL 调度",
                             "数据质量治理", "Spark/Flink 基础"],
        "coding_topics": ["复杂 SQL 题", "指标口径设计", "数据倾斜排查"],
        "interview_focus": ["SQL 能力", "数仓设计", "数据质量意识", "项目深挖"],
    },
    # ================= 测试 =================
    {
        "category": "测试", "title": "测试开发工程师", "level": "校招",
        "description": "负责质量保障体系建设，开发测试工具与自动化能力。",
        "skill_requirements": [
            {"skill": "测试", "weight": 5, "required": True},
            {"skill": "自动化测试", "weight": 4, "required": True},
            {"skill": "python", "weight": 4, "required": False},
            {"skill": "java", "weight": 3, "required": False},
            {"skill": "计算机网络", "weight": 3, "required": False},
            {"skill": "ci/cd", "weight": 3, "required": False},
        ],
        "affinity_tags": ["自动化测试", "测试工具", "质量体系", "CI/CD"],
        "knowledge_points": ["测试用例设计", "自动化框架", "接口测试", "CI/CD 流水线", "缺陷管理"],
        "coding_topics": ["测试用例设计题", "自动化脚本编写", "接口测试方案"],
        "interview_focus": ["用例设计思维", "自动化实践", "质量意识", "工具开发"],
    },
    # ================= 运维 =================
    {
        "category": "运维", "title": "基础设施/运维开发工程师", "level": "校招",
        "description": "负责基础设施与稳定性建设，保障服务高可用。",
        "skill_requirements": [
            {"skill": "linux", "weight": 5, "required": True},
            {"skill": "docker", "weight": 4, "required": True},
            {"skill": "kubernetes", "weight": 3, "required": False},
            {"skill": "计算机网络", "weight": 4, "required": True},
            {"skill": "ci/cd", "weight": 3, "required": False},
            {"skill": "python", "weight": 3, "required": False},
        ],
        "affinity_tags": ["稳定性建设", "监控告警", "自动化运维", "CI/CD"],
        "knowledge_points": ["Linux 命令与排障", "容器与编排", "网络与 DNS/负载均衡",
                             "监控告警体系", "CI/CD 与发布"],
        "coding_topics": ["Shell/Python 脚本题", "故障排查思路", "发布回滚方案"],
        "interview_focus": ["排障能力", "自动化实践", "稳定性意识", "项目深挖"],
    },
]


class Command(BaseCommand):
    help = "Seed the shared job catalog (idempotent)"

    def handle(self, *args, **options):
        created = updated = 0
        for spec in JOBS:
            obj, was_created = JobPosition.objects.update_or_create(
                category=spec["category"], title=spec["title"], level=spec["level"],
                defaults={
                    "description": spec["description"],
                    "skill_requirements": spec["skill_requirements"],
                    "affinity_tags": spec["affinity_tags"],
                    "knowledge_points": spec["knowledge_points"],
                    "coding_topics": spec["coding_topics"],
                    "interview_focus": spec["interview_focus"],
                    "is_active": True,
                },
            )
            created += was_created
            updated += not was_created
        self.stdout.write(self.style.SUCCESS(
            f"job catalog ready: {created} created, {updated} updated, "
            f"{JobPosition.objects.count()} total"))
