"""Skill synonym taxonomy + project-tag keywords.

The normalization backbone of the rule engine (PLAN.md §5.2):
skill names from resumes come in messy forms ("PyTorch 框架", "React.js"),
and everything must map to canonical keys shared with JobPosition
skill_requirements. Deterministic, auditable — no LLM.
"""

# canonical skill -> alias fragments (lowercase; match if token contains alias
# or alias contains token, min token length 2)
SYNONYMS: dict[str, list[str]] = {
    # languages
    "python": ["python", "py"],
    "java": ["java"],
    "golang": ["golang", "go 语言", "go语言"],
    "javascript": ["javascript", "js", "ecmascript"],
    "typescript": ["typescript", "ts"],
    "c++": ["c++", "cpp"],
    "sql": ["sql"],
    "shell": ["shell", "bash"],
    # backend
    "django": ["django"],
    "flask": ["flask"],
    "spring": ["spring"],
    "mysql": ["mysql"],
    "postgresql": ["postgresql", "postgres"],
    "redis": ["redis"],
    "mongodb": ["mongodb", "mongo"],
    "kafka": ["kafka"],
    "rabbitmq": ["rabbitmq"],
    "消息队列": ["消息队列", "message queue", "rabbitmq", "kafka", "rocketmq", "mq"],
    "分布式": ["分布式", "distributed"],
    "高并发": ["高并发", "高吞吐", "high concurrency"],
    "微服务": ["微服务", "microservice"],
    "linux": ["linux"],
    "docker": ["docker", "容器"],
    "kubernetes": ["kubernetes", "k8s"],
    "git": ["git"],
    "计算机网络": ["计算机网络", "tcp", "http", "网络协议", "计算机通讯"],
    "操作系统": ["操作系统", "进程", "线程", "内存管理"],
    # frontend
    "react": ["react"],
    "vue": ["vue"],
    "css": ["css", "tailwind", "sass", "less"],
    "浏览器原理": ["浏览器", "渲染原理", "v8", "事件循环"],
    "工程化": ["工程化", "webpack", "vite", "rollup", "构建工具", "脚手架"],
    # ai/ml
    "机器学习": ["机器学习", "machine learning", "ml", "sklearn", "scikit"],
    "深度学习": ["深度学习", "deep learning", "神经网络", "cnn", "rnn", "lstm"],
    "强化学习": ["强化学习", "reinforcement", "rl", "sim-to-real", "模仿学习"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "keras"],
    "nlp": ["nlp", "自然语言", "文本分类", "大语言"],
    "cv": ["计算机视觉", "computer vision", "视觉感知", "图像处理", "图像分割", "目标检测", "3d视觉", "三维重建", "nerf", "深度估计"],
    "transformer": ["transformer", "attention", "注意力", "bert", "gpt", "diffusion", "flow matching"],
    "llm": ["llm", "大模型", "大语言模型", "多模态", "预训练", "微调", "sft", "rlhf"],
    "vla": ["vla", "具身智能", "具身", "机器人操作", "操作策略", "模仿学习"],
    "rag": ["rag", "检索增强", "向量数据库", "embedding", "知识库问答"],
    "智能体": ["agent", "智能体", "agentic", "工具调用", "function calling", "prompt工程", "提示词"],
    "推理优化": ["推理加速", "推理优化", "tensorrt", "vllm", "量化", "显存优化", "kv cache", "trt", "onnx"],
    "推荐算法": ["推荐算法", "推荐系统", "召回排序", "ctr", "点击率预估", "精排"],
    "自动驾驶": ["自动驾驶", "智能驾驶", "感知算法", "occupancy", "点云感知", "slam"],
    # data
    "spark": ["spark"],
    "flink": ["flink"],
    "数仓": ["数仓", "数据仓库", "data warehouse", "hive", "维度建模"],
    "etl": ["etl", "数据管道", "数据清洗"],
    "数据分析": ["数据分析", "data analysis", "指标体系", "bi"],
    # product
    "需求分析": ["需求分析", "需求梳理", "需求拆解"],
    "产品设计": ["产品设计", "prd", "原型", "axure", "交互设计"],
    "竞品分析": ["竞品", "竞品分析"],
    "用户研究": ["用户研究", "用户调研", "用户访谈", "问卷"],
    "文档能力": ["文档", "写作", "prd撰写"],
    # qa / infra
    "测试": ["测试", "testing", "qa", "用例设计"],
    "自动化测试": ["自动化测试", "selenium", "pytest", "appium", "接口测试", "ui自动化"],
    "ci/cd": ["ci/cd", "cicd", "持续集成", "jenkins", "github actions", "发布流程"],
    "监控告警": ["监控", "告警", "prometheus", "grafana"],
}

