# 09 · 虚拟对话角色（Companion）架构设计

> **状态**：设计草案 / 待评审，**未实施**
> **日期**：2026-11-05
> **适用平台**：Windows 11 原生持久栈（N03），Web（Vite dev）与 Electron 桌面双端
> **验证范围**：基于当前仓库源码的静态架构核对与既有能力调研；未做运行时验证、未跑测试、未做性能实测
> **结论状态**：PROPOSED（架构建议，不作为当前能力承诺；不是「当前基线」）
> **文档性质**：架构决策建议。按 `docs/README.md` 维护约定归入 `架构设计/`；实施与验收证据另行写入 `开发记录/`。

---

## 1. 结论先行

**这不是一个从零新建的功能，而是一次「收编 + 加一层薄编排」。** 仓库里已经存在三套彼此不知道对方存在的角色资产：

| 既有资产 | 位置 | 已具备 |
| --- | --- | --- |
| 程序化 SVG 角色动效引擎 | `apps/frontend/src/lib/grok-character/` | 39 种状态、18 种形状、11 种配色、指针跟随、一次性动作、`destroy()` 生命周期 |
| 落地页对话角色 | `apps/frontend/src/components/landing/GlassConstellation.vue` | 形象 + 状态控制台 + 唤醒词 + **「对话 → 表情」联动**（懒加载 `chatStore` + `sendMessageStream`） |
| TUI 吉祥物系统 | `tools/tui/src/kinlin_tui/mascot.py` | 4 角色 × 6 情绪 ASCII 帧 + 中文对白池（含进度/关怀话术） |

此外还有完整的对话运行时（`stores/chat.ts` 的 SSE 流）、Copilot 会话（`/runs/{id}/copilot/*`）、任务与进度只读投影（`/api/agentos/v2/runs/*`）、意图链（`IntentParser` → `TemplateMatcher` → `CognitiveRouter`）。

因此**核心设计判断**是：

1. Companion 定位为**接入层能力域**：一个「只读消费者 + 受控意图旁路」，不是第二个执行真源。`ExecutionRuntime` 仍是唯一执行真源。
2. 新增一个自包含的 **Companion 能力模块**（前端 `features/companion/` + Python `app/companion/`），通过**端口-适配器**与现有系统通信；内核、Java 网关、Vite、Electron 壳、Chat API 均不改动。
3. 唯一不可避免的存量改动是 `apps/agent/app/main.py` 的**一行 router 注册**（若启用服务端对话能力），以及 `App.vue` 的**一行组件挂载**。

---

## 2. 定位与硬边界

依据 `docs/架构设计/kinlin-agentos-current-architecture.md` 的「不能混淆的边界」与 `apps/agentOS/README.md` 的依赖方向：

| 允许 | 禁止 |
| --- | --- |
| 消费只读投影（`GET /runs/{id}`、`/graph`、`/trace`、`/checkpoints`、`/copilot`） | 成为第二个执行真源或直接调度 ACG 节点 |
| 订阅既有 `GET /runs/{id}/events` SSE | 新建 WebSocket / 新流式协议 / 新 webhook 回调机制 |
| 产出「任务意图卡」，经用户确认后交给既有统一启动入口 | 在宠物层直接创建 Mission / 调用 `startWorkflowAsync` / 写 `/missions` |
| 复用轻量 `LLMGateway.generate_text/generate_json` | 复制 `PromptRuntime`、`IntentParser` 或内核算法 |
| 复用既有 `conversations` / Copilot exchange 追加模式 | 把 task input、ContextPack、模型正文、密钥塞进气泡或事件 payload |
| 表现层推断「展示状态」 | 表现层推断「运行真相」（进度以只读投影为准） |

**引用优先（ADR-001）**：`GET /runs/{id}` 只返回摘要与引用；正文只能经 `/outputs/{outputRef}` 解引用；Trace 投影已递归脱敏。宠物播报同样只呈现 `status / lifecyclePhase / completedStepIds / activeStepIds` 等摘要字段，正文一律以引用卡片呈现。

