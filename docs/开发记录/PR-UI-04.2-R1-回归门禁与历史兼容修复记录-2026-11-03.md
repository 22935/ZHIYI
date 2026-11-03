# PR-UI-04.2-R1｜回归门禁与历史兼容修复

状态：SELF-TESTED（按用户收缩后的必要验证范围；AgentOS 全量未完成，等待独立复验）。

## 起点与范围

2026-11-03，master / HEAD `a1b5a6a98111cf8a315686eae519094b5c9419ee`，起始工作区和暂存区为空。延续用户授权，处理测试清理、Mock 合同、历史记录兼容及真实剩余故障。本轮没有部署或操作开发服务，没有修改真实业务数据库。修复工作等待独立复验。

## 根因与必要修改

- `apps/agent/tests/conftest.py`：Task Decomposition 请求已是 JSON，旧 Mock 仍拆文本。按 planningRequest / capabilityCatalog 解析，并使用真实 sourceRegistry 的引用；目录展开的前置能力保留。修复重试追加文本时只解码首个 JSON 对象。
- `test_general_golden_recovery.py`、`test_legal_execution_runtime_vertical_slice.py`：各次 Runtime 的使用改为 try/finally。真实启动/规划故障会释放自己持有的资源和实例锁。保留正常重启顺序及原有断言。
- Legal golden 旧夹具只声明节点，补齐其显式 Blueprint 的真实语义可达关系；生产语义保真校验保持严格。
- Programmer 模板缺少目录声明的 task_understanding 前置任务，且语义键与既有 Step 绑定合同不符。补入真实前置步骤并保留原四步骤的顺序、输出、工具和记忆断言，模板版本升至 1.0.1。
- Legal 静态模板的语义键同样没有对应现有 Step ID，按现有七步依赖链对齐，模板版本升至 v1.1。目录规划测试参数化覆盖静态和动态两条路径。
- `packs/legal/planning/contract_review_blueprint.py`：检索节点错误继承 human_review 的 Agent 绑定，返回审核载荷而违反 legal_basis 输出合同。明确绑定已存在的 statute Agent。没有新增执行服务或绕过输出校验。
- `components/executor/graph.py`：所选审核分支完成、另一分支被明确跳过时，汇合仍被跳过前驱阻塞。最小补丁仅允许“全部前驱已结束，且至少有一个实际完成的前驱”的候选继续。未完成前驱仍阻塞，只有被跳过前驱的子节点不会启动。增加正反例并保留真实 Legal 审核/重启集成断言。
- `scripts/freeze_gate.py`：将新增历史测试、域模板及 Blueprint 的实际字节纳入外部指纹和真实测试映射。新外部参考为 None，始终要求复验；原始 INT-1 基线、预算、排除和失败分类保持不变。

修改清单共 13 个文件：上述三个测试文件和 conftest、两个模板、Legal Blueprint、Executor Graph、Graph 回归、新增 `apps/agent/tests/test_execution_history_compatibility.py`、freeze_gate，以及本记录和原 PR-UI-04.2 记录。原记录仅纠正已完成提交/推送的事实，保留当时的 BLOCKED 结论。生产变动集中在两个域模板、Legal Agent 绑定和 Graph 分支汇合；未修改取消内核、任务所有权或安全状态机。

## 历史数据合同

本轮不改变数据库 schema，不批量重写历史 Run，不补造旧任务的结算事实。新增六项测试覆盖：General / Legal 启动故障后的实例锁释放，以及 completed / cancelled / pending / running 四种旧格式载荷重启。

旧格式是通过真实 HTTP 创建和执行得到的合成兼容夹具，直接写入临时 SQLite JSON 并移除 taskSettlement；不是生产数据库导出，也不代表已验收所有历代 schema。重开完整应用与 Runtime 后比较完整 Run、历史 Trace、输出及 Outbox 事件事实。启动允许投递待处理 Outbox，但不能新增虚假历史事实。

对 pending / running 记录执行真实取消 API，校验完整历史前缀和输出保留、重复请求不改历史、Runtime 内部取消幂等；随后启动 Coordinator 验证不重新派发已取消任务。保留既有 HTTP 对终态取消返回 409 的合同。旧 completed / cancelled 记录不自动获得 taskSettlement。

这些测试验证本地持久化与运行时兼容，不证明升级前遗留的外部物理操作已经停止；实际遗留外部执行仍须依据既有 Admission / Receipt / 恢复屏障核实，不能从缺失结算字段推断已释放或重放。

## 反例、重复验证与证据

仓库外证据目录：`C:/Users/LZX/AppData/Local/Temp/pr-ui-04.2-r1/`。

