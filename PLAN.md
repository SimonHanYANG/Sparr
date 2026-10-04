# Sparr — 项目计划书 v3

> **产品名：Sparr**（源自拳击术语 *sparring partner*，实战陪练——正式上场前陪你把每一招练熟）。
> 品牌口吻：面试前的陪练伙伴。Logo/视觉建议用简洁字标 + 护具/拳套意象的极简线性图标（Phase 6 定稿）。

> 一句话定位：解析简历 → 生成用户画像并推荐岗位 → 三段式模拟应聘（基础笔试 + 代码笔试 + 智能面试问答）→ 综合总结报告与改进建议。
>
> **核心原则一：模拟应聘（尤其面试问答环节）是绝对核心**，其余功能（简历解析、画像推荐、总结）都为它服务或由它驱动。
>
> **核心原则二：面试必须"智能、不机械"，这是产品的生命线**（详见 §5.3③-A 防机械设计）。面试官要像真实大厂面试官一样随答而变、深挖追问、因人出题——任何环节的简化都不得以牺牲这一点为代价。

---

## 1. 功能总览（本轮确认的四大功能）

| # | 功能 | 说明 |
|---|---|---|
| F1 | 简历解析、更改与展示 | PDF 上传 → MinerU 解析 → 结构化抽取 → 可视化展示 + 编辑（版本历史） |
| F2 | 用户画像评估 + 岗位推荐 | 基于简历的结构化数据生成画像，向用户推荐匹配岗位（**不用大模型打分**，见 §5.2 决策） |
| F3 | 模拟应聘（核心） | 用户选定岗位后进入三段式：<br>① 基础题笔试（选择/简答，考察岗位基础知识）<br>② 代码笔试（大模型检查判卷）<br>③ 模拟面试问答（仿真实大厂，智能追问） |
| F4 | 应聘总结 | 汇总三段表现 → 综合评估报告 + 简历修改建议 |

其他已确认决策：
- 前后端：React SPA + Django REST API；面试为纯文字流式（SSE）
- LLM：用户自带 API-Key（DeepSeek v4 系列、小米 MiMo 2.5/2.6 系列）
- 简历解析：MinerU（用户自带 API-Key）
- 用户体系：注册登录 + 完整历史
- UI：简约克制，参考 DeepSeek / 苹果官网（黑白灰 + 单一强调色、大留白、系统字体、无"AI 味"）
- **多端自适应**：手机 / iPad / 电脑 / 大屏全适配，移动优先
- **国际化**：中文 / English 一键切换，全站文案双语；**面试/笔试/报告输出语言跟随当前界面语言**（可英文面试）

---

## 2. 技术栈

### 后端
| 层 | 选型 | 理由 |
|---|---|---|
| 框架 | Django 5 + Django REST Framework | 指定 Django；DRF 提供规范 API |
| 流式输出 | SSE（`StreamingHttpResponse`） | 面试对话流式首选，比 WebSocket 简单够用 |
| 认证 | SimpleJWT（access + refresh） | SPA 标准方案 |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） | Django ORM 屏蔽差异 |
| 任务队列 | Celery + Redis（简历解析、组卷、生成报告等慢任务） | 开发期可用 eager 模式简化 |
| LLM 适配 | OpenAI 兼容协议统一封装（DeepSeek、MiMo） | 一套代码多 provider |
| API-Key 安全 | Fernet 加密落库，保存后永不回读明文 | 前端只显示掩码，仅服务端内存解密 |
| 简历解析 | MinerU 开放 API（用户 key） | PDF → Markdown |
| **画像/推荐** | **确定性规则引擎（纯 Python，不用 LLM）** | 见 §5.2 |

### 前端
| 层 | 选型 |
|---|---|
| 框架 | React 18 + TypeScript + Vite |
| 样式 | TailwindCSS（设计 token 化，移动优先断点） |
| i18n | react-i18next（zh-CN / en 双语包，语言持久化到 localStorage + 用户档案） |
| 状态 | Zustand + TanStack Query |
| 路由 | React Router v6 |
| 流式渲染 | fetch + ReadableStream 解析 SSE，`react-markdown` 渲染 |
| 代码编辑 | CodeMirror 6 |

---

## 3. 系统架构

```
┌────────────────────────────────┐
│   React SPA (Vite/TS/Tailwind) │
└───────────────┬────────────────┘
                │ REST (JSON) + SSE (流式)
┌───────────────▼────────────────┐
│   Django + DRF                 │
│  ├─ accounts    用户 / API-Key  │
│  ├─ resumes     简历解析/编辑    │
│  ├─ profiling   ★画像与岗位推荐  │（纯规则引擎）
│  ├─ jobs        岗位库（预置）   │
│  ├─ sessions    ★模拟应聘会话    │
│  │   ├─ 基础笔试 (quiz)         │
│  │   ├─ 代码笔试 (coding)       │
│  │   └─ 面试问答 (interview)    │
│  └─ reports     综合总结/简历优化│
├────────────────────────────────┤
│  LLM Adapter（OpenAI 兼容）──► DeepSeek v4 / MiMo（用户 key）
│  MinerU Client ──────────────► MinerU API（用户 key）
├────────────────────────────────┤
│  Celery + Redis │ PostgreSQL   │
└────────────────────────────────┘
```

---

## 4. 核心数据模型

