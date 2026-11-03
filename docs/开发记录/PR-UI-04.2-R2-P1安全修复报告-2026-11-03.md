# PR-UI-04.2-R2｜P1 安全修复报告

状态：SELF-TESTED，等待 GPT 独立代码审计；未宣布 ACCEPT。

## 1. 基线、分支与工作区保护

正式基线及当前 HEAD：`eae564c1eaef4def470a4935e628bd3ba7a8596c`。

初始检查：master 工作区、暂存区均为空，无 untracked 文件、未合并文件或用户未提交修改；本地 origin/master 与指定基线一致，GitHub mirror 的 master 经 `git ls-remote` 核验亦为该 SHA。指定分支此前不存在，执行 `git switch -c fix/pr-ui-04-2-r2-p1-safety eae564c1eaef4def470a4935e628bd3ba7a8596c` 新建分支。本轮 HEAD 不前移，不修改 master，不创建正式提交、不 Push、Merge 或部署。

验证期间其他工作产生了 docs/开发记录 的归档移动、旧报告删除与合并文档，部分已暂存。本轮未操作这些并发修改和暂存项。后续范围清单、交付补丁及 scoped diff 仅包含本轮十个代码/测试/门禁文件和本报告；全局 git status 可能同时显示并发文档工作。

## 2. P1-A 根因及修复

- `AgentOutput.output` 有默认空字典，且 extra=ignore。原适配器把所有非 HTTP error 响应直接 model_validate，导致 202、`{"status":"RUNNING"}` 和空对象被解释成空成功。
- 原 TimeoutException / HTTPError 包装为默认 `outcome_unknown=False` 的 ResourceExecutionError，遗漏部分写出或远端执行后读取超时的不确定性；自动 failover 只检查异常类型，未检查 UNKNOWN。
- 超步只暴露第一个 cause。其他同时失败或因兄弟失败而取消的任务，也可能在结算时报告 UNKNOWN；该事实不能被第一个已知失败掩盖。
- 原 UNKNOWN 隔离之后调用性能观测，观测会更新健康投影，可能重新标记 healthy；首轮集成断言抓到了该问题。

修复实现：

1. 只接受现有同步 `/execute` 的 HTTP 200 原始 AgentOutput，要求显式存在字典类型 `output`。顶层 status envelope 尚无已验证的服务端协议，保守作为未确认结果，不让 Pydantic 忽略它。202、空响应、非终态、错误格式及未确认的服务端/代理响应不成功落账。
2. ConnectError、ConnectTimeout、PoolTimeout、UnsupportedProtocol，以及 httpcore trace 明确证明连接/TLS 建立阶段失败且尚未开始 HTTP headers 发送的情况，归为未发送。一旦观察到 headers 开始发送，可能已执行的证据优先于早期连接失败。WriteTimeout/WriteError 发生在写入开始后或缺乏阶段证据时、ReadTimeout、读取/协议异常等归为 UNKNOWN。没有添加重试；未分类客户端执行异常亦不能证明远端未执行。
3. HTTP 400/401/403/404/405/413/415/422 作为请求格式、认证、方法、路由或输入拒绝，不一律归 UNKNOWN。409、5xx、202、无终态证据的其他回复归 UNKNOWN。该分类依赖远端遵守 HTTP 请求拒绝语义；本轮没有验收不遵守此语义的第三方服务。
4. 正常响应和取消后的响应使用同一终态验证。取消等待仍等待请求真实结算；已确认未发送或已确认请求拒绝不伪造 UNKNOWN，未确认结果继续保留不确定性。
5. ACGSuperstepError 保留所有已结算任务的异常并聚合 UNKNOWN；检查显式 cause、Python cause/context 包装链。Runtime 优先提取链中的 UNKNOWN，而不是被外层已知失败覆盖。
6. `_recover_remote_acg_failure()` 对 UNKNOWN 返回 False；失败规划观察也不自动重规划。保留 taskSettlement 的 unknown / retained_unknown，隔离资源，并持久化 `recoveryOutcome.action=review/status=required` 等待核对。隔离在性能观测后实施。