- `focus-before-contract-fixes.log`：11 passed / 3 failed，锁污染不再掩盖独立错误。
- `focus-before-retrieval-binding-fix.log`：真实检索输出违反 legal_basis 合同的日志。
- `branch-join-before.log`：汇合应就绪但只有 root 就绪；修复后同一正反例通过。
- `history-first.log`：新测试开发中的错误断言证据（序列类型与待投递 Outbox），不作为生产回归归因。
- Windows profiles 单独五轮，每轮 5 tests 通过。原 os.replace 的 WinError 5 本轮未再复现，尚无句柄占用归因；未据此修改生产写文件或添加重试。
- AST 数量核对：General 保留 1 个测试 / 44 个断言，Legal 保留 2 个测试 / 39 个断言（目录测试增加静态、动态参数），域包保留 4 个测试 / 21 个断言；Graph 由 38 / 118 增至 39 / 120。数量核对仅辅助范围审计，实际行为仍由定向及全量结果证明。

## 最终验证

最后源码快照包含 `apps/`、`scripts/` 下 2243 个文件，清单 SHA-256 为 `2ab758bf452fe825daf02da19f045cf2db17f123a078b6e7c055f88c4f6a0b08`。11:12 再核对 `changedPaths=[]`。文档不计入源码清单；最终另执行 whitespace 和工作区审计。

| 门禁 | 结果 |
| --- | --- |
| 托管取消、历史兼容、多分支与 Store 组合定向 | 169 passed，2 warnings；exit 0 |
| Java Run / Gateway / capability / 序列化 / 投影 / 路由兼容 | 26 tests，0 failures / errors / skips；exit 0；不是 Java 全量 |
| TypeScript `vue-tsc -p tsconfig.json --noEmit` | exit 0 |
| Web `npm run build:web` | exit 0 |
| 前端全量 `npm test -- --maxWorkers=2 --minWorkers=1` | 143 files / 1053 tests passed；exit 0 |
| Local Runtime 全量 | 52 passed / 1 skipped；exit 0；原有 Windows symlink 环境跳过 |
| Agent 全量 | 493 passed，22 warnings；exit 0；1294.67 秒 |
| AgentOS 全量 | 未完成，不计通过；用户要求取消不必要测试后不再重跑 |
| Graph / Executor / Architecture / freeze_gate integrity 定向 | 175 passed；exit 0；39.92 秒 |

命令、退出码和日志位于 `verified`。第一次长时全量的进程在 11:12 检查时已不存在，四项均没有结果 receipt，不能作为通过证据。原日志保存在 `verified/interrupted-1112/`，中断原因尚未确定；没有据此修改或削弱测试。随后在同一源码摘要上重跑缺失四项。日志中的 `faulthandler_timeout=90` 是堆栈诊断信号，不等同测试退出结果。早期探索不能替代最后源码快照的全量验证。

用户随后明确要求“你认为没必要的测试就不要做了”。据此收缩验证范围：AgentOS 全量中与本次局部补丁无关的整包回归不再继续扩展，保留 Graph、执行器、架构和冻结门禁完整性定向作为其必要覆盖。检查原 AgentOS 全量时，原 PID 已不存在，未取得最终退出码；没有执行 Stop-Process，也不将其 26% 进度当作通过。Agent 493 项全量已包含真实域流程、重启与取消集成，169 项组合定向覆盖结算、多分支及 Store；通过结果均保留，不重新重复。此范围调整不删除或禁用仓库测试，也不改变任何断言、预算或排除规则。

最后定向结束后，源码清单再次核对为上述 2243 个文件及同一摘要，`changedPaths=[]`。八项正式结果 receipt 的 exitCode 均为 0。`git diff --check` 通过，暂存区为空，无未合并文件。完成的八项日志扫描未发现 Task/Future exception was never retrieved、Task was destroyed、coroutine was never awaited 或未处理 Promise rejection。测试进程正常结束，无继续运行的本轮 pytest / Vitest 门禁。未停止、恢复或部署开发服务；不将缺失的全量退出码推断为成功。

## 风险与交付

依赖和安全状态机没有改动。测试不替代 Linux、真实模型或远端设备验收。域模板更改仅影响后续准备的执行计划；历史 Blueprint 与任务状态不进行批量替换。Windows 原始 os.replace 错误未复现，不能声称已完成其根因修复。AgentOS 全量及 300 秒正式 freeze_gate 未取得本轮通过结果；175 项定向中的完整性测试不等同正式冻结验收。当前证据支持本轮局部修复提交独立复验，状态为 SELF-TESTED，不代表 ACCEPT 或仓库级全量验收。当前未提交、未推送、未部署。