```
User                        Django auth 扩展（nickname 等）

ProviderCredential          大模型/MinerU API-Key（每用户 × 每 provider）
├─ user, provider(deepseek|mimo|mineru), api_key_encrypted,
│  model_name, base_url(可选), is_valid, last_validated_at

Resume                      简历主记录
├─ user, title, source_file(PDF), mineru_markdown, current_version

ResumeVersion               结构化简历版本（可编辑、可回溯）
├─ resume, version_no, change_note, created_at
└─ structured_json:
   { basics:{name, intent_role, contact, years_exp},
     education[], skills[{name, level}],
     projects[{name, role, tech_stack, bullets, metrics}],
     work_experiences[], awards[] }

JobPosition                 ★预置岗位库（管理后台维护，全站共享）
├─ category(前端|后端|算法|产品|数据|测试|运维|...),
│  title, level(实习|校招|社招), description,
│  skill_requirements[{skill, weight, required}],   # 推荐用
│  knowledge_points[],                              # 基础笔试出题大纲
│  coding_topics[],                                 # 代码笔试出题方向
│  interview_focus[]                                # 面试考察重点

UserPortrait                ★用户画像（确定性引擎产出）
├─ user, resume_version, computed_at
└─ profile_json:
   { skill_vector{normalized skills}, project_tags[], experience_level,
     direction_scores{前端:x, 后端:y, 算法:z, ...}, strengths[], gaps[] }

JobRecommendation           岗位推荐结果
├─ portrait, job_position, score, matched_skills[], gap_skills[],
│  reasons[]（可解释：每条推荐理由对应具体证据）, created_at

ApplicationSession          ★模拟应聘会话（核心聚合根）
├─ user, job_position, resume_version, provider, model,
│  status(created|in_progress|finished),
│  current_stage(quiz|coding|interview|summary),
│  settings{strict_mode, duration_min}, started_at, finished_at
├─ interview_state_json     ★断点续面状态（见 §5.3③-B）：
│  { phase, time_used_min, asked_question_ids[], evals_digest[],
│    dangling_threads[], found_flaws[], found_highlights[],
│    plan_adjustments[] }
├─ context_summary          ★早期对话滚动摘要（每 K 轮更新）,
│  context_summary_turn_seq（摘要覆盖到的轮次）, last_turn_seq

── ① 基础题笔试 ──
ExamQuestion                试题
├─ application, seq,
│  type(single|multi|short_answer),
│  difficulty(1-5), stem, options[],
│  reference_answer, scoring_points[], knowledge_tag, score_full
ExamAnswer
├─ question, content, score, judge_json{reason}, submitted_at

── ② 代码笔试 ──
CodingQuestion
├─ application, seq, stem, function_signature, examples[],
│  constraints, language_hint, score_full, reference_solution
CodingAnswer
├─ question, code, language,
│  score, judge_json{correctness, edge_cases, complexity, style,
│                    comments, improved_solution}, submitted_at

── ③ 面试问答 ──
InterviewPlan               面试计划（环节+题池+追问树）
├─ application, plan_json
InterviewTurn               对话轮次
├─ application, seq, role(interviewer|candidate|system),
│  content, eval_json（面试官隐藏评估）,
│  meta{phase, question_id, depth, interrupted}, created_at

FinalReport                 ★综合总结报告
├─ application,
│  overall_score, hire_recommendation(强推|推荐|待定|不推荐),
│  stage_scores{quiz, coding, interview},
│  dimension_radar{基础知识, 编码能力, 项目深度, 沟通表达, 岗位匹配},
│  per_stage_summary[], highlights[], weaknesses[],
│  improvement_plan[], resume_edit_suggestions[], created_at

ResumeEditSuggestion        简历修改建议（diff 式，可逐条采纳）
├─ application(or resume_version), field_path,
│  original_text, suggested_text, reason, status(pending|accepted|rejected)
```

---

## 5. 功能模块详细设计

### 5.1 F1 简历解析、更改与展示

**流程**：
1. 上传 PDF → 存原文件 → Celery 调 MinerU API → Markdown（保留标题/表格/列表）。
2. LLM 结构化抽取：Markdown → `ResumeVersion.structured_json`（严格 schema + 校验失败自动重试 ≤2）。
3. **展示界面**：简历卡片式可视化（个人信息 / 技能标签 / 项目卡 / 经历时间线），渲染为一份干净的在线简历页。
4. **更改**：同一界面切换编辑模式——结构化表单逐字段改，左侧表单右侧 MinerU 原文对照；保存生成新版本；版本历史可 diff、可回滚。
5. 解析状态：解析中 → 完成 → 待确认。

**解析缓存与增量分析契约（用户要求，测试锁定）**：
1. **PDF 不变，绝不重复解析**：MinerU 结果（markdown）按 `mineru_source_hash`（PDF 字节 md5）缓存；同 PDF 重触发解析时跳过 MinerU 直接复用缓存，只有 PDF 变更才重新解析（`test_unchanged_pdf_never_reparsed` / `test_changed_pdf_triggers_full_reparse`）；
2. **在线编辑零解析**：保存编辑版本只写结构化数据，不触发任何 PDF 解析 / LLM 抽取（`test_online_edit_never_touches_pdf_parse`）；
3. **衍生分析仅增量更新**：画像、推荐、面试弹药卡等 LLM 衍生分析（Phase 2/3）挂在 `ResumeVersion` 变更钩子上，**仅对编辑变更的条目做增量分析更新**，永不回退到 PDF 层；未变更条目的分析结果随版本继承。

### 5.2 F2 用户画像评估 + 岗位匹配

**决策（v2 修订，用户反馈后）：混合双层。** 纯规则打分经实测不够"准"（待补强列的是泛化技能差异、分数给不出语义判断），修订为：

1. **LLM 评估层（承担"准"）**：评分 / 匹配点 / **待补强逐条锚定 JD 原文要求**（"JD 要求 PyTorch，简历未体现 → 具体补强建议"），带评分标准锚定防讨好；**支持任意粘贴的 JD**（JobProfile），不再局限于预置岗位库——预置库降级为快速选择 + 笔试/面试出题蓝图。默认模型 mimo-v2.6-flash。
2. **规则引擎（承担快速信号）**：方向倾向条形图、技能统计，零成本即时展示，明确标注"仅供快速参考"。
3. **样本集回归测试**继续守规则层；LLM 层用严格 schema 校验 + 评分锚定 + 实测抽检保质量。

**规则引擎设计（快速信号层）**：

```
ResumeVersion.structured_json
   │
   ├─ 1. 技能归一化：技能同义词表（React/React.js、MySQL/关系型数据库…）
   │     → skill_vector（规范技能集合 + 熟练度权重）
   ├─ 2. 项目打标：项目描述关键词 → project_tags
   │     （高并发/爬虫/推荐系统/CRUD/数据管道/PM 需求文档…）
   ├─ 3. 经验定级：教育 + 年限 + 项目深度 → experience_level
   │
   ▼
UserPortrait
   ├─ direction_scores = Σ(技能命中 × 岗位技能权重)
   │                     + Σ(项目标签 × 岗位方向亲和度)
   │                     + 经验等级匹配修正
   ▼
JobRecommendation（对岗位库每条岗位打分，取 Top-N）
   └─ 每条推荐输出：score / matched_skills / gap_skills / reasons[]
```

- **岗位库**（`JobPosition`）由我们预先维护：覆盖前后端、算法、产品、数据、测试等互联网岗位 × 实习/校招/社招，每条含技能需求矩阵（带权重）、基础知识考点、代码题方向、面试重点——**同一份岗位定义同时驱动推荐、基础笔试出题、代码笔试出题、面试考察重点**，保证四段体验围绕同一 JD 口径。
- **校准方式**：内置一份"标准简历样本集"（每方向 2–3 份典型简历 + 期望推荐 Top-3），作为引擎的回归测试用例；调权重直到全部命中——这就是"必须准"的工程化保障。
- 画像页展示：方向倾向条形图、技能雷达、强项/短板、Top-5 推荐岗位卡片（点进去可直接发起模拟应聘）。
- 支持手动选择任意岗位（不限于推荐列表）。

### 5.3 F3 模拟应聘（核心，三段式）

用户选定岗位（来自推荐或手动选择）→ 创建 `ApplicationSession` → 按阶段推进（三段顺序进行，也可单独重考某段）：