### Idempotency-Key 合同检查

适配器发送 commitId/attemptId 作为 Idempotency-Key，但本仓库没有可据以验真的通用远端 `/execute` 持久幂等服务合同。Local Runtime HTTP 处理器对其自身进程 API 的幂等键检查属于另一套协议，不能证明外部 `/execute` 已实现去重。因此本补丁不以该 Header 为自动重试或 failover 的依据。

## 3. P1-B 根因及修复

原 `ready_steps()` 将所有 skipped predecessor 当作可以豁免的依赖，普通 AND 节点因此被当作 Join。条件路由只跳过未选分支入口，未递归处理其后续必要依赖，导致 dormant 残留和 DAG 无可调度节点。控制节点同样无条件减去 skipped predecessor。Compiler 虽验证 Blueprint 的 branchEdgeIds / conditionSpec / joinNodeId，却未将 IF 的 joinNodeId 传入运行图。

修复在本地运行图元数据保留已验证 Blueprint 的显式 joinNodeId。CompiledPackage 的 Blueprint hash 仍必须一致；没有改变持久化合同、包版本、数据库或引入 Branch Head。

运行图建立 dependency 前后继集合及每个 IF 到声明 Join 之前的分支区域。只有声明的无条件 Control Join 可以豁免本区域内的 skipped 输入；其他必要前驱保持 AND 依赖。多个 IF 共用 Join 时，每个区域都必须有完成输入；未完成输入继续等待，任一区域输入全被跳过则 Join 跳过。

skip 按“必要依赖已被跳过”的固定点传播。声明 Join 是区域边界，不用无界 descendants 批量跳过；直达 Join 的替代边也不能把公共 Join 标为 skipped。外层未选区域中的嵌套 IF、其分支和内部 Join 可以自然跳过，选中分支与外部合法 Join 保留。循环、共识、审核及恢复仍使用既有控制逻辑，未放宽 Blueprint 对嵌套 IF/LOOP 的原有验证规则。

兼容性审计另外发现，Legal 的真实 Blueprint 将 human_review / auto_review 直接汇入普通 report_generate Step，未声明 Join。严格 AND 语义下，该报告会被正确禁止调度；如果仅改 Executor 而不修声明，会破坏现有审核后的报告交付。`legal-join-before.log` 保存高、低风险两条实际 Blueprint 完整执行均缺报告的反例。本轮只在该 Blueprint 添加 `review_join` 无条件 Control（既有 auditor consensus、quorum=1），声明 IF.joinNodeId，并将两条审核依赖经 Join 接到原报告步骤。业务步骤、输入输出、资源绑定和 YAML 不变；原 Step 间可达依赖保持一致。这是 P1-B 必需的直接兼容修复，不是业务流程重构。原三项 Legal Runtime 重启/审核/规划路径亦纳入最终复验。

## 4. 反例与新增测试

仓库外原始证据：`C:/Users/LZX/AppData/Local/Temp/pr-ui-04.2-r2/`。

