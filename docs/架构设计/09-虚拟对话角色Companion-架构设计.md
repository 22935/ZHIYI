# 09 · 虚拟对话角色（Companion）架构设计

> **状态**：部分实施（P0 前端能力域 + P0+ 桌面封装 / 养成互动已落地；P1 ~ P3 仍为设计草案 / 待评审）
> **日期**：2026-11-05（初稿）· 2026-11-06（P0+ 更新）· 2026-11-07（运行验证与布局修复）· 2026-11-08（语音优先 / DIY 形象）
> **适用平台**：Windows 11 原生持久栈（N03），Web（Vite dev）与 Electron 桌面双端
> **验证范围**：源码静态架构核对 + 前端 vitest / vue-tsc、桌面 node --test、esbuild 打包解析、agentOS 桌面执行边界门禁 + **无头 Chromium 真实渲染与语音链路验证**；**未启动真实后端做端到端联调**，未做性能实测
> **结论状态**：PARTIALLY IMPLEMENTED。§2 ~ §8 中关于 P1 ~ P3 的内容仍是架构建议，不作为「当前基线」
> **实施进度（2026-11-08 更新）**：见文末「10. P0 实施记录」、「11. P0+ 桌面封装与养成互动实施记录」、「12. 运行验证与布局修复」与「13. 语音优先交互与 DIY 形象实施记录」。
> **文档性质**：架构决策建议 + 实施记录。按 `docs/README.md` 维护约定归入 `架构设计/`；后续阶段验收证据另行写入 `开发记录/`。

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

---

## 10. P0 实施记录（2026-11-05）

**范围**：只做前端接入层，**零后端改动**；`main.py` 未改，`/ai/companion/*` 尚未创建，Java / Vite / Electron / Chat API 全部未动。存量改动仅 `App.vue` 两处（一行挂载 + 一个 `defineAsyncComponent`）。

### 新增文件

| 位置 | 内容 |
| --- | --- |
| `apps/frontend/src/features/companion/types.ts` | `CompanionState` / `SceneId` / `SkinManifest` / `AvatarRenderer` / `ChatPort` / `ProgressPort` 等协议 |
| `companionState.ts` | 状态优先级、运行时事件→语义状态映射、`ProactivityQueue`（去重/节流/优先级）、`IdleFallback` |
| `skins.ts` / `renderers.ts` | 皮肤清单与 `stateMap`、内置轻量 SVG 渲染器、按需动态加载的 Grok 引擎渲染器与失败降级 |
| `intent.ts` / `dialogue.ts` | 规则层六类意图识别与槽位、引用优先的进度摘要、本地话术 `ChatPort`、任务意图卡 |
| `companionService.ts` | 薄编排与默认端口装配 |
| `adapters/progress.ts` | 复用 `workflowApi.getWorkflowProgress` 只读投影 |
| `adapters/chatStream.ts` | **可选**真实模型通道：复用既有 SSE 帧协议 + 独立 `context_id`，默认不启用 |
| `components/companion/CompanionHost.vue` | `Teleport` 全局浮层、皮肤切换、事件订阅与生命周期清理 |
| `components/companion/CompanionDialogue.vue` | 迷你对话、快捷意图、任务意图卡 |
| 5 个同目录 `*.spec.ts` | 意图、状态机、皮肤注册、服务编排、宿主组件 |

### 与原设计的两处诚实偏差

1. **默认皮肤改为内置轻量 SVG，Grok 引擎降级为可选皮肤**。原因：`lib/grok-character/index.js` 顶层访问 `window` 且依赖 SVG 运行时，若静态导入会污染 `App.spec.ts` 等纯 jsdom 测试环境。改为按需动态加载 + 失败降级到静态皮肤，既保住可拔插性，也让首屏资源为 0。
2. **P0 的模型回复复用既有 `/ai/chat/text/stream`，但使用独立 `companion:*` context_id，且默认关闭**。这是 P1 专用端点落地前的过渡通道；**未改动该 API 本身**，但启用后会在 Java `conversations` 表留下会话记录，产品上需要决定是否过滤。P1 应替换为 `/ai/companion/*` 并移除此适配器。