#### ① 基础题笔试（选择 + 简答）
- **出题**：LLM 依据 `JobPosition.knowledge_points` + 简历技能栈出题——岗位需求的基础知识为主（如后端岗：网络/OS/数据库/并发；产品岗：需求分析/数据分析/产品设计），简历里写到的技术点适当加权；难度分布 3:5:2（易:中:难）。
- **题型**：单选、多选、简答（简答带评分要点 `scoring_points`）。
- **作答**：逐题或试卷模式，计时（可配置）。
- **判卷**：客观题比对参考答案（语义等价交给 LLM 判定）；简答 LLM 按评分要点给分 + 评语。
- 产出：每题得分 + 解析，进入报告。

#### ② 代码笔试（大模型检查）
- **出题**：LLM 依据 `JobPosition.coding_topics` + 简历技术栈生成（如后端：手写线程安全缓存/SQL 场景/接口设计；算法：经典模型场景题；产品：可出 SQL/数据分析小题），难度递进 2 题左右。
- **作答**：CodeMirror 编辑器，语言可选（Python/Java/Go/JS/C++），带函数签名、示例、约束。
- **判卷（大模型检查）**：LLM review 四维度——正确性思路 / 边界处理 / 复杂度 / 代码风格，输出分项得分 + 逐条批注 + 改进版参考代码。UI 明示"AI 评审"，不做在线运行判题。
- 产出：分项得分 + 批注，进入报告。

#### ③ 模拟面试问答（核心中的核心）

目标：**像真实大厂面试官**——有备而来、随答而变、深挖到底、节奏可控，绝不机械念题。

**面试前：生成"面试计划"（InterviewPlan）**
LLM 输入 = 结构化简历 + 岗位定义（`interview_focus`）+ 前两段笔试的**错题/弱项** + 时长/严格度，输出：

```json
{
  "phases": [
    { "name": "自我介绍", "target_min": 3 },
    { "name": "基础知识", "target_min": 10,
      "question_pool": [
        { "id": "q1", "topic": "TCP 三次握手", "difficulty": 3,
          "why": "岗位要求网络基础；简历写了高并发项目",
          "followups": ["为什么不是两次？", "握手包丢失会怎样？"] } ] },
    { "name": "项目深挖", "target_min": 20,
      "targets": [{ "project": "简历项目X",
        "angles": ["技术选型依据", "最难的点", "指标怎么来的",
                   "量级翻 10 倍怎么办", "你负责的具体边界"] }] },
    { "name": "场景/系统设计", "target_min": 12, "question_pool": [...] },
    { "name": "候选人提问", "target_min": 5 }
  ]
}
```

> 关键联动：基础笔试答错的知识点会被面试官"恰好"问到（真实面试官会顺着简历和笔试表现问），三段不是割裂的三份卷子，而是一场完整的考察。

**面试中：多轮智能对话（状态机 + 自适应追问）**
每轮 prompt 组装：面试官人设（方向 + 资深程度 + 大厂风格）+ 面试计划与进度 + 简历项目细节（追问弹药）+ 岗位要求 + 笔试弱项 + 最近 N 轮对话（滑动窗口）+ 上一轮隐藏评估。

**自适应规则（system prompt + 后端调度）**：

| 候选人表现 | 面试官动作 |
|---|---|
| 回答浅/像背书 | 沿 followups 追一层："为什么是这样？换成 XX 场景呢？" |
| 回答有破绽 | 抓住破绽追问，不轻易放过 |
| 回答扎实 | 快速切下一话题，或拔高到开放性难题 |
| 完全卡壳 | 给台阶/换同主题题（严格模式下不给） |
| 跑题 | 礼貌拉回 |
| 时间超支 | 收敛问题，进入下一 phase |

**对话能力**：SSE 流式逐字渲染；可随时打断；可"换一题 / 提示一下"（给方向不给答案）；面试官会主动反问收尾。每轮写入隐藏 `eval_json`。

#### ③-A 防机械设计（智能性保障）★ 不可裁剪

"不机械、要智能"通过 **六个具体机制** 落地，缺一不可：

1. **因人出题，绝不通用题库**：每道题在生成面试计划时就绑定"为什么问这个"（`why` 字段）——必须能追溯到候选人简历里的某段项目/技能，或岗位要求，或笔试错题。计划里没有 `why` 证据的题不允许进入题池。
2. **隐藏评估驱动的状态机**：面试官每轮先输出一份隐藏评估（`eval_json`：理解度 1–5 / 深度 1–5 / 是否背诵 / 是否跑题 / 破绽点），后端状态机据此决定下一步动作（追问 / 拔高 / 换题 / 给台阶 / 收敛），**而不是线性念完题池**。题池只是弹药库，不是剧本。
3. **指代候选人原话的追问**：追问必须引用候选人刚说的具体内容（"你刚才提到用了 Redis 做缓存，为什么不用本地缓存？一致性怎么保证？"），禁止脱离回答的模板式反问。实现上把候选人回答的关键句注入下一轮 prompt 并要求引用。
4. **动态调整计划**：允许面试官在对话中实时修改后续计划——某方向答得好就跳过其基础题直接拔高；发现意外亮点（简历没写的技能）就临时加问；某环节超时就压缩。计划变更记录在 turn 的 meta 里，报告可见。
5. **语态真实 + 明令禁止清单**：system prompt 用真实大厂面试录音文本做 few-shot（口吻简短、有停顿感、会说"嗯，你继续"），并**明令禁止**：一次抛多个问题、复读题目、客套八股（"这是一个很好的问题"）、脱离上下文的夸奖、机械报幕（"下面进入第二题"）。违反禁止清单的回答由后端正则/规则初筛 + 面试官自查兜底。
6. **长程一致性**：面试官记住整场已问内容，不重复、不自相矛盾；前期埋的线索（"这个我们待会儿再聊"）后期要兑现——通过对话摘要压缩时保留"已问清单 + 未兑现线索清单"实现。

**智能度验收标准（Phase 3 完成的 Definition of Done）**：
- 用同一份简历跑 3 场面试，题池重合度 < 50%，追问路径各不相同（自适应生效）；
- 抽查 10 条追问，≥9 条能引用候选人原话或简历具体项目；
- 主观评审（对照真实面试体验）：无"机械报幕/复读/多问连发"等禁止清单行为；
- 人为给一个"背八股"的浅回答，面试官必须在 2 轮内出现深度追问或破绽打击。

#### ③-B 断点续面与上下文记忆（不引入 RAG 的设计）

**决策：不用 RAG/向量库。** 理由：简历结构化后仅几 KB，整体注入即可，无需检索；对话记忆的本质是**结构化状态管理**（问过什么、评估如何、线索未兑现），存 JSON 比向量检索确定、不漏；RAG 反而引入 embedding 质量与漏召回两个新出错环节。未来若支持多文档附件/超大题库/跨几十场面试的检索，再评估引入。

**InterviewContextBuilder —— 每轮组装 prompt 的五层上下文**：