- `before.log` 保留适配器默认空成功、超时 UNKNOWN 丢失、Runtime 自动切换等失败；该次另有两项新 Graph 夹具缺 consensusSpec 的开发错误，不作为生产根因证据。
- 修正新夹具后，`graph-before.log` 中两项完整执行真实失败：无共享前驱时 DAG 卡在 no schedulable step nodes；有共享前驱时 dormant 被错误执行。
- 远端新增 25 项 Adapter 参数化用例，覆盖 202、非终态 JSON、空响应、请求拒绝、连接/池超时、读写超时、协议异常。WriteTimeout 阶段用真实 httpx/httpcore HTTP 序列化及可控网络后端，分别在连接建立前及 header 写入时注入，不以错误消息猜测阶段。`connect-retry-before.log` 另保留“客户端先重试连接、随后真正发送、最后读取超时”被旧阶段标记误判的失败，补丁修复了发送证据的优先级。
- 六项 Runtime 集成通过真实 HTTP Adapter、NodeRunner、ResourceBinder、ACG、WorkflowStore 执行。accepted/running/read timeout/write timeout/server error/隐式异常包装路径均断言：仅 edge-01 被调用一次，cloud-01 调用和占用为零，recovery_count=0，没有 failover history，原绑定保留、Lease active_slots=1、资源 disabled/unhealthy、结算 unknown/retained_unknown、无步骤完成、恢复要求 review。原正常 failover 用例保留并执行。
- Graph 新增 16 项完整 run 用例：编译后的分支与 dormant、共享前驱、三种多层嵌套选择、三路分支、选中分支受控等待与检查点恢复、全分支跳过、普通后继、直达 Join、两个 IF 共用 Join、真实 Legal 高/低风险审核恢复，以及已知失败取消兄弟时 UNKNOWN 包装保留。原 R1 的隐式 Join 单测修正为普通 AND 必须阻塞，并补完整 run 断言，确保其后续被跳过且 DAG 正常结束。
- 冻结门禁新增五项映射断言。仅补当前 Graph、Compiler 和 ACG Runtime 对应测试，不改 YAML 映射、预算、原始基线、排除或失败分类。

## 5. 最终验证与源码一致性

最终源码快照覆盖 apps / scripts 下 2243 个文件，SHA-256：`89d1e9ce03871e870b5d8fe2c94186d666667a50cd881c454827026408bfd0ac`。验证使用临时目录隔离默认 SQLite / Chroma；没有操作业务数据库。

首次全量因发现上述阶段优先级缺口，明确停止仅属于本轮的 pytest 进程；旧快照日志、退出码和源码不一致记录保留在 `intermediate-v1/`，不作为最终通过证据。修正后按顺序重新运行全部指定定向、映射检查及全量，最终结果以根目录 receipt 为准。

上一候选代码快照（22cacff9…）的完整运行得到 2249 passed / 2 failed / 3 warnings，1354.00 秒。两项失败均在未修改的 Hands 集成文件中导入应用包时发生：`ModuleNotFoundError: app`、`ModuleNotFoundError: packs`。原命令默认 pythonpath 只有 AgentOS 自身，缺少兄弟项目 apps/agent；该完整失败日志及同源码摘要记录保存在 `environment-missing-app/`。仅补测试进程的 PYTHONPATH 后，该文件 4 passed（`hands-environment-check.log`），未修改仓库 pytest.ini、测试或断言。随后以正确导入路径重跑；发现上述 Legal 显式 Join 兼容缺口后，该旧快照运行明确停止，日志保存在 `intermediate-legal-join/`，不作为最终结果。最终按新摘要重新执行指定定向、映射、Legal Runtime 及全量；独立四项通过不替代全量结果。

最终命令在 `apps/agentOS` 执行，设置进程级 `PYTHONPATH=<仓库>/apps/agent`，以实际导入兄弟应用包；保持原 pytest.ini。仓库外 `verify.py` 记录该路径、临时数据库目录、每项原始命令、退出码及源码摘要。PowerShell 单独复验时，可先执行 `$env:PYTHONPATH=(Resolve-Path ../agent).Path`，再运行任务书命令；默认数据路径应另设隔离临时目录。

| 检查 | 结果 |
| --- | --- |
| 任务书五个定向文件 `python -m pytest -q ...` | 126 passed，1 warning；exit 0；5.67 秒 |
| freeze_gate integrity 定向 | 100 passed；exit 0 |
| 原 Legal Runtime golden（重启、审核、静态/动态规划） | 3 passed，2 warnings；exit 0；11.58 秒 |
| AgentOS 全量 `python -m pytest -q --tb=short` | 2253 passed，3 warnings；exit 0；1301.90 秒 |
| `git diff --check` / `git diff --cached --check` | 均 exit 0 |
| 前后源码摘要 | sameSource=true，2243 文件及摘要完全一致 |

未删除、禁用测试或降低 deadline / 断言。没有通过少量定向结果宣称全量通过。