### 验证结果（2026-11-05，Windows / N03 前端栈，未跑真实后端）

| 项目 | 结果 |
| --- | --- |
| 新增 5 个 spec | **29 项全通过**（意图 11 / 状态机 5 / 皮肤 4 / 服务 6 / 宿主 3） |
| `App.spec.ts` | **10 项全通过**（含公开路由不得实例化 `useChatStore` 的断言） |
| `features/mission/architecture.spec.ts` | **3 项全通过**（新文件未触发启动字面量全量扫描） |
| 前端完整套件 | **1113 项通过**；8 个测试文件在收集阶段失败，均为既有依赖缺失（`@codemirror/*`、`@xterm/*`、`@vue-flow/core`、`motion-v`），与本次改动无关 |
| `vue-tsc --noEmit` | **companion 相关 0 错误**；剩余报错全部是上述既有依赖缺失 |
| `ChatView.spec.ts` 单独复跑 | 38 项通过，另 2 个 `Unhandled Rejection` 为既有 flaky，单独运行同样出现，与 companion 无关 |

> 运行 `vitest` 时若报 `EPERM ... Temp\...\web\...`，是环境临时目录写权限问题；把 `TEMP` / `TMP` 指向项目内可写目录（如 `.tmp-tests/`）即可消除，与代码无关。

### 下一步（P1）

新增 `apps/agent/app/companion/` 与 `main.py` 一行注册，把 `ChatPort` 换成服务端实现；同时决定会话记忆落 Java PG（Flyway 新迁移）还是 Python 既有追加表，并把 `project_run()` 通过 `ProgressPort` 注入以避免 API 层直接耦合。P2 的任务确认卡已具备 UI，接入统一启动入口前须先通过 `features/mission/architecture.spec.ts` 的白名单评审。

---

## 11. P0+ 实施记录：桌面封装与养成互动（2026-11-06）

**范围**：在不碰后端、不碰执行内核、不改安全基线的前提下，把「能点开聊两句」补成真正可用的桌面宠物。仍然是**前端 + Electron 宿主**两侧改动，Java / FastAPI / Vite 代理 / Chat API 零改动。

### 11.1 桌面端封装：做了什么

| 能力 | 实现 | 约束遵守情况 |
| --- | --- | --- |
| 系统托盘 | `main.ts` 新增 `Tray`，tooltip 显示状态 / 等级 / 好感 / 免打扰；菜单固定文案：叫一声知宝、查看当前进度、免打扰勾选、显示主窗口、退出 | **不建第二个 BrowserWindow**；`authorized()` 仍绑定唯一 `mainWindow.mainFrame`；`window-all-closed → app.quit()` 语义不变 |
| 托盘 → 渲染层 | 新通道 `kinlin:companion/tray-action`（Main → Renderer），preload 用 `TRAY_ACTIONS` 固定白名单收窄动作后才回调 | 不暴露 `ipcRenderer` 本体；渲染层不接收任意字符串 |
| 渲染层 → 托盘 | 新通道 `kinlin:companion/state`，`parseCompanionSnapshot()` 校验 8 个合法状态、有界文本、等级/好感数值收敛、严格布尔 | 每个 handler 保留 `guard(event)`；不改 IDE 13 个 handler 的既有形态 |
| 原生通知 | 新通道 `kinlin:companion/notify`；Main 依据**自身**判定的窗口焦点与已校验的免打扰快照决定是否弹 `Notification` | 复用既有原生通知能力，焦点判断放 Main（渲染层不可信）；标题/正文沿用 `parseBoundedText` 200/2000 限长 |
| 图标资源 | `apps/desktop/electron/icons/companion-tray.png`（32×32 RGBA），`build.mjs` 增加一行拷入 `dist/icons/`，随 `files: dist/**` 进 asar；图标缺失时托盘静默降级、不崩溃 | 不改 CSP、不加远程资源 |
| Web 降级 | `adapters/desktop.ts` 的 `createDesktopPort()`：无桥 / 旧版 preload 无 `companion` 命名空间 → 返回 no-op | Web 构建永不 `import 'electron'` |