# project-tag keywords: matched against project/work names + bullets
TAG_KEYWORDS: dict[str, list[str]] = {
    "高并发": ["高并发", "qps", "吞吐", "限流", "秒杀", "峰值"],
    "分布式": ["分布式", "微服务", "分库分表", "集群", "一致性", "rpc"],
    "微服务": ["微服务", "服务拆分", "grpc", "rpc", "服务治理"],
    "订单系统": ["订单", "交易", "支付", "履约"],
    "用户中心": ["用户中心", "账号", "登录", "鉴权", "权限", "用户系统"],
    "API 设计": ["接口", "api", "restful", "网关"],
    "性能优化": ["性能", "优化", "调优", "延迟", "加速", "省电", "轻量"],
    "架构设计": ["架构", "重构", "技术选型", "框架设计"],
    "CRUD": ["crud", "管理系统", "后台", "表单"],
    "数据管道": ["数据管道", "etl", "数据同步", "爬虫", "数据采集", "pipeline"],
    "组件库": ["组件", "组件库", "ui库", "封装"],
    "可视化": ["可视化", "图表", "大屏", "echarts", "渲染"],
    "小程序": ["小程序", "微信", "uniapp"],
    "H5": ["h5", "移动端", "响应式"],
    "交互体验": ["交互", "体验", "动效", "无障碍", "设计系统"],
    "大模型": ["大模型", "llm", "智能体", "agent", "rag", "vla", "多模态", "gpt", "bert", "diffusion"],
    "视觉感知": ["视觉", "3d", "nerf", "高斯", "深度", "重建", "标定", "点云", "图像"],
    "推荐系统": ["推荐", "召回", "排序", "点击率", "ctr"],
    "医学图像": ["医学", "医疗", "生殖", "影像", "分割", "诊断"],
    "机器人": ["机器人", "robot", "抓取", "机械臂", "具身", "导航", "ros", "slam"],
    "论文/竞赛": ["论文", "竞赛", "比赛", "发表", "专利", "顶会", "cvpr", "iccv", "neurips", "sigir"],
    "落地应用": ["落地", "部署", "上线", "生产环境", "tensorrt", "推理加速", "量化"],
    "多模态": ["多模态", "图文", "视频理解", "语音"],
    "需求文档": ["需求文档", "prd", "需求", "方案文档"],
    "用户研究": ["用户调研", "用户访谈", "问卷", "可用性测试", "用户画像"],
    "增长": ["增长", "留存", "转化", "裂变", "拉新", "活跃"],
    "商业化": ["商业化", "变现", "付费", "营收", "广告"],
    "产品设计": ["产品设计", "原型", "功能设计", "信息架构", "交互方案"],
    "数据分析": ["数据看板", "指标", "埋点", "ab实验", "漏斗", "归因"],
    "项目推动": ["推动", "跨部门", "协作", "上线", "迭代", "评审"],
    "数仓建设": ["数仓", "数据仓库", "分层", "建模", "维度"],
    "指标体系": ["指标体系", "口径", "看板"],
    "ETL": ["etl", "调度", "airflow", "数据同步"],
    "自动化测试": ["自动化", "selenium", "pytest", "接口测试", "ui 自动化", "ui自动化"],
    "测试工具": ["测试工具", "平台", "脚手架", "造数"],
    "质量体系": ["质量", "用例", "缺陷", "回归", "覆盖率"],
    "CI/CD": ["ci/cd", "cicd", "流水线", "jenkins", "github actions", "持续集成"],
    "稳定性建设": ["稳定性", "高可用", "容灾", "故障", "sla", "降级"],
    "监控告警": ["监控", "告警", "prometheus", "grafana", "可观测"],
    "自动化运维": ["自动化", "脚本", "批量", "运维平台"],
}

# proficiency label -> normalized score (0..3)
LEVEL_SCORES = {"精通": 3.0, "熟练": 2.5, "熟悉": 2.0, "掌握": 2.0, "了解": 1.0}
DEFAULT_LEVEL_SCORE = 2.0