**不暗改普通 Chat API**：`docs/开发记录/PR-UI-02-...md` 明确「未来若做任务对话须复用既有任务能力，不暗改普通 Chat API」。Companion 使用独立 `/ai/companion/*` 通道与独立会话标识，不向 `POST /ai/chat/text/stream` 注入参数或改变其行为。

---

## 3. 总体架构

### 3.1 四层视图

```
┌─ L0 表现层  apps/frontend/src/features/companion/ + components/companion/
│    CompanionHost（全局浮层，唯一挂载点）· AvatarRenderer · SkinRegistry · SkinLoader
│    DialoguePanel · ProactiveNotice · TaskIntentCard · CompanionStateMachine
│
├─ L1 能力编排层  apps/agent/app/companion/（独立 Python 包，零内核 import）
│    CompanionService（薄编排，只依赖 Port 协议）
│    IntentRouter · SceneRegistry（Progress / Chat / Affection / Dispatch / Control）
│    ContextManager · PersonaRegistry · EmotionPolicy · ProactivityPolicy
│
├─ L2 适配层  Ports 的实现，全部复用既有契约
│    ProgressPort  ← 只读投影 project_run / graph / checkpoints + runs events SSE
│    ChatPort      ← LLMGateway.generate_text / Copilot stream（轻量，不走 ACG）
│    ContextPort   ← Java conversations/messages 或 run_copilot_exchanges 追加模式
│    DispatchPort  ← 前端既有统一 Mission Launcher（非服务端代发，见 §7.4）
│    PersonaPort   ← roles / emotion / recommendation 既有 API
│
└─ L3 平台与内核  零改动
     Spring Boot 网关（/ai/** 通配透传 + 身份头注入）· Vite proxy · Electron 壳
     ExecutionRuntime · ACG · 六类 Store · Identity V2
```

### 3.2 两条数据通道（单向、互不反向）

| 通道 | 方向 | 载体 | 说明 |
| --- | --- | --- | --- |
| **上行：用户 → 宠物** | 前端 → Java → Python | `POST /ai/companion/messages`（SSE 流式）、`GET /ai/companion/skins` | 走 `AiServiceProxyController` 的 `/ai/**` 通配透传；Java 零改动；身份由 `X-Authenticated-*` 由网关注入，Python 侧用 `current_trusted_user()` |
| **下行：内核 → 宠物** | 内核事件 → 前端 | 既有 `GET /api/agentos/v2/runs/{runId}/events` SSE | 项目**没有 webhook**，主动播报只能靠前端订阅既有事件流并映射为形象状态/话术；不新建推送机制 |

**依赖方向恒为 `L0 → L1 → L2 → L3`**，L2 只读或经既有受控入口写入；L3 绝不 import L0/L1。

### 3.3 解耦的可验证定义

> **拔插验收**：整体删除 `apps/frontend/src/features/companion/`、`components/companion/`、`apps/agent/app/companion/` 三个目录，并移除 `App.vue` 与 `main.py` 各一行后，现有主链路（Chat / Mission / Workbench / 内核 1730 项 / Java 架构守卫 / 前端 vitest）应全部保持原状且全绿。若做不到，说明出现了反向依赖。

---

## 4. 模块职责划分