```
1. 静态层（会话开始时生成一次，存库永久复用，绝不重复分析）
   人设 + 岗位定义 + 结构化简历 + InterviewBriefing「面试弹药卡」
   （每个项目的预判攻击角度 / 待核实指标 / 深挖线索清单）
2. 状态层（每轮更新 → interview_state_json）
   当前环节与时间预算、已问问题清单、各题隐藏评估摘要、
   未兑现线索（"这个待会儿聊"）、已发现的破绽与亮点、计划调整记录
3. 滚动摘要（每 K 轮把早期对话压缩成摘要，存 context_summary，版本化）
4. 近期原文（滑动窗口：最近 12–20 轮原始对话）
5. 跨会话层（可选）：往期 FinalReport 要点
   （"上次 Redis 一致性追问你答得不好"——支持连续成长叙事）
```

**断点续面（中断后再次登录继续）**：
- 每轮对话经 `InterviewTurn` 落库（流结束标记 `streaming_done`）；
- 中断（关浏览器/断网/改天再来）后重新登录 → `GET /api/applications/{id}` 返回阶段与进度 → 面试界面显示"继续上次面试"→ 上下文由五层机制重建，面试官**无缝接着聊**（开场语自然衔接，如"刚才我们聊到你项目里的缓存方案…"），不重新分析简历、不从头开始；
- SSE 断线重连：`Last-Event-ID` 续传增量，`turn_id` 幂等防重复；
- 三段式各阶段均可独立断点续做（笔试做到第 5 题中断，回来继续第 5 题）；
- 半成品回答（流中断的轮次）标记 partial，恢复时面试官视情况确认或继续。

**记忆不遗忘的验收标准**：会话中途强制中断并隔天恢复后——(a) 面试官能准确复述已问主题且不重复出题；(b) 能主动兑现中断前埋下的待聊线索；(c) 恢复后 3 轮内的追问与中断前逻辑连贯。

**面试后**：面试维度评估（基础/项目深度/沟通/岗位匹配）+ 逐题复盘，汇入 FinalReport。

### 5.4 F4 应聘总结（FinalReport）

三段结束后生成综合报告（LLM 汇总三段数据 + 隐藏评估）：

- **综合结论**：总评分 + 录用建议等级（强推/推荐/待定/不推荐）——模拟"面试官结论"，真实感强；
- **五维雷达**：基础知识 / 编码能力 / 项目深度 / 沟通表达 / 岗位匹配；
- **分段小结**：笔试得分与错题知识点、代码分项、面试逐题复盘时间轴（标记追问/拔高/卡壳点）;
- **强项 / 硬伤 / 改进计划**（"下次面试怎么答"，含练习清单）;
- **简历修改建议**（diff 式，原句 → 建议句 → 理由，如"这个指标没写来源，面试必被追问"），逐条 accept/reject 后生成新 `ResumeVersion` —— **形成"面试 → 改简历 → 再面试"的成长闭环**。

---

## 6. API 设计概览

```
# 认证与 Key
POST   /api/auth/register | login | refresh
GET/POST/DELETE /api/credentials/          # 掩码返回
POST   /api/credentials/validate

# F1 简历
POST   /api/resumes/upload                # PDF → 解析任务
GET    /api/resumes | /resumes/{id}
GET    /api/resumes/{id}/versions | /versions/{vid}
PUT    /api/resumes/{id}/versions/{vid}   # 编辑保存（生成新版本）

# F2 画像与推荐
POST   /api/profiling/compute             # 基于某简历版本重算画像
GET    /api/profiling/portrait
GET    /api/profiling/recommendations     # Top-N 岗位 + 理由
GET    /api/jobs                          # 岗位库浏览（可按类别筛）

# F3 模拟应聘
POST   /api/applications/                 # 创建（job + resume_version + settings）
GET    /api/applications/{id}             # 状态/进度
POST   /api/applications/{id}/quiz/start | /quiz/answer | /quiz/submit
POST   /api/applications/{id}/coding/start | /coding/submit
POST   /api/applications/{id}/interview/start
GET    /api/applications/{id}/interview/state         # 断点续面：进度/已问主题/待聊线索
POST   /api/applications/{id}/interview/resume        # 恢复会话（重建上下文，返回衔接开场）
POST   /api/applications/{id}/interview/messages      # 候选人回答
GET    /api/applications/{id}/interview/stream        # ★ SSE 流式（支持 Last-Event-ID 续传）
POST   /api/applications/{id}/interview/interrupt | hint | skip | finish
POST   /api/applications/{id}/finish                  # 触发综合报告

# F4 总结
GET    /api/applications/{id}/report
GET/PUT /api/applications/{id}/resume-suggestions     # diff 建议逐条处理
GET    /api/applications                              # 历史列表（复盘对比）
```

SSE 事件：`delta`（增量文本）/ `turn_eval` / `phase_change` / `done` / `error`。

---

## 7. 前端页面结构

```
/login, /register               极简居中卡片表单
/                               首页：一句话介绍 + 「上传简历，开始模拟应聘」主入口

/resumes                        简历列表 / 上传 / 解析进度
/resumes/{id}                   ★简历展示页（卡片式在线简历）
/resumes/{id}/edit              编辑模式（左表单右 MinerU 原文对照）+ 版本历史

/profiling                      画像页：方向倾向 / 技能雷达 / 强弱项
/profiling/recommendations      Top-N 推荐岗位卡片（每条带推荐理由，一键发起应聘）
/jobs                           岗位库浏览（按类别/级别筛）

/applications/new               创建模拟应聘（选岗位 + 简历版本 + 严格度/时长）
/applications/{id}/quiz         ① 基础笔试（逐题/试卷模式 + 计时）
/applications/{id}/coding       ② 代码笔试（题面 + CodeMirror）
/applications/{id}/interview    ③ ★面试间：居中对话流、底部输入框、
                                顶部环节/计时；克制的面试官头像
/applications/{id}/report       综合总结（雷达 + 分段小结 + 复盘时间轴
                                + 简历修改建议 diff 卡片）
/applications                   历史列表（可对比成长曲线）

/settings                       API-Key / 默认模型 / 账号
```

**设计规范（token 化）**：背景纯白/`#FAFAFA`、文字 `#1A1A1A`、弱化灰 `#8E8E93`、单一强调色（深蓝或墨绿，Phase 6 定稿）；系统字体栈，正文 15–16px；大留白、无边框卡片、圆角 12px、动效仅淡入与打字流。**拒绝**：渐变紫蓝、glow、robot 图标、粒子背景。

**多端自适应（移动优先）**：

| 端 | 布局策略 |
|---|---|
| 手机（<768px） | 单列流式；底部导航栏；面试间输入框 sticky 底部 + 安全区适配（`env(safe-area-inset)`）；代码笔试用全屏编辑器（CodeMirror 移动端可打字）；报告页雷达图/复盘纵向堆叠 |
| iPad（768–1024px） | 双栏（列表+详情）；编辑器左表单右原文可并排 |
| 电脑/大屏（>1024px） | 现有页面结构：侧边导航 + 多栏内容区；面试对话居中限宽（720px 阅读宽度） |
| 通用 | Tailwind 断点 + 触控目标 ≥44px；无横向滚动；SSE 长连接在移动端切后台再回前台自动重连（`Last-Event-ID`） |

