# Chat 与 ACG Tool Calling 联网工具调用实施总结

> 完成日期：2026-07-30  
> 实施范围：Python AI 服务、AgentOS/ACG、Java Backend、Vue Frontend、Docker 开发与部署配置  
> 当前状态：共享只读工具运行时已完成；Chat 保留 Tavily 联网；ACG 在稳定性整改完成前暂停公网工具调用

## 1. 背景与问题

改造前，项目已经具备以下基础能力：

- AI 容器可以访问公网；
- DeepSeek OpenAI 兼容接口可以正常调用；
- 项目中存在一套自研 Tool Calling 代码和单元测试；
- ACG 可以在规划结果中传递 `allowedSkills`。

但真实业务链路仍存在关键缺口：

- `/chat/text` 与 `/chat/text/stream` 没有接入可执行的模型工具循环；
- ACG 只传递 Skill 元数据，没有按 Agent 权限裁剪的工具运行时；
- 程序员检索 Agent 返回模拟命中结果；
- 对需要证据的任务，系统可能在没有有效来源时继续生成结论；
- 前端不能展示工具状态、耗时和可点击来源；
- Java SSE 转发层不能完整持久化工具事件和来源。

本次工作的目标是让 Chat 与 ACG 真正具备受控、只读、可追踪的联网与工具调用能力，同时保留现有 ACG 规划器、图执行器、重试和治理架构。

## 2. 技术选型

### 2.1 模型工具循环

引入并锁定：

```text
openai-agents>=0.19.1,<0.20
```

使用 `OpenAIChatCompletionsModel` 连接现有 DeepSeek OpenAI 兼容接口，由 OpenAI Agents SDK 负责：

- 函数工具 Schema；
- 参数解析和校验；
- 多轮工具调用；
- 最大轮数；
- 流式事件；
- DeepSeek `reasoning_content` 回放；
- 工具调用结果继续送回模型。

DeepSeek Thinking 模式要求后续工具调用请求继续携带上一轮 `reasoning_content`。运行时通过 `should_replay_reasoning_content` 开启该能力，并启用流式工具调用缓冲，避免自行维护一套不完整的消息回放协议。

参考资料：