| 层 | 模块 | 单一职责 | 明确不做 |
| --- | --- | --- | --- |
| L0 | `CompanionHost.vue` | 全局悬浮宿主的生命周期、显隐、位置持久化、鉴权态守卫 | 不发起业务请求 |
| L0 | `SkinRegistry` / `SkinLoader` | 皮肤清单注册、校验、懒加载、缓存、失败降级 | 不解释业务语义 |
| L0 | `AvatarRenderer` 接口 | `mount / setState / setSkin / destroy` 四个动作 | 不读取 store、不推断运行真相 |
| L0 | `CompanionStateMachine` | 把对话事件、运行事件、时间策略归一为 8 个语义状态 | 不直接调用具体形象引擎 |
| L0 | `DialoguePanel` / `ProactiveNotice` / `TaskIntentCard` | 输入、气泡、播报、任务确认 UI | 不拼装 Mission 请求体 |
| L1 | `CompanionService` | 单轮编排：`接收 → 取上下文 → 判意图 → 选场景 → 产出流事件 → 落库` | 不 import `runtime.*` / `components.*` 内核符号 |
| L1 | `IntentRouter` | 分级意图识别与槽位抽取，输出 `IntentResult` | 不执行任务 |
| L1 | `SceneRegistry` / `SceneHandler` | 每个意图一个 handler，注册表驱动，新增场景即新增 handler | handler 之间不互相调用 |
| L1 | `ContextManager` | 三层上下文的读写、预算裁剪、滚动摘要 | 不缓存模型正文与密钥 |
| L1 | `EmotionPolicy` / `ProactivityPolicy` | 情绪状态、主动触发条件、节流与优先级 | 不主动提交任务 |
| L2 | 各 `Port` 适配器 | 把 Port 协议翻译成既有 API / 只读投影调用 | 不改写既有契约 |
| L3 | 既有系统 | 唯一执行真源、鉴权边界、持久化 | 零改动 |

**Port 协议（TypeScript 侧示意，Python 侧用 `Protocol` 对应）**

```ts
export type CompanionState =
  | 'idle' | 'listening' | 'thinking' | 'working'
  | 'happy' | 'alert' | 'sleeping' | 'error'

export interface AvatarRenderer {
  mount(el: HTMLElement, skin: SkinManifest): void
  setState(state: CompanionState): void
  setSkin(skinId: string): Promise<void>
  destroy(): void
}

export interface CompanionPorts {
  chat: ChatPort          // 轻量生成，非 ACG
  progress: ProgressPort  // 只读投影
  context: ContextPort    // 会话记忆
  persona: PersonaPort    // 人设与情绪
}
```

**Python 装配（唯一一行存量改动）**

```python
# apps/agent/app/main.py，紧跟既有 include_router 之后
from app.companion import create_router as create_companion_router
app.include_router(
    create_companion_router(ports=build_companion_ports(runtime)),
    prefix="/ai",
    tags=["Companion"],
)
```

`create_companion_router(ports=...)` 与既有 `agentos_v2.create_router(runtime, coordinator)` 采用同样的**工厂 + 构造注入**范式；单测可注入 fake ports，不启动运行时。

---

## 5. 虚拟形象：资源、渲染与展示

### 5.1 三层资源模型（资源与逻辑分离）

| 层 | 内容 | 落点 |
| --- | --- | --- |
| **描述层** | `SkinManifest`：`id / version / rendererType / entry / stateMap / fallbackSkinId / license / size` | `apps/frontend/public/companion/skins/<id>/manifest.json`；内置皮肤以 TS 常量注册 |
| **资源层** | SVG 程序化参数、sprite sheet、Lottie/APNG 帧、语音/对白池 | 同上目录；`public/` 会被 `copy-renderer.mjs` 整体打包进 Electron，Web/Electron 双端一致 |
| **渲染层** | `AvatarRenderer` 实现：`ProceduralSvgRenderer` / `SpriteRenderer` / `LottieRenderer` | `features/companion/renderers/` |

**关键：`stateMap` 是解耦点**。业务逻辑只发 8 个语义状态，由皮肤自己声明如何映射，换形象不改任何业务代码：

```json
{
  "id": "grok-default",
  "version": "1.0.0",
  "rendererType": "procedural-svg",
  "entry": "@/lib/grok-character",
  "stateMap": {
    "idle": "idle", "thinking": "thinking", "working": "curious",
    "happy": "happy", "alert": "surprised", "error": "sad",
    "listening": "curious", "sleeping": "sleeping"
  },
  "fallbackSkinId": "static-logo"
}
```

### 5.2 渲染路线对比与推荐