**国际化（i18n）**：
- react-i18next，`zh-CN` / `en` 双语包；**所有 UI 文案走 i18n key，禁止硬编码字符串**（开发期约定，同 §11.0 配置化原则）；
- 语言切换入口在顶栏（中/EN），选择持久化到 localStorage + 用户档案，登录后跨设备同步；
- **输出语言跟随界面语言**：面试官对话、笔试题目、判卷评语、报告均以当前语言输出（prompt 注入 `response_language`），支持"中文界面 + 英文面试"练习外企面试——切换界面语言即切换面试语言；
- 简历解析：输入 PDF 中文/英文均可，结构化字段与展示跟随界面语言渲染（字段值保持简历原文语言）。

---

## 8. 项目目录结构

```
ai-mock-interview/
├─ backend/
│  ├─ config/             # settings, urls, celery
│  ├─ apps/
│  │  ├─ accounts/        # 用户、ProviderCredential
│  │  ├─ resumes/         # MinerU client、解析任务、版本/编辑
│  │  ├─ profiling/       # ★规则引擎：normalizer、scorer、recommender、
│  │  │                   #   skill_taxonomy（同义词表）、job_seed（岗位库种子数据）
│  │  ├─ jobs/            # JobPosition 模型 + 管理命令/后台维护
│  │  ├─ sessions/        # ★模拟应聘：quiz_builder、coding_builder、
│  │  │                   #   interview_planner、interviewer_agent、evaluator、judge
│  │  └─ reports/         # FinalReport、简历优化建议
│  ├─ core/               # llm_adapter、mineru_client、crypto、sse 工具
│  └─ tests/              # 含画像引擎回归测试（标准简历样本集）
├─ frontend/
│  ├─ src/
│  │  ├─ api/             # axios/fetch 封装、SSE client
│  │  ├─ pages/ components/ stores/ styles/
├─ docker-compose.yml     # postgres + redis + backend + frontend
└─ PLAN.md
```

---

## 9. 里程碑（约 5–6 周）

| 阶段 | 内容 | 估时 |
|---|---|---|
| **Phase 0** | 脚手架：Django+DRF+JWT、React+Tailwind、docker-compose、LLM Adapter（DeepSeek/MiMo + 流式）、API-Key 加密管理；含 §11.0 部署友好约定；**含 i18n 骨架 + 移动优先布局基础（文案全走 key，避免后期补翻译返工）** | 3–5 天 |
| **Phase 1** | F1 简历：上传/MinerU 解析/结构化抽取/展示页/编辑/版本 | 5–7 天 |
| **Phase 2** | F2 画像：岗位库种子数据 + 归一化/打标/打分引擎 + 样本集回归测试 + 画像/推荐页 | 4–5 天 |
| **Phase 3 ★** | F3 面试问答（核心）：面试计划 → SSE 面试间 → 自适应追问状态机 → 打断/提示/换题 → 与笔试弱项联动 → **断点续面（§5.3③-B）**；过智能度 + 续面两套验收标准才算完成 | **10–12 天** |
| **Phase 4** | F3 基础笔试 + 代码笔试（组卷、判卷、CodeMirror） | 5–7 天 |
| **Phase 5** | F4 综合总结报告 + 简历 diff 修改建议闭环 | 4–5 天 |
| **Phase 6** | UI 打磨（设计规范 + Logo 定稿）、**多端实测（手机/iPad/电脑）**、中英文案审校、体验细节、**两版部署落地**（本地 docker-compose 一键起 + 免费云端 B1 上线，产出两份部署文档与 GitHub Actions） | 5–6 天 |

> 可演示闭环节点：Phase 3 结束 = 上传简历 → 画像推荐 → 选岗 → 智能面试 → 面试小结；Phase 5 结束 = 完整三段式 + 综合报告。

---

## 10. 关键风险与对策

| 风险 | 对策 |
|---|---|
| 画像/推荐不准 | 结构化抽取严格 schema 把关 + 同义词表持续维护 + **标准简历样本集回归测试**（调参直到 Top-3 命中）+ 推荐理由可解释可纠错 |
| 面试官"机械化" | §5.3③-A 六机制（因人出题/隐藏评估状态机/引用原话追问/动态计划/禁止清单/长程一致性）+ 智能度验收标准作为 Phase 3 的 DoD，不达标不进下一阶段 |
| LLM 结构化输出不稳 | schema 校验 + 失败重试 + 宽松解析降级；面试计划/报告单独校验层 |
| 流式中断/重复 | SSE 断线重连带 turn_id 幂等；turn 流结束后落库标记 |
| Token 成本 | 五层上下文设计（§5.3③-B）：静态层复用 + 滚动摘要 + 滑动窗口；报告只投喂压缩摘要 |
| 中断后失忆/上下文重建不完整 | interview_state_json（已问/评估/线索）为权威状态，摘要仅压缩早期原文；恢复后按验收标准（复述不重复、兑现线索、逻辑连贯）测试 |
| 用户 API-Key 泄露 | Fernet 加密、永不回传、日志脱敏、内存解密调用 |
| MinerU 输出质量参差 | 结构化抽取 + 人工确认兜底，保留原文对照 |
| MiMo/DeepSeek 接口差异 | OpenAI 兼容层 + provider 配置化 base_url/model |

---

## 11. 部署方案

### 11.0 部署友好开发约定（贯穿所有 Phase，不只是 Phase 6）

开发期即遵守，保证本地/免费云端两版随时可切换、不返工：

| 约定 | 做法 |
|---|---|
| 配置零硬编码 | `django-environ`：数据库 URL、存储、队列模式、CORS、ALLOWED_HOSTS 全部走环境变量；`.env.example` 随仓库维护 |
| **任务队列可切换** | `TASK_MODE=celery`（本地/完整版）或 `TASK_MODE=lite`（免费云端：同进程线程池执行后台任务，去掉 Redis 依赖）。业务代码只调 `core.tasks.dispatch(fn, *args)` 统一入口 |
| **文件存储可切换** | `STORAGE=local | s3 | db`。小文件（简历 PDF）支持存 DB bytea——免费云磁盘多为临时盘，DB 存储最省事可靠 |
| 流式友好 | SSE 响应带 `X-Accel-Buffering: no`；Gunicorn 用 gthread worker；文档注明 Nginx/代理需 `proxy_buffering off` |
| 静态/媒体 | Whitenoise 托管前端构建产物（或纯 CDN 托管前端）；开发 CORS 全开按环境变量控制 |
| 生产安全 | DEBUG 按环境变量、密钥不入库、HTTPS 由前置代理终止、日志脱敏（API-Key 永不入日志） |
| 健康检查 | `/api/healthz`（含 DB 连通性），免费平台的探活/自唤醒都依赖它 |

### 11.1 版本 A：本地部署版（完整功能）

一条命令起全套：`docker-compose up`。