**四处同构**（`ipc-contract.ts` → `preload.ts` → `main.ts` → `frontend/platform/electron/bridge.ts`）新增后，顺手补了 `test/companion-ipc.test.ts` 一致性门禁，把 PR-EL-01 登记的「手工同构」已知问题在这一组通道上变成可失败的断言。

**明确没做、且不建议偷偷做**：独立置顶/透明悬浮窗（会破坏单窗口授权模型，§5 已否决）；放宽 `hardenSession()` 以启用语音（全局权限策略，需独立安全评审）；`setLoginItemSettings` 开机自启（N03 已有外部启动器承担生命周期，且需产品授权）。托盘「退出」直接 `app.quit()`，**关闭主窗口仍是退出**，没有改成「最小化到托盘」——避免改变 N03 supervisor 观察到的进程语义。

### 11.2 趣味性与交互逻辑

新增 6 个纯逻辑模块 + 3 个 UI 组件，全部可注入时钟 / 随机数 / storage，便于确定性单测：

- **养成**（`pet.ts`）：好感度 → 12 级称号、精力随时间衰减、连续来访天数（本地日历日，跨月/跨年正确）、8 个成就；摸头 1.5s / 点心 5min / 玩耍 90s 冷却**只挡刷数值不挡回应**（仍给一句俏皮话）。localStorage 内容一律经 `sanitizePetProfile()` 收敛，脏数据不会污染 UI。
- **心情与闲时**（`idleBehavior.ts`）：由状态 / 精力 / 时段 / 最近互动派生心情；只在 `idle|happy|sleeping` 且空闲 45s 后按节流随机搭话，15min 后打盹；免打扰、后台标签页、思考/告警态一律不插嘴。
- **互动反馈**：点角色是「叫它过来 / 让它退下」，**不占摸头冷却**（否则展开面板后立刻点「摸摸头」会被判成刷数值——这是实现中发现并修掉的真实交互缺陷）；摸头/喂食/玩耍有浮动气泡、`+N 好感`、表情变化与成就提示；告警/思考/跟进中不被开心表情打断。
- **拖拽**（`position.ts`）：位置按「角色右下角到视口右下角的距离」记录，**面板永远向上、向左生长**；早期按根节点 `top/left` 锚定会导致角色拖到屏幕下方后展开面板溢出，已修正；越界夹回边缘并持久化。
- **桌面联动**：Ctrl/Cmd+Shift+K 唤起、Esc 收起；托盘「查看当前进度」直接发进度问询（仍走只读投影）；高优先级运行事件在窗口未聚焦时弹原生通知；长时间离开后回到窗口有回归问候；免打扰同时关闭闲聊与原生通知，并同步到托盘勾选态。
- **动效**：CSS `bob` / `wiggle` / 气泡过渡，告警环、睡眠 z z Z、按钮按压反馈；全部遵守 `prefers-reduced-motion`；卸载时清理 interval、timeout、事件与渲染器，`destroy()` 对称。

> 养成状态是**本地展示层数据**，只写 localStorage，不进任何后端 Store，不参与任务执行，不改变进度投影真相。任务分发仍只出意图卡、不提交。

### 11.3 验证结果（2026-11-06，Windows / N03 栈，未启动真实后端）