| 路线 | 优点 | 代价 | 建议 |
| --- | --- | --- | --- |
| **A 程序化 SVG（GrokCharacter）** | 已有 39 状态 / 18 形状 / 11 配色；零图片资源；矢量缩放跟随缩放工具；`destroy()` 干净 | 美术表现偏抽象 | **P0 默认**：直接复用 `lib/grok-character`，抽取 `GlassConstellation.vue` 的 mount/onChange/destroy 生命周期 |
| **B Sprite / Lottie / APNG** | 美术表现强、可换装、可做待机循环 | 需资源体积预算、帧映射、预加载与缓存 | **P3 可选**：`SkinLoader` 预留接口，首次进入才拉资源 |
| **C 3D / Live2D / 数字人** | 沉浸感最强 | `DigitalHuman.vue` 已冻结（`is-frozen` 占位）；Electron CSP 严格、性能与体积风险 | 不建议纳入本期；如要重启数字人需单独评审 |

### 5.3 语义状态与驱动源

| 语义状态 | 主要驱动源 | 典型触发 |
| --- | --- | --- |
| `idle` / `sleeping` | 时间策略 | 空闲阈值、`prefers-reduced-motion` 下静止 |
| `listening` | 输入焦点 / 唤醒词 | 输入框聚焦、`/justin|贾斯汀/i`（复用落地页唤醒词） |
| `thinking` | 上行流事件 | `isStreaming` / `reasoning_*` / `thinkingState` |
| `working` | 下行 run 事件 | `step.started` / `planner.started` / `model.activity` |
| `happy` | 终态 | `run.completed` / 对话成功回复 |
| `alert` | 需人工介入 | `run.waiting_review` / `node.failed` / 审批请求 |
| `error` | 异常 | SSE `error` / `run.failed` / 请求失败 |

映射**只读** `chatStore.isStreaming / thinkingState / streamActivity` 与既有 SSE 事件，**不修改 `chatStore`**。若复用 TUI 的 6 情绪帧与中文对白池，也通过 `stateMap` 降级映射（8 → 6），不新写一套话术引擎。

### 5.4 加载与生命周期

1. `SkinRegistry.resolve(skinId)` → 校验 manifest（版本、体积上限、rendererType 支持、许可证）。
2. `SkinLoader.load()` → 动态 `import()` 或 HTTP 拉取 → `Map<skinId, renderer>` 缓存 → 超时/失败**降级到内置 SVG 皮肤**，永不阻塞主界面。
3. `CompanionHost.onMounted` 挂载、`onBeforeUnmount` 调 `renderer.destroy()`；参照 `WorkspaceContinuity.spec.ts` 的「unmount 后 streams === 0」约束，订阅与 SSE 必须成对释放。
4. 尊重 `prefers-reduced-motion`；动效 160–220ms，颜色一律用 `global.css` 的 `var(--*)`（遵守 `apps/frontend/brand-spec.md`：禁止新增彩色光晕与装饰性卡片）。

### 5.5 展示方式

- `<Teleport to="body">` + `position: fixed`，`z-index: 2100`（避开 `global-error-banner` 的 2000 与右键菜单的 3000）；参照 `AuthenticatedAppShell.vue` 的 Teleport 范例。
- 可折叠 / 拖拽 / 隐藏，位置与皮肤偏好存 `localStorage`（沿用 `layout.*` 命名）。
- **不做独立置顶窗口**：`apps/desktop/electron/src/main.ts` 是单无边框窗口并拒绝 `window.open`，置顶透明窗口要改 IPC 三处同构 + 安全基线，成本高。
- **语音降级**：Electron `hardenSession()` 拒绝所有 media 权限，`SpeechRecognition` 在打包版不可用；桌面端默认文字输入，语音功能需单独做权限白名单评审。

---

## 6. 对话功能

### 6.1 对话生成