四项最终结果均记录同一源码 SHA-256，所有退出码为 0。最终日志扫描未发现 Task/Future exception was never retrieved、Task was destroyed、coroutine was never awaited 或未处理 Promise rejection。验证命令均已结束，没有继续运行的本轮验证进程。HEAD、master 和 GitHub master 最后复核仍为正式基线；本轮代码未暂存，现有暂存项为并发文档工作，未触碰。

本轮十个已跟踪代码/测试/门禁文件的 `git diff --stat` 汇总：

```text
10 files changed, 591 insertions(+), 45 deletions(-)
```

本报告为另一个新增文件。完整交付补丁仅包含上述十个文件与本报告，共十一文件；不包含并发文档整理。补丁位于 `C:/Users/LZX/AppData/Local/Temp/pr-ui-04.2-r2/PR-UI-04.2-R2-P1-safety.diff`，配套 `diff-stat.txt`、`delivery-files.json`、`patch-result.json` 和 `verification.json` 记录完整统计、各文件摘要、反向应用检查及最终测试收据。原始 target / gate-mapping / legal-compat / full 日志全部保留。门禁完整性测试不等同正式 300 秒 freeze_gate 整包验收，本轮未宣称该整包通过。

## 6. 修改文件及必要性

| 文件 | 必要性 |
| --- | --- |
| apps/agentOS/src/adapters/resource_execution.py | 终态响应验证、传输阶段和 UNKNOWN 分类 |
| apps/agentOS/src/runtime/acg_execution.py | 禁止 UNKNOWN 自动切换/重规划，保留隔离与结算 |
| apps/agentOS/src/components/executor/graph.py | 显式 Join、依赖 skip 传播、并发异常 UNKNOWN 保真 |
| apps/agentOS/src/components/executor/compiler.py | 从已验证的 Blueprint 保留 IF Join 本地运行元数据 |
| apps/agent/packs/legal/planning/contract_review_blueprint.py | 修正实际审核 Blueprint 的隐式 Join，保持报告交付与恢复 |
| apps/agentOS/tests/adapters/test_resource_execution.py | 真实 Adapter 与 httpcore 阶段反例 |
| apps/agentOS/tests/runtime/test_resource_binding.py | UNKNOWN 只执行一次并保留 Lease 的完整绑定链 |
| apps/agentOS/tests/test_acg_execution_graph.py | 分支、嵌套、共享节点及 Join 完整执行反例 |
| apps/agentOS/tests/storage/test_freeze_gate_integrity.py | 当前生产修改能选择新增回归 |
| scripts/freeze_gate.py | 本次直接相关生产路径的测试映射 |
| 本报告 | 基线、原始证据、实现与验收边界 |

## 7. 剩余边界与独立审计建议

- 本轮是本地 Windows 自动化验证；真实远端设备及 Linux 尚未验收。HTTP MockTransport 不替代实际外部副作用确认。
- 原始 HTTP 200 AgentOutput 合同仍有效；异步 202/status envelope 需要既有核对流程或正式后续协议，当前明确阻止将其视为成功。
- 保留 Lease 的既有 TTL 合同未变；本轮不把 TTL 到期当作远端停止证明。资源 enabled=False 保持隔离，需核对后再人工处理，不自动恢复或重放。
- taskSettlement.taskState=ended 仅表示本地拥有的 Task 已结算；outcome=unknown 不表示远端物理操作已停止。
- 旧持久化 Blueprint 不批量补写 Join。未声明 Join 的历史汇合不能继续享有隐式依赖豁免；此类旧 Run 的恢复或迁移须独立核对，不能把本轮新生成 Blueprint 的审核恢复通过扩展成所有历史载荷已验收。
- Blueprint 原本拒绝声明 IF 区域内的嵌套 IF/LOOP。本轮不放宽该合同；多层嵌套测试验证运行图 API 的安全调度，并覆盖外层未选区域全部跳过。需要编译接收更多嵌套 Blueprint 时应另作合同决策。
- 最终完整 Diff 留在新分支工作区及仓库外补丁，交给 GPT 独立代码审计；没有提交、推送或部署。