| 项目 | 结果 |
| --- | --- |
| 前端 companion + 关键守卫 | **75 项全通过**（12 个 spec；含 `App.spec.ts` 10 项与 `architecture.spec.ts` 3 项） |
| 前端完整套件 | **1165 项通过**；8 个测试文件在收集阶段失败，均为既有依赖缺失（`@codemirror/*`、`@xterm/*`、`@vue-flow/core`、`motion-v`），与本次改动无关 |
| 桌面 `node --test` | **52 项全通过**（原 42 + 新增 10），含通道同构与安全基线回归断言 |
| `vue-tsc --noEmit` | companion / bridge 相关 **0 错误**；全量 27 条报错均为既有缺失依赖 |
| 桌面纯逻辑严格 tsc / esbuild 打包 main+preload | 均通过；桌面自身 `npm run typecheck` 因该目录未安装 `typescript`/`electron` 依赖而不可运行（**既有环境状态**，非本次引入） |
| agentOS 桌面执行边界门禁 | 通过（扫描 16 个 desktop TypeScript 源文件） |
| `components.d.ts` | 由 `unplugin-vue-components` 自动登记两个新组件，属正常生成物 |

### 11.4 遗留与下一步

1. **未做真实 Electron 端到端联调**：托盘图标、原生通知与 `second-instance` 恢复需要在打包/运行环境人工走一遍；单测覆盖的是纯逻辑与通道同构。
2. **P1 仍未启动**：`/ai/companion/*` 专用端点、会话记忆落库选型、`project_run()` 的 Port 注入都还停在 §8 的两个待决点。
3. **P2 任务卡**仍未接统一启动入口；**P3 语音**仍受 `hardenSession()` 全拒权限约束，需单独安全评审。
4. 托盘事件若发生在渲染层订阅之前会丢失（当前只在页面就绪后才可能出现，风险可接受）；若后续要支持开机即播报，需引入一次「状态重放」握手。

---

## 12. 运行验证与布局修复（2026-11-07）

### 12.1 运行方式

- `npm run dev -- --host 127.0.0.1`（Vite web 模式，端口 **3000**）；**未启动 Java / FastAPI / PostgreSQL**，因此 `/api/*` 代理返回连接错误，路由守卫按「临时后端中断」放行，可进入认证态页面。
- 本地预览入口 `apps/frontend/companion-preview.html`：只写入一个占位 `token` 让前端进入认证态，随即跳转 `/chat`；**不参与生产构建**（Vite 只打包 `index.html`），不调用后端、不授予任何真实权限，正式使用仍走正常登录。
- 用无头 Chromium + CDP 做真实渲染与交互（导航、点击、输入、拖拽、皮肤切换、截图、控制台错误采集），而非仅靠 jsdom 断言。

### 12.2 实测通过的功能链路

| 场景 | 实测结果 |
| --- | --- |
| 认证态挂载 | `CompanionHost` 挂到 `body`，`z-index: 2100`，默认 `idle`，右下角；公开路由 `/`、`/login` 不加载 |
| 展开面板 | 状态标签、Lv / 心情 / 连续天数、好感与精力条、3 个互动按钮、4 个快捷意图、输入框、模型回复 / 免打扰 / 皮肤下拉、皮肤两张（`轻量 SVG`、`动效 SVG`） |
| 养成互动 | 摸头 → `happy` + `+1 好感` + 成就徽章「初次见面」；喂食 / 玩耍改变好感、精力与心情；气泡文案正常 |
| 对话与意图 | 进度问询（无运行 → 明确兜底，不编造进度）、情感陪伴闲聊、任务分发**只出意图卡且注明不提交**；消息区滚动正常 |
| 皮肤 | 切到 `动效 SVG` 时 Grok 引擎按需动态加载成功、不崩；`thinking` 态的「三点」是引擎既有 `fx.js` 设计，非加载失败 |
| 桌面通道 | 只做了前端 no-op 降级路径验证；**托盘 / 原生通知仍未做真实 Electron 端到端联调** |

### 12.3 运行中发现并修掉的 4 个真实效果缺陷