- **轻量路径**：复用 `apps/agent/app/llm/gateway.py` 的 `LLMGateway.generate_text / generate_json`，自动继承激活供应商档案、超时与 `MODEL_TIMEOUT` 治理；**不新建模型配置、不建 ACG 图**。
- **流式**：`/ai/companion/messages` 返回 `StreamingResponse`，复用既有 `ChatStreamEvent` 帧格式（`event: ... / data: {...}` + heartbeat + done/error）与前端 `utils/sse.ts` 解析器；不新增第五套 SSE 协议。
- **人设**：`PersonaRegistry` 管理人设提示词模板与版本 hash，参照 `adapters/prompt_runtime.py` 的 `_trusted_system()` 做可信封装（系统提示与用户输入分离）；人设数据可复用 `roles` 的 `systemPrompt / personality / dialogueStyle` 字段。
- **既有先例**：`runtime/planning_interaction.py` 的 Copilot `stream_message()` 直接复用 `runtime._intent_llm`、不建图 —— 这就是「轻量对话」的合规样板。

### 6.2 上下文管理（三层，引用优先）

| 层 | 内容 | 落点与预算 |
| --- | --- | --- |
| **L1 工作记忆** | 当前会话滑窗：系统人设 + 最近 N 轮 + 当前意图与槽位 | 内存；按 token 预算裁剪，超限只保留摘要 |
| **L2 会话记忆** | 跨轮次/跨会话的历史消息与滚动摘要 | 优先 Java PostgreSQL 新增 `companion_sessions` / `companion_messages`（Flyway 新迁移），沿用现成的用户归属、JWT、备份链；或以 `run_copilot_exchanges` 追加模式落在既有 `workflows.sqlite3`。**独立 session id，不污染主 Chat 的 `contextId`** |
| **L3 任务锚点** | `{ runId, missionId, summary, outputRef }` 引用 | 只存引用与摘要；需要正文时经 `/runs/{id}/outputs/{outputRef}` 现取，绝不复制进 prompt 或气泡（ADR-001） |

- 压缩策略：每轮结束生成滚动摘要；跨会话只注入「摘要 + 用户偏好 + 最近任务锚点」，不注入完整历史。
- **不推荐新建独立 SQLite 库**：需同步改 `wiring.py` 的 `_DEFAULT_DATABASES` 与 close 序列、`native_runtime.py` 的 `DBS`、N03 冷备份清单、迁移脚本共 4 处，且属于 CONTRACT_EVOLUTION 评审范围。

### 6.3 多场景意图识别（分级 + 可降级）

```
输入 + UI 上下文（当前 runId、当前视图、最近任务锚点）
   ↓ ① 规则层（零模型、确定性）
唤醒词 / 显式命令 / 正则（"进度"、"到哪一步了"、"帮我跑一个…"）→ 直接定意图 + 抽槽
   ↓ ② 轻量模型层
LLMGateway.generate_json(prompt, schema) → IntentResult
   ↓ ③ 兜底层
低置信度 / 模型超时 / 非法 JSON → small_talk + 澄清反问；不阻断对话
```

`IntentResult` 固定 schema：

```json
{
  "intent": "progress_query | task_dispatch | small_talk | emotional_support | system_control | unknown",
  "confidence": 0.0,
  "slots": { "runId": "", "timeRange": "", "detailLevel": "", "title": "", "domain": "", "intent": "" },
  "needsConfirmation": true,
  "reason": ""
}
```

- **与既有意图链的关系**：宠物层只做**用户话语层**的浅分类（「这句话想干嘛」），不重复实现 `IntentParser` → `TemplateMatcher` → `CognitiveRouter` 的**任务规划层**语义。真要分发任务时，把 `domain/intent` 作为标准参数交给既有链，由 `PluginScopeResolver` 决定插件作用域。
- **确定性回落**与内核 `IntentParser` 的 heuristic 回落哲学一致：模型故障不阻断陪伴体验。
- **场景注册表**：`SceneRegistry.register(intent, handler)`；新增场景 = 新增一个 handler + 一条 manifest 声明，不改 `CompanionService`。

### 6.4 四类场景的职责

