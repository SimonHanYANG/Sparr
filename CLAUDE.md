# CLAUDE.md — Sparr

本文件是 Claude Code 在本仓库工作的持久约定。**`PLAN.md` 是需求与架构的唯一事实来源（活文档）**，与本文件冲突时以 PLAN.md 的需求描述为准、以本文件的协作约定为准。

## 每次对话开始

1. **开口第一句先称呼用户为「涵哥」**。
2. 先读 `PLAN.md` 的 **「§12.3 开发进度」** 了解当前进度和下一步该做什么。
   - **不要**为了弄清"干到哪了"去通读全部代码或重读整份 PLAN.md——进度表就是入口；
   - 只有在执行具体改动时，才读相关的局部代码/章节。
3. 如果上次会话中断且进度未更新，对照 git log（`develop`/`feature/*` 最近提交）核实实际完成情况，补更新进度表后再开工。

## 开发中（进度与推送）

- 每完成一个有意义的增量（可运行的功能/修复/文档）：
  1. **立即更新 `PLAN.md` §12.3 开发进度**：勾选项、写一行完成日期与 commit 短号、记录遗留问题；
  2. **及时 `git push`** 当前 `feature/*` 或 `develop` 分支（无需询问，用户已授权）。
- 进度表是会话之间的交接棒：宁可多更新一次，也不要把状态只留在对话里。

## Git 工作流（详见 PLAN.md §12，铁律）

- 远程：`git@github.com:SimonHanYANG/Sparr.git`。
- `main` **只进发布版本**（按 Phase 打 tag v0.1~v0.6 → v1.0）。**每次合并/推送 main 之前必须先征得涵哥同意，获准后才执行**——这是硬性规则，没有任何例外。
- `develop` 集成分支、`feature/*` 功能分支：完成增量即推送，不需要逐次询问。
- 提交信息用 Conventional Commits（`feat:` `fix:` `docs:` `chore:`…），末尾附：
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## README.md

- 仓库根目录维护 `README.md`，与功能同步更新（功能介绍、技术栈、快速开始、部署方式、项目进度）。
- 新增用户可见功能或改变部署/启动方式时，检查 README 是否需要同步修改。

## UI 自查（强制，写完 UI 必做）

- 写完任何 UI 页面/组件后，**必须自己截图检查**，不许只靠代码推断效果：
  1. 启动前端（或用 `python -m http.server` 托管构建产物），用 **Playwright 无头浏览器截图**（如 `npx playwright screenshot`）；
  2. 至少截三个宽度：**390px（手机）、768px（iPad）、1280px（电脑）**；关键页面（面试间、简历展示、报告）还要截长页面全图；
  3. 用 Read 工具打开截图逐张检查：排版错位、文字溢出、间距不均、对比度、对齐、移动端可点性；
  4. 发现问题**立即修复并重新截图确认**，在进度表里记录"UI 自查完成"。
- 设计规范见 PLAN.md §7：简约克制（DeepSeek/Apple 风）、黑白灰+单一强调色、移动优先、中英双语、拒绝 AI 味渐变/发光/机器人图标。

## 技术栈速查

- 后端：Django 5 + DRF + SimpleJWT，SSE 流式，Celery/Redis（`TASK_MODE=celery|lite` 可切换），PostgreSQL/SQLite
- **Python 包管理一律用 uv**（`pyproject.toml` + `uv.lock`，`uv add`/`uv run`；不用 pip/poetry/conda 直接装包）
- 前端：React 18 + TS + Vite + TailwindCSS（移动优先）+ react-i18next（zh-CN/en）+ Zustand + TanStack Query + CodeMirror 6
- LLM：OpenAI 兼容适配层（用户自带 Key：DeepSeek v4 / MiMo 2.5/2.6）；MinerU 解析简历（用户自带 Key）
- 部署友好约定（配置化、存储/队列抽象）见 PLAN.md §11.0，写代码时必须遵守，不许硬编码配置

## 核心优先级（做取舍时的依据）

1. **模拟面试的智能性（不机械）是产品生命线**（PLAN.md §5.3③-A 六机制 + 验收标准）；
2. 模拟应聘整体（三段式）是核心功能，其余功能为其服务；
3. 任何简化都不得以牺牲面试智能性为代价。
