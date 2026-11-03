# PR-UI-04.2-R2.1 Remote Terminal Response Contract 实施记录

日期：2026-11-03。状态：**SELF-TESTED**，等待 GPT 独立审计。

## 1. 入场状态与范围

- 入场 HEAD、本地 master、fetch 后 origin/master、GitHub master 均为 `a0f4f17c87aa86a89b00ed33951da510326a4e80`。
- 入场工作区、暂存区均干净，无未跟踪文件。由精确基线新建 `fix/pr-ui-04-2-r2-1-terminal-response`。
- 本轮仅修改 HTTP 适配器及其两份测试；不修改全局 AgentOutput、Graph/Compiler、Runtime 生命周期、Legal Blueprint 或前后端其他模块。
- 未创建正式提交，未合并、推送或部署。完成后保留修复分支，交由 GPT 独立审计。

## 2. 原始缺陷及失败复现

`service/agents/base.py` 中 AgentOutput 使用 `populate_by_name=True, extra="ignore"`，output 默认 `{}`。基线 HTTP 适配器要求 200、显式字典 output，另拒绝顶层 status，但其余未定义字段被模型忽略。`{"state":"RUNNING","output":{}}` 和 `{"success":false,"output":{}}` 因而成为成功结果；甚至未定义的 state=COMPLETED、progress、admission、executionStatus、metadata 也会被接受。

先增加 Adapter 回归，再修改生产代码。使用实际 HttpResourceExecutionAdapter.run 和 httpx.MockTransport 执行，原实现结果为 **11 failed, 47 passed**。其中 7 项证明未定义字段被接受，3 项证明取消等待路径将非法响应认定为确定结算，另 1 项证明原本拒绝的 status 包装在取消路径丢失了验证异常的显式 cause。没有用孤立 whitelist 函数替代实际请求路径。

原始失败日志完整保留于 `C:/Users/LZX/AppData/Local/Temp/pr-ui-04.2-r2.1/before-adapter.log`，对应 `before-verification.json` 和 `before-source.json`。红测时尚未加入后续 Runtime 新参数；最终门禁覆盖所有最终源码变更。

## 3. 已定义同步响应合同

已登记远端 Adapter 的工厂 `build_resource_execution_adapter()` 只支持 HTTP/HTTPS，Runtime 的 `_remote_runtime_adapter()` 接入该工厂。本轮依据现有同步 `/execute` → 原始 AgentOutput 合同收紧；仓库内没有可据以接受额外顶层状态/进度/Admission 元数据的已验证合同。

HTTP 200 响应必须是 JSON object，且显式包含字典 output。所有顶层键必须属于 AgentOutput 的已定义 Python 字段名或 JSON alias，再由原模型验证类型和值：

| Python 字段 | JSON alias | 类型 |
| --- | --- | --- |
| output | output | dict[str, Any]，必须显式提供 |
| summary | summary | str |
| risk_level | riskLevel | str 或 null |
| sources | sources | list[dict[str, Any]] |
| tool_executions | toolExecutions | list[dict[str, Any]] |
| evidence_refs | evidenceRefs | list[str] |
| model_invocations | modelInvocations | list[dict[str, Any]] |
| runtime_events | runtimeEvents | list[dict[str, Any]] |

白名单从 AgentOutput.model_fields 的名字和 alias 构建，复用 `populate_by_name=True` 的既有兼容行为；没有复制字段类型，也没有修改全局 extra 行为。纯 alias、纯 Python 名字及混合名字均实测通过。

顶层 state/status/success/executionStatus/progress/admission 或任何其他未定义字段均拒绝。字面 COMPLETED 不能建立一个未定义的成功包装合同。output 内部的 state、success、status、progress、admission 是业务数据，保留原值；sources 等已定义容器内的数据仍由原模型合同处理。`{"output":{}}` 是合法同步终态，空业务结果本身不是拒绝理由。

## 4. 最小实现及 UNKNOWN 传递