```
services: postgres + redis + django(gunicorn) + celery-worker + celery-beat
          + frontend(build 后由 nginx 托管静态并反代 API/SSE)
```

- 无任何功能删减：Celery 真队列、Redis 缓存、本地磁盘存 PDF；
- 适合个人使用、演示、二次开发；Mac/Linux/Windows(Docker Desktop) 均可；
- 提供 `make init`（迁移 + 岗位库种子数据 + 超管账号）。

### 11.2 版本 B：云端免费部署版（$0，免信用卡子方案 + 常免费 VM 方案）

**原则：全部使用长期免费层，用户自己的 LLM/MinerU API-Key 也是用户侧成本，平台方零费用。**

#### 方案 B1：免信用卡免费 PaaS 拼装（推荐首选，纯注册即用）

| 组件 | 平台 | 免费额度 |
|---|---|---|
| 前端静态托管 | **Cloudflare Pages**（或 Vercel） | 免费、全球 CDN、免冷启动 |
| Django 后端 | **Render Free Web Service** | 免费（750 小时/月）；**15 分钟无访问后休眠，冷启动约 50 秒** |
| PostgreSQL | **Neon**（serverless Postgres） | 免费 0.5 GB 存储；计算闲置自动暂停（唤醒秒级） |
| 后台任务 | `TASK_MODE=lite`（同进程线程池） | 不需要 Redis/Celery，省掉一个免费组件 |
| 简历 PDF | `STORAGE=db`（bytea 存 Neon） | 免费额度内（单份 PDF 通常 < 5 MB） |

配套改造（一次性，架构已预留）：
- `render.yaml` + `wrangler.toml`/CF Pages 配置入库，一键部署；
- SSE 在 Render 上直接支持流式响应（已按 §11.0 做好不缓冲）；
- 冷启动体验优化：前端在"继续面试"时先打 `/api/healthz` 预热，页面给"服务唤醒中…"提示。

#### 方案 B2：Oracle Cloud Always Free VM（$0 但注册需信用卡验证，不扣费）

- 一台 ARM VM（最高 4 核 24 GB，长期免费）直接跑 **版本 A 的 docker-compose 全栈**，功能无删减、无休眠冷启动；
- 适合愿意绑定一张信用卡做注册验证、想要"真服务器"体验的用户；配一个免费域名/Cloudflare 之后体验接近付费 VPS。

#### 免费版的诚实代价（产品内向用户说明）

| 代价 | 应对 |
|---|---|
| Render 休眠 → 首次访问约 1 分钟冷启动 | 预热请求 + "唤醒中"提示；面试中途不会休眠（有活跃流量） |
| Neon 计算暂停 → 首个查询慢几秒 | 同上，可接受 |
| 免费层政策随时可能变化 | 平台选择集中在一个 `deploy/` 目录与文档里，替换平台不动业务代码（配置化约定已保证） |
| lite 模式长任务（批量出题）比 Celery 弱 | 单次面试相关任务都在秒~分钟级，lite 足够；真正大批量才需要 Celery |

#### 部署文档（Phase 6 产出）
- `docs/deploy-local.md`：本地版逐步指南；
- `docs/deploy-free-cloud.md`：B1 逐步指南（注册 Neon → Render → Cloudflare Pages，含环境变量清单）+ B2 简版指南；
- CI：GitHub Actions 免费额度跑测试 + 前端构建，push 即部署 B1 三件套。

### 11.3 开发环境

`docker-compose.dev.yml`：postgres + redis + Django(runserver) + Vite；`TASK_MODE` 默认 celery，也可本地用 lite 模式模拟免费云行为。

---

## 12. 开发流程（GitHub Flow 变体）

**远程仓库**：`git@github.com:SimonHanYANG/Sparr.git`（origin）。

### 12.1 分支模型

```
main        发布专用 ✋ —— 只进发布版本，打 tag（v0.1 … v0.6, v1.0）
              合并/推送 main 必须先征得用户同意（每次）
develop     集成分支 —— 日常集成，及时 push，无需逐次同意
feature/*   功能分支 —— 从 develop 切出，完成后合回 develop 并及时 push
              命名：feature/phase-0-scaffold、feature/resume-parse …
release/*   发布准备（可选）—— develop → main 的发布 PR 分支
hotfix/*    线上修复 —— 从 main 切出，修完回 main（走同意）并同步 develop
```

### 12.2 铁律（已与用户确认）

1. **main = 发布版本**：仅在发布点合并；每次合并/推送 main 前**必须征得用户同意**，获准后打 tag（`v0.N` 对应 Phase N，完整版 `v1.0`）并附发布说明；
2. **开发过程及时 push**：`feature/*`、`develop` 的推送无需逐次询问，完成一个有意义的增量即推送，保持远程同步；
3. **按 Phase 发版**：每个 Phase（里程碑）完成 = 一个可发布版本，合并 develop → main、打 tag；
4. 发布流程：`develop` 全绿（测试通过）→ 开 PR/汇总变更 → **征得同意** → merge 到 main → tag → push main --tags；
5. 提交规范：Conventional Commits（`feat:` `fix:` `chore:` `docs:`…），提交信息末尾附 Co-Authored-By 签名；
6. PR/合并信息使用规范模板，发布说明列出该 Phase 的用户可见变化。

### 12.3 开发进度（活文档 · 会话交接棒）

> **约定（CLAUDE.md 强制）**：每完成一个有意义的增量，立即更新本表（勾选 + 日期 + commit 短号 + 遗留问题），并及时 push 对应分支。新会话从本表了解进度，不通读代码/全文。

**当前阶段**：Phase 2 已发布 v0.3 · 进行中 Phase 3（★ 智能面试问答）· 最近更新 2026-10-03

- [x] 需求与架构计划定稿（PLAN.md v3，含面试智能化/断点续面/双部署/i18n/多端）— 2026-10-02
- [x] 仓库初始化 + GitHub Flow 配置（远程 origin 就绪）— 2026-10-02 · `0b8e4f9`
- [x] CLAUDE.md / README.md 建立 — 2026-10-02
- [x] **Phase 0**：脚手架 — 2026-10-02 · `feature/phase-0-scaffold`
  - 后端：uv + Django 6.1 + DRF + SimpleJWT + CORS + env 配置；apps 六件套骨架；`core/`（LLM Adapter 流式/OpenAI 兼容、Fernet 加密、TASK_MODE/STORAGE 抽象、SSE 工具、healthz、MinerU client 接口）
  - accounts：注册/登录/JWT/me + ProviderCredential（加密落库、掩码回读、validate 端点）— 7 测试全过
  - 前端：React 18 + TS + Tailwind v4 + i18n（zh/en 双语全量文案）+ 路由骨架 + JWT API 客户端 + 设计 token；Home/登录/注册/骨架页
  - 部署接线：docker-compose（dev + 完整版）、Makefile、.env.example、gunicorn SSE 配置、nginx 反代
  - **UI 自查完成**（Playwright + Chromium，390/768/1280 三断点，无溢出、排版正常；截图脚本固化为 `npm run shots`）
  - 注册体验修复 — 2026-10-02：报错改为逐字段内联显示（用户名占用/密码规则等真实原因）；密码策略（8–64 位 + 大写 + 小写 + 特殊字符）前后端双侧实施，注册页实时规则清单，DOM 级 E2E 断言通过