| 场景 | 处理链路 | 输出 |
| --- | --- | --- |
| **工作进度问询** | `ProgressPort` 读 `project_run()` 的结构化状态（同进程或只读投影，零 HTTP 开销）→ 轻量模型改写为自然语言 → 需要细节时列 `/graph`、`/checkpoints`、`/trace` 引用 | 摘要气泡 + 引用卡片；实时推进由前端订阅既有 `/runs/{id}/events` SSE |
| **基础聊天** | `ChatPort` + 人设 + L1/L2 上下文 → 流式回复 | 迷你气泡（复用 `utils/markdown.ts` 渲染）；不写主 Chat 会话 |
| **情感陪伴** | `EmotionPolicy`（情绪状态机 + 空闲/时长触发）+ 既有 `/emotion/analyze`、`/emotion/response`、`/api/recommendations/contextual` + 中文对白池 | 关怀话术 + `happy/idle` 状态；所有主动话术经节流队列 |
| **任务分发** | 意图卡 → **用户确认** → 转交既有统一启动入口 | 见下 |

**任务分发的约束（重要）**：宠物**不自己发任务**。推荐做法是「意图卡 → 深链跳转」：把 `{title, domain, intent, input}` 交给已存在的 Mission Launcher UI（PR-UI-01 统一启动合同），由用户在既有界面确认后按既有 `clientRequestId` 幂等链路提交。原因有三：

1. `features/mission/architecture.spec.ts` **全量扫描** `src/**/*.{ts,vue}`，禁止在 `views/`、`stores/` 及未白名单文件中出现 `startWorkflowAsync(`、`POST '/missions'`、`prepareMissionLaunch` 等字面量；宠物层不得成为第四条启动路径。
2. Python 服务不持有用户 JWT，让它代发 `POST /api/agentos/v2/missions` 会绕回 Java 鉴权边界，身份链被破坏。
3. 既有 `clientRequestId` + 请求体指纹的幂等/409 对账语义必须保持单一来源。

### 6.5 主动播报与打扰控制

- 前端订阅既有 `GET /runs/{runId}/events`（`workbench/runtime/runtimeEvents.ts` 已有断线重连且不重提命令的范式），把 `planner.* / node.* / step.* / run.*` 映射为语义状态与话术。
- `ProactivityQueue` 做**去重 + 节流 + 优先级**：`run.failed / waiting_review`（最高）> `run.completed` > 阶段进度 > 闲时关怀（最低）。
- 事件是 transient 且可丢弃的，关键生命周期事件不可丢；**不得把正文、密钥写进事件 payload**（`live_events.py` 已剥离 `model.completed` 的 `data`）。
- 项目无 webhook，不假设服务端能回调推送。

---

## 7. 集成方案：最小侵入路径

### 7.1 契约与挂载点

| 项 | 结论 |
| --- | --- |
| 对外接口 | 只新增 `/ai/companion/*`（PLATFORM_AI 透传）。`AiServiceProxyController` 的 `/ai/**` 与 `vite.config.ts` 的 `/ai` proxy 已覆盖任意新路径，**Java 与前端代理零改动** |
| 禁止 | 不在 `/api/agentos/v2` 下新增 Controller：`ArchitectureGuardTest` 精确断言该前缀 Controller **恰好 6 个**，新增会直接构建失败；也不新增控制面契约 json（既有 5 个是 Mission/Run/Review/Retry/Error 契约） |
| 传输 | 仅 SSE；`ArchitectureGuardTest` 全仓禁止 WebSocket / STOMP / SockJS，上游 SSE 只能经 `AiSseGatewayService` |
| 鉴权 | Java `SecurityConfig` 状态无关 JWT + 全局 `WebClientConfig` 注入 `X-Internal-Service-Token` / `X-Authenticated-*`；Python `InternalServiceAuthMiddleware` 自动校验并提供 `TrustedUserContext`。新 router 内只用 `current_trusted_user()` / `current_semantic_principal()`，绝不信任客户端传入的 user/tenant |
| 前端挂载 | `App.vue` 中 `<ZoomIndicator />` 同级新增 `<CompanionHost v-if="!isPublicRoute" />`，用 `defineAsyncComponent` 懒加载。**必须用 `isPublicRoute` 守卫**：`App.spec.ts` 断言公开路由下不得实例化 `chatStore` / `workflowRuns.bootstrap()` |
| 工作区内可选挂载 | 若只需要在 Mission Workspace 内出现，走 `workbench/composition.ts` 的 `auxiliaryViews` 贡献点（仿 `contributions/copilot/index.ts`），完全不改 `App.vue` |
| 请求实例 | 复用 `utils/request.ts` / `services/api/agentos/client.ts`；**不新建第 4 个 axios 实例**；SSE 用 `apiUrl()` + Bearer + `getReader()` 既有范式 |
| 事件通信 | 沿用 `window` CustomEvent（`global-error` / `history-refresh` 等既有约定），**不引入 mitt 等事件库** |
| 测试 | 新增组件同目录补 `*.spec.ts`（jsdom + vitest，`data-testid` / `aria-*` 断言，`createPinia()` + `vi.mock` 隔离）；Python 侧补 router 契约测试；Java 侧不动 |

