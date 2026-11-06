# PR-CTX-01 OScode 上下文链路与 P0

## 实际调用链

`ChatView.sendMessage` → `chatStore.sendMessageStream` → fetch `/ai/chat/text/stream` → Java `AiServiceProxyController.proxyChatStream` → `ChatStreamPersistenceService.prepare` → `AiSseGatewayService.openPost` → Python `chat_text_stream` → `AgentsToolRuntime.stream` → Agents SDK `Runner.run_streamed` → `_ProviderAwareChatModel` / OpenAI-compatible Provider。

Feature Flag 开启后，只在 Python Chat API 对 Runtime 显式传入 `oscode_context_compaction=True`。共享 Runtime 默认 False，因此 ACG/只读调用即使应用开关为 True 也不自动进入压缩器。SDK 每次模型调用前执行 `call_model_input_filter`：Python 预算适配 → 请求级 TS worker → 独立压缩引擎 → 原 SDK Provider。

## 十项核查

1. 前端流式请求传 `text/context_id/model/thinking_mode/...`，不上传完整 `context`；Java 从持久化消息构建历史。
2. **发现 P0**：prepare 先保存本次 userMessage，再查全部消息，当前 user 已在 context；Python `_input` 又追加 text，重复两次。
3. 修复位于 Java `buildContext(conversationId,currentMessage)`，按当前对象/ID 排除本次消息。不是按内容去重；此前相同文本仍保留。原始消息仍保存一次、当前 text 仍独立传给 Python。独立 Java 回归模拟 save 后立即可见的真实数据库顺序。
4. Tool call/result 在单次 SDK Runner 内通过 `call_id`/`tool_call_id` 或 Responses `function_call/function_call_output` 关联。压缩器同时支持两种格式，校验实际 ID、重复和孤立结果。
5. 同次请求多轮工具结果由 SDK 增量输入持有，filter 在每次模型调用前重投影。跨 HTTP 请求由 Java 历史恢复文本；当前持久化不保存完整 tool wire branch，不能宣称服务重启后可完整恢复该分支。
6. SSE 仍使用 reasoning/content/tool/approval/execution/usage/done 等既有事件。摘要调用不混入聊天 SSE；压缩指标仅写结构化日志，不增加事件类型。
7. 模型窗口从 `provider_model_capabilities(effective_model,base_url)` 取得；未知模型需 exact-route policy 显式配置 context_window。
8. 既有流式 usage 是调用后的 Provider 计量；前端显示 context usage，不等于调用前预算或压缩。新核心区分内容分词、保守 framing/图像预算与 Provider 报告使用量。
9. 历史每个请求重新从 Java 传给 Python。第一阶段无跨请求摘要缓存；只在同一 Runner 的 Node worker 内 memo 已验证前缀，避免工具循环反复摘要。这样不引入 DB 迁移和跨 contextId 复用。
10. 权威聊天记录是 Java 已保存的 user/assistant 正文及清洗后的 execution/source metadata；原始 reasoning、完整工具正文/协议不是完整持久化的内容。压缩不会改变该既有持久化合同，也不会把摘要写入其中。

## 边界

原始数据库记录不改写；本轮唯一历史相关修复是排除本次消息进入历史投影。系统指令、工具授权/执行、Provider 接口、外部 Chat API/SSE 合同均保留。没有修改 `apps/agentOS/**`，无数据库迁移、无生产配置切换、无部署。