- [x] **Phase 1**：F1 简历上传 / MinerU 解析 / 结构化抽取 / 展示 / 编辑 / 版本 — 2026-10-02 **发布 v0.2**
  - MinerU API v4 契约实测摸清：`POST file-urls/batch` → 预签名 OSS **PUT（禁止带 Content-Type）** → `GET extract-results/batch/{id}` 轮询（waiting-file→pending→done/failed）
  - 后端：Resume/ResumeVersion 模型、上传 API（PDF≤10MB）、后台解析管线（dispatch）→ MinerU → LLM 结构化抽取（严格 schema + 重试）、版本创建/回滚/重解析 — 20 测试全绿
  - 前端：简历列表（上传+状态轮询）、卡片式在线简历、结构化编辑器（保存即新版本）、版本历史/回滚、解析原文对照；UI 自查通过（DOM 断言：编辑→保存→版本历史全链路）
  - MinerU 双模式策略（按官方文档 https://mineru.net/apiManage/docs 实现）：**🎯 精准解析优先**（`full_zip_url` 取 `full.md`，`model_version=vlm`）→ 队列超过 `MINERU_ACCURATE_PATIENCE`（默认 300s）**降级 ⚡ Agent 轻量解析**（`/api/v1/agent/parse/*`，免 token，`markdown_url` 直取）——已用真实 CV 实测：精准超时降级后轻量解析成功（5209 字符/228 行）
  - LLM 双模型实战验证 — 2026-10-02：DeepSeek 与 MiMo（Token Plan `tp-` key → `token-plan-cn` 集群、`mimo-v2.6-pro`，双鉴权头兼容）均跑通真实 CV 抽取；设置页三凭据卡 + **大模型偏好选择器**（provider+model 自选，`/api/auth/preferences`）；抽取 prompt 加固（技能宁多勿漏）；修复重解析版本号冲突（追加 vN+1 并记录所用模型）— 22 测试全绿
- [x] **Phase 2**：F2 岗位库种子数据 / 画像规则引擎 / 样本集回归测试 / 画像与推荐页 — 2026-10-02~03 **发布 v0.3** · `feature/phase-2-profiling`
  - 岗位库：JobPosition（加权技能矩阵 + 考点/代码题/面试重点/项目亲和标签）× 12 岗位（后端/前端/算法/产品/数据/测试/运维 × 实习/校招/社招），`seed_jobs` 幂等灌库
  - 画像引擎（**纯规则、零 LLM、可复现**）：技能两遍归一化（精确优先，防 "pytorch→py" 误配）、项目打标、经验定级、方向打分、岗位匹配打分（技能 0.55 + 标签 0.3 + 经验 0.15 − 必会缺口惩罚）→ 可解释推荐（matched/gaps/reasons）
  - **样本集回归测试守住"必须准"**：后端/算法/产品/前端四份标准简历全部 rank-1 命中正确方向（9 引擎测试 + 37 全量全绿）
  - API：profiling/compute·portrait + jobs 浏览（类别/级别筛选）；前端：画像页（方向条/优势/项目标签/Top-8 推荐卡带证据与补强提示）+ 岗位库页（筛选/展开详情），导航新增"画像"
  - **主线流式引导**（用户交互重设计）：四步状态机（简历→画像与岗位→模拟应聘→总结提升，宽松跳转）+ 首页工作台（动态"下一步"卡片与 hero CTA，杜绝过期引导）+ 页尾"下一步"衔接条 + `flow/state` 状态接口
  - **岗位匹配评估 LLM 化**（v2 修订）：评分/匹配点/待补强由 mimo-v2.6-flash 评估并逐条锚定 JD 原文；支持任意粘贴 JD（JobProfile）；自适应筛选适合岗位（≥5，一岗一卡含校招/社招）AI 精评；流式进度（骨架卡/进度条/尾部转圈）；评估结果持久化（切页/刷新不丢）；卡片折叠交互
  - 岗位库对齐 2026 热招口径（34 条：VLA/具身智能、预训练、后训练、感知算法、Agent/RAG、MLSys 等）
  - **岗位页 = 备考工作台**（用户交互重设计）— 2026-10-03 · `cbb34fe`：岗位卡显示「我的匹配度」；展开工作台 = 我 vs 岗位（一键 AI 评估/重评）+ 考点自查（掌握/模糊/不会 三态即时保存，**自评薄弱项喂给面试官**）+ 目标岗位星标（纳入主线）+ 一键「针对此岗位模拟应聘」；自定义 JD 收进「我的 JD」区消除割裂 — 52 测试全绿
