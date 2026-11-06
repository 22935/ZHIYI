# PR-CTX-01｜OScode 独立上下文压缩器实施记录

日期：2026-11-06（Asia/Shanghai）。

状态：**IMPLEMENTED / TARGETED-TESTED；不标记 SELF-TESTED**。

本轮仅交付未提交开发成果。Feature Flag 默认关闭；未提交、推送、合并、部署，未执行生产数据库迁移。`apps/agentOS/**` 未修改；549 个已跟踪路径相对任务开始时的字节内容一致，见 [ACG 冻结证据](PR-CTX-01/ACG-freeze.json)。

## 最终实现

- 独立 TypeScript 核心：`apps/oscode-context/src/`，API 入口 `index.ts`。
- `TokenMeter`：匹配本地 tokenizer/OpenAI 编码时做内容分词；否则使用显式标记的 UTF-8 保守预算。系统、工具、输出预留、安全余量分别计入。没有把 DSH chars/4 估算当作精确计量。
- `ContextBudget/CompactionPolicy`：使用 Provider 声明的实际模型窗口或 exact-route 配置，触发阈值与压缩目标分离形成迟滞；输出预留同时成为主 SDK 调用的真实输出上限。
- `HistorySegmenter`：保留系统指令、当前消息、近期完整对话、未完成工具周期和多模态引用；以 Call ID 配对并把切点移到合法边界。
- `ToolResultPruner`：优先确定性裁剪已完成工具结果的长文本中段，保留头尾、错误、路径、引用和不透明图片/文件块。
- `LLMSummarizer`：通过注入回调使用原有 Provider helper；工具关闭、thinking 关闭、输出预算明确、分块 map/reduce 与调用次数受限，不递归经过压缩器。
- `CompactionValidator`：校验摘要八字段结构、长度、缩小比例、完整尾部、工具结构、来源 hash；提交前验证源未变化。失败时完整回退，超窗口则明确拒绝，不静默丢历史。
- 请求级 memo/互斥：同一 Runner 中复用成功前缀；context/provider/model/hash 均进入身份，Node worker 不允许更换会话所有者。无跨 HTTP 摘要缓存和数据库快照。
- Python 薄桥接：`apps/agent/app/context_compaction/runtime.py`；短输入只做快速保守准入，不启动 Node/摘要模型。压力时启动请求级 JSON-lines 子进程，SDK 结束/取消时关闭。Node 不接收模型 API Key，不执行工具，不是常驻服务。
- OScode 集成：Python Chat API 显式选择 `oscode_context_compaction`；共享 Tool Runtime 默认不选择此路径。接入 SDK 每次模型调用前的 `call_model_input_filter`，覆盖同轮新增工具结果。Chat API、SSE、Provider 的外部接口没有新增合同字段。

## 独立 P0：当前用户消息重复注入

原流程 Java 保存当前 userMessage 后查询历史，Python `_input` 又追加当前 text。本轮 Java `buildContext(conversationId,currentMessage)` 按对象/ID 排除当前已保存记录，保留此前同内容消息，原始聊天持久化仍执行一次。新增 Java 回归模拟 save 后记录立即可见的数据库行为；Python SDK/HTTP 测试验证当前消息只出现一次。

## 开关与配置

`OSCODE_CONTEXT_COMPACTION_ENABLED=false` 为默认值；原有路径保留。模型窗口、输出预算、阈值、保留策略、精确 tokenizer 资产等通过 `OSCODE_CONTEXT_COMPACTION_MODELS` 的 `base_url::effective_model` 精确键配置。Node 路径可用 `OSCODE_CONTEXT_COMPACTION_NODE` 指定。具体格式见 [模块 README](../../apps/oscode-context/README.md)。

第一阶段未纳入发行包部署。启用前还需核对 Node 24、npm 锁定依赖、模块路径、模型窗口和 tokenizer/图像计价配置。

## DSH 来源与迁移边界

上游固定提交：`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`。

迁移的是预算/压力、保留尾部、工具平衡边界、Unicode head/tail 裁剪、结构化 checkpoint 和原子验证机制。`pruneContent` 为去掉服务外壳后的函数提取/类型适配，其余是合同/算法适配，**不是四个 DSH 包的逐字迁移**。

没有迁移 Cordis 服务、DSH AgentLoop、Session surface/journal、持久 shadow events、分布式维护锁、usage replay 定价、UI compact 命令、自动 Provider overflow 重试。摘要不重放工具 schema/KV 前缀；这是本轮“摘要不启用工具”的边界选择。

MIT 原文和 45 个审计源码/类型/测试/依赖文件 SHA256 见 [来源清单](../../apps/oscode-context/third_party/dsh/provenance.json)、[许可证](../../apps/oscode-context/third_party/dsh/LICENSE)。审计文件 hash 对应固定提交检出的本地字节，包含检出时换行形式；上游 commit 同时固定内容版本。

## 验证与源码快照

主工作区存在并行修改。最终验证改在固定的 `.tmp-tests/pr-ctx-01/validation` 工作树执行；没有把较早主目录的结果冒充最终快照结果。

