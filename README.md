# Sparr

> **Sparr** /spɑːr/ — *sparring partner*：正式上场前，陪你把每一招练熟。
>
> AI 模拟应聘平台：解析简历 → 画像与岗位推荐 → 三段式模拟应聘（基础笔试 · 代码笔试 · **智能面试问答**）→ 综合总结与简历优化。
>
> Your sparring partner before the real interview — resume parsing, job matching, and lifelike AI mock interviews.

---

## 为什么是 Sparr

- **面试官不机械**（产品生命线）：因人出题、隐藏评估驱动追问、引用你的原话深挖、动态调整节奏——像真实大厂面试官，而不是念题机器人。
- **一场完整的模拟应聘**：选择/简答基础笔试 → 代码笔试（AI 评审）→ 面试问答，三段互相联动（笔试弱项会被面试官"恰好"问到），最后给出综合录用建议等级。
- **面试可以续上**：中断后再次登录无缝继续，面试官记得聊过的每一句、埋过的每条线索，不重新分析简历。
- **改简历的依据来自真实追问**：逐条 diff 式简历修改建议（"这个指标没写来源，面试必被追问"），形成"面试 → 改简历 → 再面试"的成长闭环。
- **多端自适应 + 中英双语**：手机 / iPad / 电脑全适配；界面中英一键切换，面试与报告输出语言跟随界面语言（可英文模拟外企面试）。
- **自带 Key，零平台成本**：接入你自己的 DeepSeek / 小米 MiMo API-Key 与 MinerU Key，加密存储。

## 功能

| 模块 | 说明 |
|---|---|
| 简历 | PDF 上传 → MinerU 解析 → 结构化抽取 → 卡片式展示 / 编辑 / 版本历史 |
| 画像与岗位 | 2026 热招岗位库（VLA/具身智能、Agent/RAG、预训练/后训练…）+ 规则画像快速信号 + **LLM 匹配评估**（评分/待补强逐条锚定 JD 原文，支持任意粘贴 JD）；主线四步流式引导 |
| 备考工作台 | 岗位卡显示我的匹配度 · 考点自查（掌握/模糊/不会，**薄弱项喂给面试官**）· 目标岗位星标 · 一键针对该岗模拟应聘 |
| 模拟应聘 ★ | 三段式：基础笔试（选择/简答）· 代码笔试（AI review 四维判卷）· 智能面试问答（流式、可打断、自适应追问、断点续面） |
| 总结 | 五维雷达 + 录用建议等级（强推/推荐/待定/不推荐）+ 逐题复盘时间轴 + 简历修改建议 |

## 技术栈

- **后端**：Django 5 · Django REST Framework · SimpleJWT · SSE 流式 · Celery/Redis（可切换 lite 模式）· PostgreSQL/SQLite
- **前端**：React 18 · TypeScript · Vite · TailwindCSS（移动优先）· react-i18next（zh-CN/en）· Zustand · TanStack Query · CodeMirror 6
- **AI**：OpenAI 兼容适配层（DeepSeek v4 系列 / 小米 MiMo 2.5/2.6，用户自带 API-Key）· MinerU（简历解析）
- **部署**：本地 Docker Compose 完整版 / 免费云端版（Cloudflare Pages + Render + Neon，$0 运行）

## 快速开始

```bash
# 开发环境（Docker）
git clone git@github.com:SimonHanYANG/Sparr.git
cd Sparr
cp .env.example .env          # 填写数据库等配置
docker compose -f docker-compose.dev.yml up

# 初始化
make init                     # 迁移 + 岗位库种子数据 + 超管账号
```

前后端分离开发：后端 `http://localhost:8000`，前端 `http://localhost:5173`。

> 详细部署（本地完整版 / 免费云端版）见 `docs/deploy-local.md` 与 `docs/deploy-free-cloud.md`。

## 配置

| 环境变量 | 说明 |
|---|---|
| `TASK_MODE` | `celery`（完整）/ `lite`（免 Redis，同进程线程池）|
| `STORAGE` | `local` / `s3` / `db`（简历 PDF 存数据库，适配免费云临时盘）|
| LLM / MinerU Key | 用户在「设置」页自行填入，Fernet 加密存储，永不回读 |

## 项目结构

```
backend/    Django 后端（apps: accounts / resumes / profiling / jobs / sessions / reports）
frontend/   React 前端
docs/       部署文档
PLAN.md     需求与架构（唯一事实来源，含开发进度表）
CLAUDE.md   开发协作约定
```

## 路线图

详见 [PLAN.md §12.3 开发进度](./PLAN.md)。发布按里程碑打 tag（v0.x → v1.0）。

## License

TBD