### 7.2 必须绕开的守卫（对照表）

| 守卫 | 位置 | 新增模块的自律规则 |
| --- | --- | --- |
| 冻结 6 个 AgentOS Controller | `backend/.../ArchitectureGuardTest.java:184-204` | 不新增 `/api/agentos/v2` Controller |
| Mission 启动字面量全量扫描 | `frontend/src/features/mission/architecture.spec.ts` | 新 `.vue`/`.ts` 不出现 `startWorkflowAsync(`、`'/missions'`、`prepareMissionLaunch` 等 |
| 公开路由 store 隔离 | `frontend/src/App.spec.ts` | `v-if="!isPublicRoute"` + 动态 `import('@/stores/chat')` |
| 流式生命周期 | `WorkspaceContinuity.spec.ts` | unmount 后订阅数归零 |
| 通用层不得反向依赖具体实现 | `frontend/src/plugins/registry.spec.ts` | companion 不 import `plugins/legal|industrial` 等 |
| SSE-only / 禁 WebSocket | `ArchitectureGuardTest.java:322-343` | 只用 `text/event-stream` |
| Python 平铺顶层包布局 | `native_runtime.py` 的 `PYTHONPATH` | 用 `from app.companion...`，不自建嵌套顶层包 |
| 品牌视觉门禁 | `frontend/brand-spec.md` | `var(--*)` 令牌、无新增光晕/装饰卡片、160–220ms 动效 |

### 7.3 分阶段落地

| 阶段 | 交付 | 存量改动 | 验收要点 |
| --- | --- | --- | --- |
| **P0 只读陪伴** | 抽出 `CompanionHost.vue` + `AvatarRenderer`（复用 Grok 引擎）+ 语义状态机；基础聊天复用 `chatStore` 懒加载流；订阅既有 run events 做表情/播报 | `App.vue` **1 行** + 新增 2 个前端目录内文件与 spec；**零后端改动** | `App.spec.ts`、`GlassConstellation.lazyStore.spec.ts`、`WorkspaceContinuity.spec.ts` 保持全绿；公开路由不加载角色 |
| **P1 独立对话域** | 新增 `app/companion/` + `/ai/companion/messages` SSE；`IntentRouter` + `ContextManager` + `ProgressScene` + `ChatScene` | `main.py` **1 行**；PostgreSQL Flyway 新迁移（或复用 Copilot exchange 追加表） | Java 架构守卫、Python 契约测试、前端 vitest 全绿；`/ai/**` 透传链路打通；身份头正确 |
| **P2 任务分发确认卡** | `DispatchScene` 产出意图卡 → 深链交给既有 Mission Launcher | 视深链实现，可能 1 个路由参数 | 零误触发；重复点击不产生双 run；`clientRequestId` 409 对账语义不变 |
| **P3 皮肤体系 / 语音 / 多端** | `SkinRegistry` 多皮肤、Lottie 渲染器、TUI 情绪帧复用、桌面语音 | Electron 权限白名单需**单独安全评审** | 资源体积预算、降级路径、双端一致 |

### 7.4 目录建议（新增文件全部落在 3 个新目录）