最终 SHA256：`aa352a7326667e0017568ef5cce68a376716a403356a065c105ea9e6d0649ff1`。

完整逐文件清单见 [source-snapshot.json](PR-CTX-01/source-snapshot.json)。本快照包括 1756 个应用源码、测试、配置文件；排除生成物、依赖、数据和报告文档。验证后逐文件重新计算 hash，无变化。主工作区相对该快照的后续并行改动在 [verification.json](PR-CTX-01/verification.json) 单列，未回滚或覆盖。

| 检查 | 通过 | 失败 | 收集错误 | 跳过 | 说明 |
|---|---:|---:|---:|---:|---|
| TypeScript 独立核心 | 28 | 0 | 0 | 0 | 类型检查同时通过 |
| OScode / SDK / 工具 / Chat / SSE 定向 | 53 | 0 | 0 | 1 | 真实 Provider 默认关闭，另行显式运行 |
| 真实 Provider 小样本 | 1 | 0 | 0 | 0 | deepseek-flash，合成数据，单独成本记录 |
| Java 全量 | 548 | 0 | 0 | 0 | 新 target 报告；不混入主目录遗留报告 |
| 前端全量 | 1187 | 0 | 0 | 0 | 145 个文件；桌面构建通过 |
| Agent / AgentOS 全量 | 见最终 JSON | 未通过 | 见最终 JSON | 见最终 JSON | 有既有测试基线阻塞，不能据此标记 SELF-TESTED |

最终详细数量、命令证据、失败位置、此前中断/无效尝试的排除说明见 [verification.json](PR-CTX-01/verification.json) 和 `PR-CTX-01/evidence/`。定向/Java 全量存在子集交叉，表格不作为无重复测试总数相加。

已知门禁阻塞至少包括：

1. `apps/agent/tests/test_hands_transport_chat.py:310` 的既有 SyntaxError；该文件相对任务开始时未由本轮修改。
2. ACG 架构测试仍要求已经退役的 `apps/local-runtime` 进程源码存在。按冻结范围不恢复代码、不改测试掩盖失败。

随后尝试继续执行两组 Python 全量测试，约七分钟后仍未完成，AgentOS 停在约 18%。已停止这两个测试进程并保留日志；这些未完成运行不计入通过数量，也不替代上述门禁结果。

## 性能与质量结论

五类 Mock 场景包括技术对话、代码审计、多轮工具、长文档、多阶段开发；15/15 标注事实保留仅证明 Mock 数据流，不证明真实摘要质量。

真实样例保留四项已确认信息；主请求输入显著下降，但摘要成本与延迟另计，单轮总成本没有下降。精确数字、保守预算和 Provider 实测计量的区分见 [性能与质量评估](PR-CTX-01/性能与质量评估.md)。第一阶段没有跨 HTTP 摘要复用；不能只用主请求 Token 降幅宣传经济收益。

## 十项交付对照

1. [DSH 源码审计](PR-CTX-01/DSH源码审计.md)。
2. [迁移文件来源/SHA256](../../apps/oscode-context/third_party/dsh/provenance.json) 与 MIT 许可证。
3. [OScode 真实上下文链路审计](PR-CTX-01/OScode上下文链路审计.md)。
4. `apps/oscode-context/src/` 独立 TS 实现。
5. `app/context_compaction/runtime.py`、Chat API、SDK Runtime 集成及 Java P0 修复。
6. `OSCODE_CONTEXT_COMPACTION_ENABLED` 默认关闭。
7. `apps/oscode-context/test/` 独立单测与五场景评估。
8. `apps/agent/tests/test_oscode_context_compaction.py`、Java 历史服务回归与现有工具/SSE 回归。
9. [质量评估](PR-CTX-01/性能与质量评估.md)、[Mock 数据](PR-CTX-01/mock-evaluation.json)、[真实样例](PR-CTX-01/live-evaluation.json)。
10. 本实施记录、[验证报告](PR-CTX-01/verification.json)、源码清单与 ACG 冻结证据。

## 最终五项判断

1. **成功迁移**：压力预算、近期保留、工具配对、Unicode 裁剪、结构化摘要、源稳定/缩小校验和请求内重复保护。
2. **未迁移**：DSH Session/Cordis/replay/维护事务和 UI 命令；当前宿主使用现有 SDK/Provider 与请求级桥接。
3. **独立可用程度**：独立 TS API 和隔离 OScode SDK/HTTP 链路已有定向及真实 Provider 验证；尚未达到项目全量准入标准，不能标记生产可用或 SELF-TESTED。
4. **生产风险**：保守计量过早触发、视觉计价未校准、真实质量覆盖窄、跨请求重复摘要成本、过大保护区明确失败、发行包依赖尚待装配验证。
5. **真实用户测试条件**：目前只适合继续隔离/合成样本评估；不建议默认开启或直接进入正式真实用户验收。先解决既有全量门禁，并扩大计量/质量/成本验证；本轮不提前接入 ACG。