1. **小窗口 / 长对话时面板顶部溢出**：面板原先没有高度上限，消息与意图卡累积到 700px 高，在 746px 视口下 `y = -101`。改为 `.companion-panel` 按 `--companion-bottom` 计算 `max-height` 并内部滚动，消息区改成 `clamp(88px, 22vh, 208px)`；实测 1200×700 + 12 条消息时 `panelInside = true`，输入行仍可见。
2. **拖到屏幕左侧后展开，面板向左溢出**：root 以 `right` 锚定，收起态宽 76、展开态宽 320，靠左拖拽时展开后 `x = -82`。新增 `clampExpandedPosition()`，在**展开 / 松手 / 窗口 resize / 刷新后记住展开态**四条路径上自动把角色平移回有完整面板空间的位置，并配一句拟人化气泡「我往里挪了挪，这样面板能看全～」；**收起态仍可自由拖拽**。
3. **拖到屏幕上方时面板被压成一条**：仅做高度限制会把面板压到 108px，输入区要滚动才看得到。把 `PANEL_RESERVE` 定为 `240（面板最小可用高度）+ 132（头像/气泡/间距）= 372`，配合 CSS `max(240px, …)`，实测拖到上限后面板仍有 240px 且完全在视口内。**取舍**：拖拽纵向范围被限制在「上方仍有面板空间」的区域，避免跳位与不可读。
4. **表情偏冷 / 思考态像加载中**：`idle` 改成微微笑嘴，`thinking` 从三个点改成「挑眉 + 圆眼 + 小弧嘴」，更像在琢磨而不是转圈。

同时补了 `resize` 监听，窗口缩小后按当前展开态重新夹取位置；`onPointerUp` 抽成 `writePosition()` 复用。新增 4 项单测覆盖高度预留、展开避让、刷新恢复与拖拽持久化。

### 12.4 环境问题（非代码缺陷）

- 仓库 `node_modules` 缺 `@codemirror/*`、`@xterm/*`、`@vue-flow/core`、`motion-v` 等既有依赖，Vite 启动即报解析失败；已 `npm install` 补齐，并把 `package-lock.json` 的副作用**回滚**，未改动依赖声明。补齐后原先「收集阶段失败」的测试文件可正常运行，全量套件规模从 1165 增至 1255。
- Vite 清理 `node_modules/.vite/deps*` 时被本机 Node 删除保护拦截而退出；启动 dev server 时仅对该进程设 `CODEBUDDY_SAFE_DELETE_ENABLED=0`，缓存目录先移走备份，**未改项目配置、未放宽全局安全策略**。

### 12.5 本次验证结果

| 项目 | 结果 |
| --- | --- |
| 前端 companion + `App.spec.ts` + 架构守卫 | **79 项全通过**（12 个 spec，含新增 4 项） |
| 前端完整套件 | **1254 / 1255 通过**；唯一失败为 `src/views/MissionLifecycle.integration.spec.ts:218` 的 `.workspace-lifecycle button` 断言，单跑同样失败。该文件与相关视图**本轮均未改动**，属依赖补齐后首次可收集暴露的既有用例问题，与 Companion 无关 |
| 桌面 `node --test` | **52 项全通过** |
| `vue-tsc --noEmit` | companion / 预览入口相关 **0 错误** |
| 真实浏览器渲染 | 全屏与右下角特写截图、控制台仅 1 条「加载用户信息失败」（后端未启动的预期错误），**无页面级异常** |

### 12.6 仍需人工确认

真实 Electron 打包环境下的托盘图标、原生通知与 `second-instance` 恢复；以及上表那条既有的 `MissionLifecycle.integration.spec.ts` 失败用例，建议单独定位，不要与 Companion 改动混在一起修。

---

## 13. 语音优先交互与 DIY 形象实施记录（2026-11-08）

### 13.1 需求变更与边界

用户要求：**取消文字输入**，改为语音对话与语音控制；**保留**养成互动机制；补强**动效**；角色要**能发出声音**；形象要**可 DIY、可自定义**。

实现仍严格落在接入层能力域：**零后端改动、零新增 IPC 通道、不改 `hardenSession()`、不建第二个 BrowserWindow、不碰 ACG 执行内核**。文字输入框被移除，但快捷指令按钮保留——它是语音不可用时的兜底「控制」入口，不是打字入口。

### 13.2 新增 / 改造模块

