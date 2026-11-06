# PR-CTX-01 DSH 源码审计

上游：https://github.com/deepseek-ai/deepseek-harness
固定提交：`fcc0ad462172522aaf5c93a7b2e01f6b9f0b0159`。本地审计副本位于 `.tmp-tests/pr-ctx-01/upstream`。45 个源码、类型、测试、package.json 的 SHA256 见 `apps/oscode-context/third_party/dsh/provenance.json`，完整 MIT 许可证同步保留。

## 实现追踪

1. **压力触发**：`compaction-basic/src/index.ts#compactPressure` 从最新 routed request header 取 Provider/Model，再解析真实模型窗口与输出预留。`config.ts#resolveCompactSpec` 使用 `min(window * thresholdRatio, window - outputReserve - headroom)`；低于阈值不裁剪、不摘要。达到阈值后先 prune、再重新计量、再选择摘要范围。重试次数有限。
2. **Token 计量**：`token-meter/src/estimate.ts` 的基础价格为 `ceil(chars/4)` 加角色/块开销，明确是 heuristic。`route-pricing.ts` 用实际图像定价、文件投影替换基础价格；`measurement-projection.ts` 和 `index.ts` 从 Session request/header、step 与 Provider usage 事件恢复计量锚点。它不是对所有模型使用精确分词器的实现。OScode 不复制 chars/4 为精确计量。
3. **压缩范围**：`region.ts#selectCompactableRange` 从尾部累加 retainTokens，保留最近尾部，再将切点向旧头部移动到 tool-pairing balanced 边界；系统头不进摘要范围。
4. **最近对话**：价格与 Session surface 的位置序列必须完全匹配，避免过期计量选择错误范围。OScode 额外按完整 user turn 保留，并用完整 message 深比较验证尾部。
5. **摘要模型调用**：`summarizer.ts#summarizeWithLlm` 默认重放 system、tools、旧前缀，末尾追加 compaction 指令，通过 `ctx.llm.stream()` 获得文本；结构化 Markdown checkpoint 保留目标、概念、文件、错误、待办、当前工作、下一步、约束，并合并旧 checkpoint。原始输出和真实 model/provider/usage 写日志。OScode 改为工具关闭的独立 JSON 摘要调用，不复制工具 schema 重放/KV-prefix 优化。
6. **工具结果**：`compaction/src/tool-pairing.ts` 用 assistant tool-call 数量与 tool/result 差额寻找平衡切点，Session surface generation 变化会重建缓存。`compaction-tool-result-pruner/src/index.ts#pruneContent` 用 Unicode code point 保留头尾、替换中间，保留富内容块顺序；`config.ts` 默认 8192/4096/1024 字符。OScode 提取该纯转换并增加 actual call ID 配对、结构化错误/路径保护。
7. **信息保留**：保留系统头、尾部、完整工具周期；摘要输出不能为空、必须比被替换范围短；源 surface 稳定性必须在异步摘要前后成立。它不能数学保证语义事实无损，质量仍需单独测量。
8. **失败与重复**：`region.ts#compactSurfaceRegion` 用 `compaction/start/end` 记录事务、来源范围与失败；`summarizeCompaction` 校验 shrink；摘要恢复钩子允许重新准备稳定源。`index.ts` 给压力/溢出有限重试、阻止活跃压缩；`checkpoint.ts` 定义持久 checkpoint 来源。OScode 无共享可写 Session，改为请求级队列/源 hash/成功结果 memo；无无界重试和跨会话缓存。
9. **内部依赖**：Cordis Service/Context、DSH Agent/AgentLoop、Session surface/journal/seq、Session projections、LLM block assembler、commands brand、schemastery、util-values、retry/image-offload 插件。package.json 多个 peerDependencies 是 workspace 内部包，不适合整包搬入当前 Python Runtime。
10. **可提取部分**：窗口/预留/阈值数学合同、Unicode 工具输出 head/tail、工具平衡边界、结构化 checkpoint 内容要求、源稳定性与缩小校验。不可独立逐字提取的是服务生命周期、Session 事务和 replay 校准层。

## 测试与合同交叉检查

重点追踪 `compaction-basic/tests/compaction-basic.spec.ts` 中的阈值/保留、可选 prune、无安全切点、同模型换 Provider、源改变、非缩小摘要、模型输出失败；`compaction-loop-repro.spec.ts` 的 toolcalls 后重复压缩/overflow 重试；`runtime-context-admission.spec.ts` 的 cwd 等必要 Runtime context 保留；`compaction/tests/tool-pairing.spec.ts` 的未完成周期/孤立结果；`compaction-tool-result-pruner/tests/tool-result-pruner.spec.ts` 的 surrogate pair、富块和 replay；`token-meter/tests` 的 usage/projection/pricing 合同。测试源码作为审计证据，不宣称在 OScode 内运行了完整 DSH monorepo 测试。

## 语言方案比较与选择

- Python 原生适配：无需跨进程，但会把 TS 算法重写成另一种语言，难以直接对照和维护上游。用户随后明确选择 TS，未交付 Python 核心。
- 独立常驻服务：增加端口、认证、部署、故障恢复和服务版本管理；本轮不采用。
- **TS 核心＋请求级 Node 子进程＋Python Provider 薄桥接**：保持核心语言，短请求无子进程；压力出现时才启动，SDK 请求结束即回收。复用现有 Node 24，不启动第二套 Agent/Session Runtime。代价是压力请求有进程启动/JSON 序列化开销，以及 Node/package 依赖必须随应用准备。

`src/tool-result-pruner.ts#pruneContent` 是移除 Cordis 外壳后的函数提取/类型适配；其余文件是算法与合同的独立适配。不得将本轮工作描述为四个上游包的逐字迁移。