```
apps/frontend/src/
├── features/companion/          # 纯逻辑：state / intent card / ports / policy
│   ├── companionState.ts
│   ├── ports.ts
│   └── adapters/               # 只读投影、SSE 订阅、深链适配
├── components/companion/        # UI：Host / DialoguePanel / TaskIntentCard
└── public/companion/skins/      # 皮肤 manifest 与资源（P3）

apps/agent/app/companion/        # 独立 Python 包
├── __init__.py                  # create_router(ports=...)
├── service.py                   # 薄编排
├── intent.py                    # 分级识别 + schema
├── context.py                   # 三层上下文
├── scenes/                      # 每个意图一个 handler
├── ports.py                     # Protocol 定义
├── adapters/                    # Port 实现（只调用既有能力）
└── store.py                     # 会话持久化（复用既有表）
```

---

## 8. 风险与待决问题

| # | 风险 / 待决 | 建议 |
| --- | --- | --- |
| 1 | **两套对话并存**（Chat / Copilot / Companion）导致用户认知分裂 | 明确产品边界：宠物只做「轻问询 + 陪伴 + 意图卡」，复杂任务一律引导到 Workbench；不复制完整聊天能力 |
| 2 | 上下文落库选 Java PG 还是 Python SQLite | 倾向 **Java PG**（用户归属、Flyway、备份现成），但需新增一个普通 `/api` Controller，须遵守 `controller → service → client` 分层守卫；若追求零 Java 改动，退到 Python `run_copilot_exchanges` 追加模式 |
| 3 | `project_run()` 定义在 `app/api/agentos_v2.py` 内部，直接 import 会造成 API 层耦合 | 通过 `ProgressPort` 注入只读投影函数；必要时把该投影函数提升为独立只读模块（纯内部重构，不改契约） |
| 4 | 主动播报打扰用户 | 优先级队列 + 节流 + 可关闭开关，默认只对失败/待审核/完成三类主动发声 |
| 5 | 形象资源体积与 Electron CSP | 默认程序化 SVG 零资源；外部皮肤设体积上限、懒加载、静态兜底 |
| 6 | 语音在 Electron 打包版不可用 | 文字降级；权限白名单走安全评审，不暗中放宽 `hardenSession()` |
| 7 | 早期架构文档（`02-`、`05-`）目录树已过时 | 以 `apps/agentOS/README.md` 与当前源码为准，不按旧文档目录新建文件 |
| 8 | 文档治理 | 本文已登记 `docs/README.md` 架构设计索引；**实施后**须在 `开发记录/` 补阶段证据，并同步 `开发记录/README.md`（本文未实施，故不在该索引留下虚假记录） |

### 验收标准（可量化）

1. **拔插性**：删除 3 个 companion 目录 + 2 行注册后，既有测试套件全部保持原结果。
2. **依赖方向**：静态扫描 `app/companion/` 与 `features/companion/`，不得出现 `runtime.workflow_runtime`、`prepare_run`、`coordinator.submit`、`compiledACGPackage`、`startWorkflowAsync` 等内核/启动符号。
3. **契约零漂移**：`contracts/agentos-v2/*.json` 5 个文件不改；Java 6 Controller 断言不变；前端 architecture guard 不变。
4. **功能**：四类意图各 20 条样例，意图准确率与兜底率达标；任务分发**必须**经过确认卡，误触发为 0。
5. **性能**：首屏形象资源 ≤ 200KB（默认皮肤为 0）；空闲态 0 轮询；播报节流后不高于 N 次/分钟（阈值产品定）。
6. **安全**：气泡与事件 payload 不含 task input / ContextPack / 模型正文 / 密钥；所有请求经 Java JWT 边界。

---

## 9. 一句话总结

> 把散落在落地页、TUI 与 Copilot 里的角色能力，收编成一个**只依赖端口协议、只读消费投影、经既有统一入口提交任务**的独立 Companion 能力域；它挂在 `App.vue` 的一行和 `main.py` 的一行上，可以整体拔掉而不惊动执行内核 —— 这就是本项目语境下「低耦合」的可验证含义。