| 文件 | 职责 |
| --- | --- |
| `features/companion/voice.ts` | `VoicePort` 实现：`VoiceEngine` 状态机、浏览器 ASR/TTS 适配、能力探测、错误文案、`toSpokenText` 朗读清洗；浏览器 API 全部经 `VoiceHost` 注入，可完整单测 |
| `features/companion/speechCommands.ts` | 14 条口语化控制命令（收起 / 免打扰 / 静音 / 别说了 / 换形象 / 回右下角 / DIY / 摸头等），带优先级与语音确认话术 |
| `features/companion/customization.ts` | DIY 数据模型、净化、本地持久化、JSON 导入导出、5 套预设、DIY manifest 生成 |
| `components/companion/CompanionVoiceBar.vue` | 麦克风按钮、实时波形、识别字幕、朗读开关；**无任何文本框** |
| `components/companion/CompanionCustomizer.vue` | 形象工坊：名字 / 轮廓 / 三色 / 图片 / 台词 / 语速音调音量 / 动效 / 导入导出 |
| `features/companion/renderers.ts` | 新增 `DiySvgRenderer`（5 种轮廓、自定义配色、图片裁剪、腮红高光）；三种渲染器共用 `createFace()` 表情层 |
| `features/companion/types.ts` / `skins.ts` | `SkinManifest` 增加 `diy-svg` 与 `custom`；`SkinRegistry.upsert()` 支持运行时重建 DIY manifest |
| `dialogue.ts` / `companionService.ts` | `LocalChatPort(customSmallTalk)`；自定义台词只覆盖闲聊，不改进度与任务反馈 |
| `CompanionDialogue.vue` / `CompanionHost.vue` | 移除输入表单，接入语音、命令、DIY、粒子与状态动效 |

### 13.3 语音链路与权限事实

- **听（ASR）**：Web Speech API `SpeechRecognition`，`zh-CN` + `interimResults`，15s 超时保护；`not-allowed` / `no-speech` / `network` 等错误码统一收敛成中文提示。识别结果先过 `matchCompanionCommand()` 做界面控制，未命中才进入既有 `CompanionService` 意图编排。
- **说（TTS）**：`speechSynthesis` + `SpeechSynthesisUtterance`，优先挑中文音色，语速 / 音调 / 音量 / 静音由 DIY 配置驱动。**TTS 不需要任何 media 权限**，因此 Electron 的 `hardenSession()` 全拒策略不影响朗读。
- **降级是诚实的**：ASR 在 Electron 宿主里可能被媒体权限策略与内置识别能力限制，UI 会明确提示「这里不能语音输入」，并给出三条可用路径——快捷指令按钮、系统语音输入（Win+H）、面板展开时按 `R`；**不会假装在听**。Web 端 Chrome 157 实测 `SpeechRecognition`、`speechSynthesis`、`SpeechSynthesisUtterance` 齐备且有 22 个可用音色。
- **朗读时机**：只在用户手势后的互动、回复与命令确认时发声；页面加载的 `visit` 与长时间离开的回归问候**不自动出声**（浏览器本来也会拦截无手势的朗读，避免 `speaking` 状态卡住）。免打扰 / 静音 / 模型不可用时均静默，文字与气泡照常。
- **朗读清洗**：去 markdown 与链接、**保留括号内实质信息**（换成一次停顿）、剔除「（+N 好感）」这类只给眼睛看的数值附注、最长 160 字。

### 13.4 DIY 形象

- 仍是 manifest 驱动：业务层只发 8 个语义状态，DIY 皮肤用恒等 `stateMap`，外观全部由 `custom` 决定；换形象不改任何业务逻辑。
- 支持：自定义名字、5 种轮廓（圆 / 方团子 / 水滴 / 星星 / 软乎乎）、主色 / 点缀 / 底色、5 套预设、上传图片（仅 PNG/JPEG/WebP/GIF，原图 ≤ 4MB，canvas 压到 256×256，localStorage 字符上限 700k）、专属闲聊台词（≤ 6 条）、语速 / 音调 / 音量、动效开关、JSON 导入导出。
- 安全净化：颜色必须是 6 位 hex，图片必须是位图 dataURL（**禁用 SVG/HTML 防注入**），名字 ≤ 12 字、台词 ≤ 60 字并去控制字符，所有数值 clamp。配置**只写 localStorage**，不上送后端。
- 自定义名字贯通面板标题、托盘 tooltip 与对话上下文；形象工坊采用**编辑模式**（与养成区互斥、内部独立滚动、sticky 保存栏），关闭后养成数值、消息与语音状态原样保留。