- [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Chat Completions Adapter](https://openai.github.io/openai-agents-python/ref/models/openai_chatcompletions/)

### 2.2 联网提供方

引入并锁定：

```text
tavily-python>=0.7.26,<0.8
```

Tavily 提供两个首期联网能力：

- `web_search`：搜索当前新闻、法规、价格、日程和其他时效性信息；
- `web_extract`：提取指定公开 HTTP(S) 网页的正文。

参考资料：

- [Tavily Python SDK](https://docs.tavily.com/sdk/python/quick-start)
- [Tavily API Reference](https://docs.tavily.com/documentation/api-reference/introduction)

## 3. 共享只读工具运行时

共享工具实现位于：

```text
agent/app/tools/
├── __init__.py
├── catalog.py
├── contracts.py
└── runtime.py
```

AgentOS 通过中立适配器接入应用层运行时：

```text
agent/app/integrations/tool_adapter.py
agentOS/src/agentos/adapters/tool_adapter.py
```

### 3.1 首批工具

| 工具 | 用途 | 来源/范围 | 是否只读 |
| --- | --- | --- | --- |
| `web_search` | 公网时效信息搜索 | Tavily | 是 |
| `web_extract` | 公网页面正文提取 | Tavily | 是 |
| `knowledge_search` | 本地知识库检索 | 项目已有 RAG | 是 |
| `codebase_search` | 当前项目代码检索 | AgentOS 代码索引 | 是 |
| `current_datetime` | 获取指定时区当前日期时间 | 系统时钟 | 是 |

未开放 Shell、文件写入、数据库写入、外部系统写入或任意 URL 工具注册能力。

### 3.2 统一契约

工具输出统一包含：

- `status`；
- `durationMs`；
- `inputSummary`；
- `outputSummary`；
- `errorCode`；
- `sourceRefs`；
- 经过裁剪的公开来源数据。

来源结构在保留 `title`、`filename`、`url`、`content` 兼容性的基础上增加：

- `provider`；
- `citationId`；
- `retrievedAt`。

网页完整正文只在服务端作为不可信证据参与模型处理，不直接传给前端，也不写入普通日志。

### 3.3 默认限制

| 项目 | 默认值 |
| --- | ---: |
| 单次模型运行最大轮数 | 6 |
| 单次运行最大工具调用次数 | 8 |
| 单工具超时 | 15 秒 |
| 搜索结果数量 | 最多 5 条 |
| 单次网页提取 URL | 最多 3 个 |

工具参数使用 Pydantic/SDK Schema 校验，并限制查询长度、URL 数量、正文大小和代码搜索范围。

### 3.4 安全边界

- 客户端不能传入工具地址、工具密钥或任意工具名称；
- `codebase_search` 只能访问 `TOOL_CODEBASE_ROOT` 配置的工作区；
- `web_extract` 只接受绝对 HTTP(S) URL；
- 拒绝 localhost、私网 IP、带账号密码的 URL 和非公网地址；
- 外部网页和工具输出被明确标记为不可信证据，不能覆盖系统指令；
- 日志只记录工具名、状态、耗时和来源数量；
- 不记录 API Key、完整网页正文或模型内部推理内容。

## 4. Chat 链路改造

主要实现：

```text
agent/app/api/chat.py
agent/app/llm/chat_stream.py
backend/src/main/java/com/kinlin/ai/service/AiService.java
backend/src/main/java/com/kinlin/ai/service/ChatService.java
backend/src/main/java/com/kinlin/ai/service/ChatStreamPersistenceService.java
frontend/src/services/api/chat.ts
frontend/src/stores/chat.ts
frontend/src/utils/sse.ts
frontend/src/components/MessageBubble.vue
```

### 4.1 请求行为

Chat 普通接口和 SSE 接口统一进入共享工具运行时：

- 默认 `toolMode=auto`；
- `toolMode=disabled` 时使用空工具作用域；
- 模型、基础地址和密钥继续由服务端配置管理；
- 客户端不能扩展工具白名单。

### 4.2 SSE 事件

新增事件：

```text
tool_start
tool_result
tool_error
```

原有内容、推理、用量和终止事件继续保留。最终响应和持久化消息中增加：

- `sources`；
- `toolsUsed`；
- `toolExecutions`；
- `executionSummary`。

Java Backend 负责透传 `toolMode`，持久化经过裁剪的工具记录和来源；Vue 前端负责显示工具名称、成功/失败状态、耗时和可点击来源链接。

### 4.3 能力检查

新增只读接口：

```text
GET /ai/chat/capabilities
```

该接口返回：

- 当前模型能力；
- 工具运行时是否启用；
- 各工具的 `available/provider/readOnly` 状态；
- 最大轮数和最大调用次数。

接口不会返回任何密钥。

## 5. ACG 接入

### 5.1 Tool 与 Skill 权限分离

`AgentProfile` 和绑定结构新增独立的 `allowedTools`：

```text
allowedSkills：声明专业能力/流程能力
allowedTools：声明运行时可执行工具权限
```

`AgentRunContext` 新增 `toolRuntime`。执行器按当前 Agent 和任务绑定裁剪工具作用域，Agent 不能在运行过程中自行扩大权限。

### 5.2 已接入 Agent

- 原生 `information_retrieval`；
- 法律法规/依据检索 Agent；
- 程序员代码库检索 Agent。

程序员 Agent 已删除模拟检索命中，改为调用真实只读代码索引，输出真实文件路径和行号。

### 5.3 证据与治理

每次工具调用都会：

- 生成现有 `TOOL_CALLED` Trace；
- 把来源引用写入 Evidence；
- 把 Evidence 引用写入 Provenance；
- 记录工具状态、耗时和错误码。

声明“必须有证据”的步骤在没有有效来源时会失败或进入现有重试机制，不再生成伪造的 `native://deterministic-source` 或模拟法规依据。

### 5.4 ACG 阶段性离线策略（2026-07-30）

在 `run_e52c28cd6b14` 的问题诊断中，ACG 的复杂 `information_retrieval` 节点连续扩大搜索上下文，最终触发 DeepSeek 请求超时；随后异常封装和失败状态持久化缺陷又使该 Run 残留为 `running`。这说明在 ACG 生命周期、超时和恢复机制稳定前，继续开放公网检索会放大故障影响。

当前策略如下：

- Chat 继续允许 `web_search` 和 `web_extract`，不受本策略影响；
- ACG 调度入口强制剔除 `web_search` 和 `web_extract`，即使 Agent 或插件声明了这两个工具也不能获得运行权限；
- 原生通用 Agent 和法律法规检索 Agent 不再声明公网工具；
- `knowledge_search`、`codebase_search` 和 `current_datetime` 等本地只读工具继续可用；
- DeepSeek 模型接口仍然可用，“ACG 离线”仅表示禁止公网搜索和网页提取，不表示停用模型推理。

重新开放 ACG 公网工具前至少应满足：

1. 任意节点异常都能可靠进入 `failed`、`cancelled` 或其他明确终态；
2. Run 失败时活动节点可以原子终止，不产生僵尸 `running` 记录；
3. 节点具备总超时、来源预算、上下文压缩和有界重试；
4. Trace 能保留原始工具或模型异常；
5. 复杂检索在 Docker 集成测试中连续运行通过。

## 6. 代码检索改造

`codebase_search` 复用项目已有 `CodeIndexBuilder`，没有再实现第二套索引系统。

改造点包括：

- 支持配置工作区根目录；
- 对搜索结果做根目录越界检查；
- 返回真实文件路径和行号；
- 首期使用词法索引模式；
- `enable_vectors=False`、`prefer_vectors=False`；
- AI 服务启动时预热代码索引。

禁用首次调用时的本地 Sentence Transformer 加载，避免大型模型下载和嵌入初始化导致首个程序员任务超时。向量检索仍可作为后续独立优化项。

## 7. Tavily 与 Docker 配置

### 7.1 Secret 路径

Windows 当前部署使用：

```text
.secrets/kinlin-win-p1-001/tavily_api_key
```

文件只包含一行 Key，不包含变量名、引号或其他内容：

```text
tvly-xxxxxxxxxxxxxxxx
```

Key 不应写入 `.env.windows`、前端配置或 Git。

### 7.2 Compose 注入

Compose 将 secret 挂载到容器，由入口脚本复制到仅 AI 运行用户可读的位置：

```text
TAVILY_API_KEY_FILE=/run/kinlin-secrets/tavily_api_key
```

修改 Key 后需要重新创建 AI 服务：

```powershell
docker compose --env-file .env.windows `
  -f compose.yaml `
  -f compose.dev.yaml `
  -f compose.windows.yaml `
  up -d --no-deps --force-recreate ai-service
```

缺少 Key 时：

- AI 服务仍然启动；
- `web_search`、`web_extract` 报告 `available=false`；
- 日期、知识库和代码库工具继续可用；
- 时效性请求必须明确说明无法联网，不能静默使用模型记忆替代。

## 8. 重要故障及修复

### 8.1 Tavily 缺失导致 `AI_STREAM_FAILED`

现象：

1. 模型成功调用 `current_datetime`；
2. 随后调用 `web_search`；
3. SSE 以 `AI_STREAM_FAILED` 中断。

根因：

- Tavily Key 为空时，`web_search` 没有注册到 SDK Agent；
- 系统提示仍提到了 `web_search`；
- DeepSeek 仍生成该工具调用；
- Agents SDK 抛出 `ModelBehaviorError: Tool web_search not found`。

修复：

- 系统提示动态列出当前可用和不可用工具；
- 可选提供方缺失时保留安全的失败工具 Schema；
- 实际可用性仍由服务端 Catalog 判定；
- 不可用调用返回标准 `TOOL_UNAVAILABLE`；
- 模型收到工具失败结果后继续生成明确的降级回答；
- SSE 正常以 `done` 结束。

### 8.2 多工具结果错位

现象：同一轮出现多个工具调用时，`current_datetime` 的结果可能被映射成重复的 `web_search` 错误。

根因：输出事件只从 SDK `raw_item` 读取 `call_id`，而当前 SDK 已在 Tool Output Item 上提供规范化 `call_id` 属性。

修复：优先读取 SDK Item 的规范化 `call_id`，再回退到原始载荷，确保每个 `tool_result/tool_error` 与对应调用一一匹配。

### 8.3 宿主目录生成代码索引缓存

一次性 Docker 测试容器把项目挂载到 `/workspace`，但没有显式设置 `AGENTOS_DATA_DIR`，导致测试期间在宿主项目的 `agent/app/data/code_index/` 生成大型 JSON 缓存。

该目录是未跟踪的派生索引，不是源码；任务结束时已清理，Docker 数据卷中的正式索引不受影响。后续一次性测试应把 `AGENTOS_DATA_DIR` 指向 Docker 临时目录，避免生成内容进入任务编辑统计。

### 8.4 `run_fa61d0b1e9f8` 离线 ACG 阻塞

现象：服务重启后，Run 仍长期停留在 `native_general_agent_6` 的 `information_retrieval`，界面显示完成 4/14，无法产生最终结果。

第一性原理排查结论：

1. ACG 公网权限剔除已经生效，日志中没有 Tavily、`web_search` 或 `web_extract` 调用；
2. 原生资料检索 Agent 仍进入共享 `ToolRuntime.run()`，这会启动 DeepSeek 模型工具循环；
3. 模型在本地 `knowledge_search` 返回后继续多轮调用，最终触发请求超时；
4. `APITimeoutError.code` 为 `None`，异常归一化把空值写入非空 `errorCode` 字段，引发二次 Pydantic 校验错误；
5. Run 失败持久化前没有先关闭活动节点，SQLite 一致性规则拒绝保存“Run 已失败但节点仍运行”的快照；
6. 因此执行协程已经结束，数据库中的 Run 却仍显示 `running`，形成僵尸任务。

修复内容：

- ACG 通用资料检索改为一次有界的 `knowledge_search` 直接调用，不再进入模型工具循环；
- 本地知识库无命中时，通用任务只把用户已提供的任务事实标记为 `task-input` 证据，不冒充外部来源；
- 法律依据检索无本地权威来源时明确失败，不使用任务输入伪造法规；
- 异常码统一回退到异常类型，确保 `errorCode` 永不为空；
- Run 失败前原子关闭运行中/重试中的节点和 Attempt，再刷新兼容投影并持久化；
- 服务重启清理也复用相同终态逻辑，清空 `activeStepIds` 并修复历史遗留的活动 Attempt；
- Docker 测试改用独立一次性容器，不再把测试目录复制到实时开发容器，避免 WatchFiles 在用户运行期间重载服务。

## 9. 测试与验收结果

所有开发、测试和真实 API smoke test 均在 Docker 环境中执行。

### 9.1 自动化测试

| 测试范围 | 结果 |
| --- | --- |
| Python AI | 259 passed，1 skipped |
| AgentOS | 177 passed |
| Java Backend | 150 passed |
| Vue Frontend | 108 passed |
| 前端生产构建 | 成功 |
| Dockerfile 静态检查 | 无警告 |
| ACG 离线阻塞定向回归 | 28 passed，2 warnings |
| ACG 终态一致性定向测试 | 4 passed |

### 9.2 真实调用验证

- Chat 非流式调用 `current_datetime` 成功；
- Chat SSE 产生 `tool_start`、`tool_result`、内容、用量和 `done`；
- DeepSeek Thinking 模式连续工具调用成功；
- Tavily 缺失场景返回单个 `tool_error`，最终回答明确降级且不中断；
- ACG 程序员任务返回 `agent/app/main.py` 等真实代码位置；
- ACG Trace 中存在 `TOOL_CALLED`；
- Evidence/Provenance 引用完整且完整性校验通过；
- 使用 `admin / 123456` 验证前端到 Backend、AI、DeepSeek 和工具的完整链路成功。

Tavily Key 配置后已完成 Chat 真实搜索与正文提取验证。ACG 公网 smoke test 曾确认工具可以调用，但在复杂任务中暴露了超时与僵尸 Run 问题，因此现已按 5.4 节暂停 ACG 公网工具。

`run_fa61d0b1e9f8` 已收口为 `failed/interrupted_after_restart`，`activeStepIds` 为空。随后使用相同中文任务输入创建精确复测 `run_ed4b4cdf8b5a`：

- 14/14 步全部完成，Run 状态为 `completed`；
- 原阻塞节点 `native_general_agent_6` 完成；
- 资料检索只调用一次 `knowledge_search`；
- `retrievalMode=task_input_only`，来源提供方为 `task-input`；
- Trace 不包含 `web_search` 或 `web_extract`；
- 测试 Run 保留用于界面人工验收。

### 9.3 生产镜像说明

开发 AI 镜像已经成功构建并健康运行。生产 AI 镜像完整构建在 20 分钟验证窗口内因原有基础依赖锁较大而超时；Dockerfile 静态检查通过，未发现语法或构建规则警告。

## 10. Git 提交记录

```text
0685ab9 feat(tools): 建立共享只读工具运行时
93fcf80 feat(chat): 接入联网与工具调用链路
2fc218a feat(acg): 注入受限工具运行时与证据链
65b1b78 feat(backend): 透传并持久化工具调用结果
da95f3f feat(frontend): 展示工具轨迹与可点击来源
0e4f3af fix(chat): 降级处理不可用联网工具
11fa1b6 fix(acg): 暂停公网工具调用
b148dad docs(acg): 记录阶段性离线策略
058a3be fix(acg): 可靠持久化运行失败状态
2829118 fix(acg): 离线检索绕过模型工具循环
5e1b1f8 fix(acg): 清理重启中断节点投影
f147284 fix(acg): 修复历史中断尝试状态
```

## 11. 后续建议

1. 优先修复 ACG 异常归一化、终态持久化、节点总超时和僵尸 Run 回收。
2. 为一次性 Docker 测试统一设置临时 `AGENTOS_DATA_DIR`。
3. 为未来 ACG 联网增加来源预算、查询规划、去重压缩和有界重试。
4. 增加 Tavily 额度、限流和错误率监控，但日志中不得记录 Key 或网页全文。
5. 根据真实代码库规模评估是否恢复可选向量索引，避免把重量级模型重新放回首请求路径。
6. 第一阶段继续保持工具只读；任何写操作工具应经过独立权限模型、审计和人工确认设计后再开放。

## 12. 结论

本次改造已经把项目从“容器和模型能够联网”提升为“Chat 与 ACG 具备共享、受限的只读工具运行时”。工具运行时由 Chat 与 ACG 共享，但不替换现有 AgentOS 编排架构；模型工具循环、ACG 任务治理和前端可观测性保持职责分离。

当前 Chat 可以使用 Tavily 公网搜索与正文提取；ACG 仅开放本地日期、知识库和代码检索工具。ACG 公网工具将在生命周期、超时、恢复和上下文预算达到 5.4 节门槛后重新评估开放。