- [x] **Phase 3 ★**：F3 面试问答（面试计划 / SSE 面试间 / 自适应追问 / 断点续面）— 过 §5.3③-A + §5.3③-B 两套验收 — 2026-10-03~04 · `feature/phase-3-interview`（待发 v0.4）
  - [x] 面试域模型 + 面试计划生成 — 2026-10-03：ApplicationSession/InterviewPlan/InterviewTurn（sparr_sessions 迁移 0001）；`generate_plan`（briefing 弹药卡 + phases 题池，每题强制 `why` 证据、targets 必须对上简历真实项目，校验直接丢弃违规项）；会话 API（创建/列表/详情/计划幂等生成 force 重生成）；考点自评薄弱项（模糊/不会）喂入计划 — 59 测试全绿
  - [x] SSE 面试轮次引擎 + 隐藏评估状态机 — 2026-10-03：`POST /api/applications/{id}/turns` 流式面试官回复（[EVAL] 标记服务端剥离不外泄）；五层上下文组装（弹药卡/状态/滚动摘要/滑动窗口/动作指令）；后端状态机 `decide_action`（背书→深挖、破绽→追打、扎实→拔高、卡壳→给台阶、跑题→拉回）注入下轮 prompt；禁止清单正则初筛记入 turn.meta；破绽/亮点/未兑现线索/phase 推进落 interview_state_json；滚动摘要每 K 轮压缩；hint/skip/end 控制 + partial 落库断点续面 — 65 测试全绿
  - [x] 前端面试间 + 对接主线 — 2026-10-03：`/applications` 会话列表（断点续面入口）+ 新建表单（岗位库/我的 JD/时长/严格模式）；`/applications/:id` 面试间（计划预览含出题理由与薄弱项高亮 → 开场 → 对话流式逐字渲染 + 提示/换题/结束控制 + 续面横幅）；岗位页「针对此岗位模拟应聘」一键建会话进面试间；**UI 自查完成**（390/768/1280 无溢出，DOM 断言通过）；**真实 MiMo 实测**：开场口语化自然（无报幕/单问题），背八股浅回答被当场点破并记入隐藏评估（rote=true → 状态机追打，破绽落库）
  - [x] 选岗与加载体验重做（用户反馈）— 2026-10-03：岗位选择弃用大下拉框——**按匹配度降序推荐卡**（点击即选）+ 搜索兜底全部岗位 + 我的 JD 卡片；创建不再阻塞按钮（建会话即进房间）；计划生成走 SSE 流式（`plan/stream`：stage/tick/done，tick 实时揭示出题清单）+ **环绕灯带加载卡**（conic-gradient 边缘光弧 + 已用时计时 + 逐步出题列表 + 重试）；提速：prompt 篇幅克制（followups≤2/why≤30 字）、`max_tokens=2800` 封顶、重试 ≤1、简历/JD 投喂截断减半——实测全程 ~18s 且过程全程可见 — 68 测试全绿
  - [x] 计划 JSON 容错管线（用户现场故障修复）— 2026-10-03：模型偶发输出坏 JSON（字符串内未转义引号/全角逗号/截断 → `Expecting ',' delimiter` 直接报错）；改为严格解析失败后 **json-repair 修复兜底**（字符串感知括号切片 + 多候选重试）+ 截断自适应（尾部未闭合 → 重试自动放宽 max_tokens 预算）+ prompt 源头约束（值内禁英文双引号/半角标点/括号补齐）+ 失败信息带原因 — 70 测试全绿
  - [x] 幽灵文本修复（用户现场故障）— 2026-10-03：面试官回复会多出一段"像思考"的变体文本、卡顿后消失——根因是 `generate_reply` 函数体在历史编辑中整体重复，每轮跑**两次 LLM 流**（第二段流出但落库取第一遍的 result，故显示后消失，且每轮双倍耗时）；SSE 抓帧实证（流出 162 字/落库 73 字）定位后切除重复块；回归测试锁死「chat_stream 仅一次 + 流出==落库」；实测 identical=true — 71 测试全绿
  - [x] 打断（interrupt）— 2026-10-04：流式中控制条变为「⏹ 打断」→ `turns/cancel` 置取消信号 → worker 段间停止、已流出部分落库（meta.interrupted）→ done 收束回正常控制条；客户端断开同样算打断（不白烧生成）；回归测试（慢流中途取消）+ 浏览器实测 — 72 测试全绿
  - [x] 面试后复盘（§5.3③ 面试后）— 2026-10-04：`POST /applications/{id}/review` 整场对话 → 维度评估（基础知识/项目深度/沟通表达/岗位匹配 0-100）+ 录用印象（强推/推荐/待定/不推荐）+ 亮点/不足（强制引用回答原话）+ 逐题复盘 + 改进建议；`review_json` 落库幂等（force 重生成），Phase 5 FinalReport 直接消费不重复分析；结束页复盘卡（印象徽章/维度条/逐题时间轴）+ 环绕灯带加载；真实 MiMo 实测质量高（评分严格不讨好、引用原话、建议具体）— 75 测试全绿
  - [x] **两套验收实测通过（Phase 3 DoD）** — 2026-10-04：**智能度**（同简历同岗 3 场实测：字面题池重合度 0%——语义锚点（Redis/TCP/MySQL…）按简历与 JD 因人复现属机制 1 设计预期，项目深挖角度与追问路径三场各异；追问大量引用原话（"你说'负责整体架构'"、"刚才你提了三个点：整体架构、主从复制、10k QPS"…）；背八股浅回答 **3/3 当场点破**（"你别慌，也别背八股"）；零机械报幕/复读；复合追问多问号 3 次命中→prompt 收紧「一段话最多一个问号」）；**断点续面**（中断恢复 3 轮：复读 0 次；面试官主动追讨未答问题并兑现（"框架和团队分工那两问还是没答，我先记着，待会儿补"）；恢复追问 3/3 引用新回答内容、逻辑连贯）
- [ ] **Phase 4**：F3 基础笔试 + 代码笔试（组卷 / 判卷 / CodeMirror）— 开工 2026-10-04 · `feature/phase-3-interview` 延续
  - [x] **MiMo v2.6 = 思考模型，重要适配** — 2026-10-04：响应含 `reasoning_content` 且**思考 token 计入 max_tokens 预算**（曾致正文截断→JSON 解析失败/空内容）；策略：计划/复盘保留思考+预算 5000-7000（质量靠它），交互对话/出题/判卷 `thinking:{type:disabled}` 提速（出题 121s→37s、对话首字大幅提前）；`llm.chat` 空内容改抛错触发重试（不再静默空串）；`fast_completion_kwargs()` 统一开关
  - [x] 基础笔试域（§5.3①）— 2026-10-04：ExamQuestion/ExamAnswer（迁移 0003）；`generate_quiz` 出题（10 题=单选5/多选2/简答3，难度 3:5:2，考点大纲+简历技能加权，真实实测质量贴岗）；判卷（客观题选项集合确定性比对含多选漏选半分、简答题 LLM 按 scoring_points 给分+评语）；**防作弊**（试卷 API 不下发参考答案/评分要点）；重考覆盖旧作答；**三段联动**：错题 knowledge_tag → `quiz_weak` → 面试计划出题理由 — 79 测试全绿
- [ ] **Phase 4**：F3 基础笔试 + 代码笔试（组卷 / 判卷 / CodeMirror）
- [ ] **Phase 5**：F4 综合总结报告 + 简历 diff 修改建议闭环
- [ ] **Phase 6**：UI 打磨 + 多端实测 + 双语审校 + 两版部署落地（v1.0）

**遗留问题**：本机 8000 端口被其他服务占用，本地跑后端用 8010（`VITE_API_PROXY=http://127.0.0.1:8010` 启动前端代理）；`apps.sessions` 的 Django label 为 `sparr_sessions`（避开内置 sessions 冲突）。

**发布记录**：（main 合并/推送均需涵哥同意后执行）

| 版本 | 日期 | 内容 | commit |
|---|---|---|---|
| —（基线）| 2026-10-02 | 文档基线：PLAN.md + CLAUDE.md + README.md，已推送 origin/main | `0b8e4f9` + `c326a75` |
| **v0.1** | 2026-10-02 | Phase 0：脚手架（后端六 app + core 基建 + LLM 适配层 + API-Key 加密管理；前端双语骨架 + 设计体系；Docker 双版本部署接线；注册体验修复 + 密码策略） | `319dd6d` |
| **v0.2** | 2026-10-02 | Phase 1：简历上传/解析/编辑/版本全功能（MinerU 双模式+缓存、LLM 抽取默认 mimo-v2.6-flash、技能分组、换 PDF、手动创建、设置页凭据与模型偏好） | `ca68265` |
| **v0.3** | 2026-10-03 | Phase 2：画像与岗位匹配全功能（34 条 2026 热招岗位库、规则画像引擎 + LLM JD 锚定评估、自适应精评 ≥5 岗、流式进度与持久化、主线四步流式引导、备考工作台：我的匹配度/考点自查/目标岗位/一键开练） | `cbb34fe` |