### 13.5 动效

说话口型 4 帧轮换、收音 / 说话光晕环、随机眨眼、呼吸浮动、互动粒子（✦ / ★）、面板入场过渡、语音波形条、状态色外发光。全部遵守 `prefers-reduced-motion`，所有 `setInterval` / `setTimeout` 在 `destroy()` / `onBeforeUnmount()` 对称清理。

### 13.6 桌面封装联动

`TRAY_ACTIONS` 增加 `voice`，托盘菜单新增「听我说话」，Main 先 `restoreMainWindow()` 再下发动作；`CompanionSnapshot` 增加**可选** `name` / `voice`，tooltip 显示自定义名字与「正在听 / 正在说」。老版本渲染层不带这两个字段时 `parseCompanionSnapshot()` 的返回结构不变，向下兼容。**复用既有 `companionState` / `companionTrayAction` 通道，未新增通道、未放宽权限、未破坏单窗口模型。**

### 13.7 运行验证中发现并修掉的 3 个真实缺陷

1. **朗读把养成数值念出来**：气泡里的「（+1 好感）」被念成「加一好感」。`toSpokenText()` 增加数值附注剔除，同时把「括号整段删除」改为「括号换成停顿」——后者原本会丢掉「去工作台看看」这类关键提示。
2. **页面加载自动抢读**：`onMounted` 的 `visit` 互动会触发朗读，而浏览器要求用户手势，导致 `speaking` 状态挂到超时。给 `interact()` 增加 `speak=false`，自动问候只出气泡。
3. **工坊保存按钮被双层滚动藏住**：工坊与养成区同处 `.companion-panel` 的滚动容器，小窗口下「保存形象」落在裁剪区外。改为工坊模式互斥渲染 + 工坊自身滚动 + `position: sticky` 保存栏；1200×700 实测 `saveVisible = true`、`panelInside = true`。

### 13.8 验证结果

| 项目 | 结果 |
| --- | --- |
| 前端 companion + `App.spec.ts` + 架构守卫 | **130 项全通过**（18 个 spec；新增语音 12 / DIY 9 / 命令 17 / 语音与 DIY 集成 5 / 组件 8 项） |
| 前端完整套件 | **1305 / 1306 通过**；唯一失败仍是 `MissionLifecycle.integration.spec.ts:218` 的既有 `.workspace-lifecycle button` 断言，本轮未改该文件 |
| 桌面 `node --test` | **53 项全通过**（含托盘语音态、菜单动作与四处同构门禁） |
| `vue-tsc --noEmit` | companion / voice / customization **0 错误** |
| 无头 Chromium 真实渲染 | 无文字输入框、麦克风 / 波形 / 字幕齐备；语音识别 → 字幕 → 意图卡 → 朗读动效全链路通；DIY 改名换肤后星形紫色角色正常；1440×900 与 1200×700 面板均不越界 |

### 13.9 限制与后续

- **Electron 端语音输入仍受 `hardenSession()` 全拒媒体权限约束**，且打包版 Chromium 未必内置在线识别服务；当前提供的是明确降级与快捷键，不是桌面端离线 ASR。若要在桌面端完整语音输入，需要单独的安全评审 + 本地/服务端 ASR 方案。
- Web 端 ASR 依赖浏览器在线识别服务，离线或权限被拒时按上条降级。
- 真实 Electron 托盘「听我说话」的端到端联调、以及 P1 服务端对话域 / P2 任务卡提交 / P3 语音，仍未实施。