1. `_terminal_output()` 在 model_validate 前验证顶层字段集合；不合法响应继续以 `ResourceExecutionError(..., outcome_unknown=True) from exc` 报出。
2. 正常返回和取消等待请求结算均调用同一个 `_terminal_output()`。取消路径遇到 UNKNOWN 验证异常时直接重新抛出，保留原 TypeError/ValidationError cause，不再换成仅带取消上下文的新错误。
3. 合法同步结果在取消路径保持原 CancelledError 结算语义；它不变成 UNKNOWN，也不因调用者已取消而提交本地成功。
4. HTTP 状态码分类、传输阶段分类和请求所有权保持既有合同，没有添加重试或异步执行协议。

现有链路由 Adapter → NodeRunner → ACGSuperstepError（保留 UNKNOWN）→ ACGExecutionService 拒绝自动 Failover/重规划 → RuntimeRecoveryCoordinator 记录执行失败 → 既有 recoveryOutcome 改为 review/required、REMOTE_EXECUTION_OUTCOME_UNKNOWN。任务结算保留 outcome=unknown、leaseState=retained_unknown，资源 enabled=False/healthy=False。该路径没有新增状态仓库。

## 5. 修改文件与回归反例

| 文件 | 必要性 |
| --- | --- |
| apps/agentOS/src/adapters/resource_execution.py | 严格限定顶层合同；取消结算保留原始验证异常链 |
| apps/agentOS/tests/adapters/test_resource_execution.py | 新增 27 项参数化用例：17 项非法响应、3 项完整合法字段名字组合、1 项空 output、6 项确定性取消结算 |
| apps/agentOS/tests/runtime/test_resource_binding.py | 保留原六种 UNKNOWN，新增两种已定位响应；补强 recovery reason、executionBinding、无成功 Trace、无输出断言 |
| 本实施记录 | 基线、合同、原始证据、验证与审计边界 |

取消测试使用 started/release Event 控制真实 Adapter 请求返回；收到开始信号后取消所有者，再释放远端响应，不依赖固定 Sleep。未知响应要求 UNKNOWN 及原始 TypeError cause；合法空 output 和包含业务 state 的合法响应要求 CancelledError。finally 检索并结算请求 Task，client 使用 async context manager 关闭。

Runtime 八种情形均走真实绑定/代理/NodeRunner/ACG/WorkflowStore 链，检查 Edge 一次、Cloud 零次、recovery_count=0、无 resourceFailoverHistory、原两种绑定保留、Lease 保留、Edge 隔离、无完成步骤、无 step_succeeded Trace、无成功输出，且 recoveryOutcome 要求核对。既有正常 Failover 测试保留且通过。

## 6. 测试环境与同源码门禁

- Windows，Python 3.14；工作目录 apps/agentOS。
- PYTHONPATH 包含 `C:/Users/LZX/Desktop/kinlin_ai/apps/agent`；保留仓库 pytest.ini 的 `.` 与 `src` 导入路径。
- AGENT_CHROMA_PATH 和下列 AGENTOS_* 数据库配置均指向独立临时目录：WORKFLOW_DB_PATH、LANGGRAPH_CHECKPOINT_DB、EXECUTION_VALUE_DB、EXECUTION_MEMORY_DB、PROVENANCE_DB、AUDIT_DB、CONTENT_MANIFEST_DB、RESOURCE_DB、NODE_DB、RESOURCE_HEALTH_DB、EVOLUTION_DB、IDENTITY_DB。定向测试使用 `C:/Users/LZX/AppData/Local/Temp/pr-ui-042-r21-db-0lyd512p`，最终完整全量使用 `C:/Users/LZX/AppData/Local/Temp/pr-ui-042-r21-full-db-j9ey2ta8`，两者均未使用业务数据目录。
- 未修改 pytest.ini、测试预算、依赖、excludes 或断言强度，没有删除/禁用/跳过原有测试。

| 门禁 | 结果 |
| --- | --- |
| python -m pytest -q tests/adapters/test_resource_execution.py | 58 passed，1.79 秒 |
| python -m pytest -q tests/runtime/test_resource_binding.py | 21 passed，1.79 秒 |
| python -m pytest -q tests/test_acg_execution_graph.py | 55 passed，1 warning，3.15 秒 |
| python -m pytest -q tests/components/executor/test_advanced_acg_capabilities.py | 8 passed，0.47 秒 |
| python -m pytest -q --tb=short | 2282 passed，3 warnings，1554.13 秒（25:54）；exit 0 |
| git diff --check / git diff --cached --check | 均 exit 0 |

最终候选 apps/scripts 共 2243 文件，逐文件 SHA-256（按路径排序）的 JSON 清单摘要：`12f0d3d178412e916089791cb6c4d657da44570beb6ee7e36f85c38590004e30`。每条命令开始前校验摘要，所有门禁结束后再次逐文件比较；报告与补丁文件不在 apps/scripts 摘要范围内。最终前后摘要相同，sameSource=true；全部五组完成门禁均 exit 0 且对应此摘要。

四组定向共 142 项通过。全量新增后的数量为 2282，较上一轮 2253 增加 29 项；全量结果不以定向数量替代。三个 warning 分别是既有 Pydantic class-based config、PyPDF2 和 Starlette TestClient/httpx 弃用提示。完整日志扫描未发现 Task/Future exception was never retrieved、Task was destroyed、coroutine was never awaited 或失败摘要。

第一次全量运行随会话中断停止，日志最后进度为 28%，没有 pytest 完成摘要或可用退出码，明确不计为通过。`interrupted-full.log` 及 `interrupted-full-result.json` 保留该原始记录；已通过的四组定向结果不重跑。源码逐文件核对未变后，使用独立临时目录重新执行完整全量命令。此次重执行用于补齐被中断的门禁，没有修改测试、源码或预算，也没有清除原数据与日志。

证据目录：`C:/Users/LZX/AppData/Local/Temp/pr-ui-04.2-r2.1/`。`run_gates.py` 与 `resume_full.py` 保存精确命令、环境与收据；final-source.json 是完整逐文件摘要，final-*-result.json 和 final-*.log 保存各门禁退出码、耗时和原始输出，final-verification.json 汇总最终同源校验。

## 7. 完整 Diff 与剩余风险

交付完整补丁：`C:/Users/LZX/AppData/Local/Temp/pr-ui-04.2-r2.1/PR-UI-04.2-R2.1-terminal-response.diff`。它仅包含本轮三个代码/测试文件及本报告。生成时使用独立临时 Git index，不覆盖真实暂存区；生成后执行 `git apply --reverse --check`。`delivery.json` 记录补丁及四个文件的 SHA-256、反向检查退出码、最终 Git 状态，`diff-stat.txt` 记录完整统计。

已跟踪代码/测试 `git diff --stat` 为 3 files changed, 127 insertions(+), 6 deletions(-)；完整补丁另外包括本新增报告。最终 HEAD 仍为入场基线，暂存区为空，工作区仅保留本轮三项代码/测试修改和本报告。

当前是 Windows 本地自动化验证，未声称真实外部设备或 Linux 已验收。MockTransport 可证明响应边界及本地安全收敛，不能证明实际远端执行已停止或服务端实现持久幂等。无合同扩展的顶层元数据将被保守拒绝；如果远端确需新增字段，应先定义并审查协议，再改变此白名单。既有 Lease TTL、隔离和人工核对规则未改变，不能把本地 Task 结束解释为远端物理副作用结束。

结论：本地必需门禁通过，可提交独立代码审计，状态 SELF-TESTED。没有新增未解决的本轮 P1；真实远端和跨平台验收边界如上。未 Commit、Push、Merge 或部署；保留修复分支，到此停止实施，不宣布 ACCEPT。
