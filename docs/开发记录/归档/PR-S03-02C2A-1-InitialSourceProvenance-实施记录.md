# PR-S03-02C2A-1 Initial Source Provenance 实施记录

状态：**SELF-TESTED**。实施、最终定向、扩大及 AgentOS 全量验证完成；全部修改未暂存、未提交，等待独立验收，不宣称 ACCEPT。收尾日期：2026-10-20。

## 1. 基线、范围与权威边界

入场/当前 HEAD：`dac4217836f3ea468df25f61c8692d38a032704d`，master，暂存区为空。唯一入场未跟踪文件是上一轮 C2A 来源审计提案，已识别并原样保留。没有 README、EX-00、图片或其他用户修改需要覆盖。已读取该提案、S02/S03/C1 记录与实际 Record/Service/Store/Provider、Topology/Binding/Lowerer/Compiler 输入链。

本轮源码范围（相对 `apps/agentOS/`）：

- 新增 `src/contracts/initial_planning.py`：版本化首次来源与编译策略合同。
- 修改 `src/contracts/planning_commit.py`：在既有 sourceProvenance 联合中加入 Initial 分支及接受来源绑定校验。
- 新增 `src/runtime/initial_planning_sources.py`：只读、有限大小的正式来源捕获。
- 修改 `src/runtime/planning_commit.py`：初始捕获、冻结 L1/L2 输入、事务来源重验、历史重放及只读预检。
- 修改 `src/components/planner/planning_commit.py`：Runtime 首次 Provider 必须提交新版来源证明；仍由原 Service 接受。
- 新增 `tests/components/planner/test_initial_planning_sources.py`：34项真实 Runtime/SQLite 对抗与兼容测试。
- 根 `scripts/freeze_gate.py`：新增受影响模块→正式安全用例映射，没有修改预算、筛选策略或断言。

仅原 PlanningCommitService/SQLitePlanningCommitStore 写 Commit+outbox。Store 的表、事务、CAS、索引与 Schema 代码未修改。未修改 Materialization、Activation、Handoff、Permit、Recovery、ResourceBinder、Native Executor、Artifact、Workspace 或默认生产装配；新的 Initial 接受路径不构造图、GraphVersion、Head、Checkpoint、Attempt、Receipt 或 Artifact。既有回归的临时旧链路夹具仍正常运行，不将其测试写入误算为新功能物化。

## 2. 来源合同及完整正文

`InitialPlanningSourceProvenance.version=initial-static-v1` 与原 runtime-static-v1/v2 在同一 Record.sourceProvenance 体系中通过互不重叠的 Literal 版本区分。合同 extra=forbid/frozen，读取时重新解析与校验，而非相信 model_copy 绕过校验后的对象。

| 数据 | 持久内容与校验 |
|---|---|
| Run/Mission/Basis/scope | sourceRunId、Mission/revision、原 MissionIntentBasis 和 RunExecutionScope 全文、Run domain；Mission/basis/revision/Workflow scope 一致性校验 |
| Workflow | 原 WorkflowDefinition 全文，含 domain、version、模板节点/边、Step 输入输出/审核配置等；不是仅保留 ID/version |
| Agent Profiles | scope 下真实注册 Profile 的完整规范化 JSON，复用 AgentProfile 重验后复制；保持原登记次序，按既有 agentId 或 agentName 回退验证 scope 完整覆盖及唯一性 |
| Catalog | scoped Catalog 全文用于规划/后续路由；另保留现有接受语义验证实际使用的全局 validationCatalog，避免冻结 scoped 目录却暗读另一份全局内容 |
| Identity | 通过正式 TaskPlanRepository.latest 读取，内嵌既有 TaskPlan 模型全文与摘要；Mission/planVersion 构成身份。第一次尚无 snapshot 时显式保存 null 及其摘要；Identity authority 不可用时拒绝，不能把服务缺失视为可信空值 |
| 实际 L1 Profile | 非模板计划内嵌实际 IntentParser 产生的 TaskSemanticProfile，保留 Lowering 会读取的 objective/complexity/entropy/evidence/webExtraction 等值；模板路径为 null，由完整 Workflow 提供模板下沉依据 |
| 其他编译条件 | materialRefs、planningSeed、planningDiversity、requested capability profile；原 Run input 与既有 Runtime 来源 context 只保存摘要，避免无必要复制整个输入中的运行期凭证 |
| 编译策略 | initial-compilation-policy-v1：Topology 版本、Binding Solver 策略/搜索预算、Lowerer、Graph Compiler package 版本、逻辑路由与接受策略身份；附实现文件内容摘要 |

全部编译对象正文均内嵌，不依赖 Registry、缓存或外部可变 ID 重新补齐。Identity 也保存正文而非只保留 latest 指针。关键实现摘要覆盖 Topology 模块组、Binding Solver、Lowerer 与 ACG schema/resource 合同、Graph Compiler 与 CompiledACGPackage 合同、CognitiveRouter/规划算法/semantic profile，以及 lowering_input。它们是版本漂移检测依据，不是代码签名或任意依赖的供应链证明。

编译策略、静态并发建议等属于规划配置；没有读取 ResourceBinder.assess、心跳、动态 Runtime 健康、Lease 或瞬时资源占用。能力需求不等于执行资源分配。

来源正文最多2M JSON字符，最多256 Profiles、512 scoped/validation Catalog 描述、256 materialRefs；实际 Scope 覆盖及 Catalog 自身合法性亦验证。Profile 无 SDK/密钥/端点实例；捕获器拒绝配置中常见凭证键（api_key、authorization、password 等），不通过静默删字段改变编译语义。普通业务自由文本不能靠键名检查完成全面敏感信息识别，不能将其宣传为通用 DLP。

## 3. 唯一接受链、CAS 与幂等身份

链路：`accept_initial → 读取正式 Run/Basis/Scope → 两次捕获并比较 → 写锁外原 L1/L2 → 冻结实际 L1 Profile（如有） → 原 PlanningCommitService → 正式 Sources/权限/语义重验 → Record+outbox 同事务提交`。

L1/L2 使用捕获 Workflow 的私有副本和 scoped Catalog 副本；保留既有 scoped Planner 实例/调用接缝，只注入冻结 Catalog 到 SemanticPlanner、TaskDecomposer、IntentParser。没有把 L1/L2 或模型调用移入 BEGIN IMMEDIATE。后续路由所需 Profile/Catalog/策略均已封存，本轮不执行路由下沉或图编译。

新来源先对规范化 alias JSON（含版本，排除 staticFingerprint 本身）计算 SHA-256；`initial-acceptance-v1` 将原 runtimeFingerprint 与完整来源 staticFingerprint 合成为新 Sources.strategyFingerprint。现有 requestFingerprint 已覆盖 sources 全文，因此幂等请求身份传递覆盖新版来源类型、正文及策略摘要；Record 总内容指纹也包含完整来源。Record validator 再校验 Initial 类型、Mission/revision、Basis 引用、Sources 策略摘要与原 TaskPlan。

Service 从受信任 Runtime Provider 获取正文，新 Runtime Provider 标记 requires_versioned_initial_sources，缺失新版对象即拒绝。客户端/模型请求合同没有新增来源正文或权限字段。旧通用受信任 Provider 的兼容协议未移除；其无证明记录不具备新版来源资格，不能因 DTO 合法而成为可物化对象。

来源初检在 L1/L2 前，事务内在语义验证前后重读当前输入并比较；捕获来源/正文回调之后再关闭 Sources 与授权 fence。Scope/Policy 等无法捕获时返回不同的失效来源指纹，明确收敛 STALE_STRATEGY，不退回旧来源投影。冻结 Catalog 还用于原确定性语义验证。

原 Mission commitmentRevision CAS、parent/head、全请求幂等绑定、事务回滚、唯一约束以及原子 outbox 均保留。新来源由原 JSON Record 一并持久化，无数据库 Schema 升级，无另建接受权威。

## 4. 历史兼容与后续消费方式

旧 initial sourceProvenance=None 的 Record 仍按原结构读取；accept_initial 命中原 Key 后显式选择旧 Runtime 来源投影，只重放原接受事实，不运行 Planner、不补写历史。新版对象未知版本、缺少 Workflow、摘要损坏、或修改来源后重新封口但未同步原接受 Sources，均拒绝。

新增 `RuntimePlanningCommitAuthority.validate_initial_sources(commit_id)` 只读预检：加载正式 Record，要求新版 Initial 类型、当前附着 Authority、Mission 当前接受头、权限和来源一致；历史 None 对象返回 INVALID_PROPOSAL。非模板重验读取已接受的 L1 Profile，不重新调用模型。它不是事务承诺或激活许可。

后续 C2A-2 可从原 ledger.get(commit_id).source_provenance 获取完整冻结对象，用其 Workflow、Catalog、Profiles、L1 Profile、Basis/scope/编译策略构造现有编译输入。最终物化仍须使用现有唯一 MaterializationAuthority，并在最终事务内重新验证；不能只凭本预检成功或历史接受 Receipt 绕过当前来源。

本轮未开放首次 materialize/activate；旧 MaterializationAuthority 依然只接受 GraphRevisionProposal，Initial 不会因为新增证明而自动变成图或执行许可。旧 runtime/graph_revision 来源分支与 Safe-Cut 算法没有修改。

## 5. 失败反例、开发修正与安全证据

- 两个原始反例保留在正式测试：接受后修改 scoped Agent capabilities；修改 Workflow domain 但保留 version。新版 Sources 重验拒绝 STALE_STRATEGY，持久快照正文仍保持原值。
- 独立基线复现：从 `git show dac421...:apps/agentOS/src/runtime/planning_commit.py` 提取原始模块，在临时测试宿主中加载原 Provider/Authority，其余宿主兼容现有合同。两个断言要求变化后 Sources 不相等，实际均失败：`2 failed in 2.98s`，墙钟5.738秒，退出码1。日志 `tmp/c1_audit/c2a1_original_failures_v2.log`；原模块与探针在 ignored `tmp/c2a1_baseline/`。未把该局部原模块复现冒充整个基线 checkout 的全量验证。
- 初版开发反馈：AgentProfile 未显式 agentId 时应按 Registry 规则回退 agentName，已修正；构造新版 Planner 对象绕过了原实例挂载的漂移注入，原7项来源竞争断言失败，改为保留实例并注入冻结 Catalog，原断言不改。该运行源码中途变化（source_unchanged=false），仅作为开发失败证据，不作为最终测试快照。
- 非模板测试先因 Fixture 使用错误参数 task_input 失败，改为真实 input_override；随后暴露只读预检未装入已接受 L1 Profile，已修正为显式使用持久 Profile。未修改生产 L1 推理算法或旧测试断言。
- 新34项覆盖：来源漂移/接受中变化、完整正文与无业务副作用、Identity 可信空值/服务不可用、损坏/未知来源、历史兼容、动态资源隔离、缺失证明拒绝、凭证配置拒绝、相同 Key 重放、不同 Key/同 expectedRevision 跨连接 CAS、record/outbox/commit/ACK 四阶段故障。
- 并发是实际独立 SQLite 连接与线程竞争；没有声称本轮完成多进程故障、跨机器隔离或最终物化并发。接受前后多库内容比较扣除允许的 ledger/outbox 后一致。另调用原 execute_prepared_run 验证仍停留 planningDeferred，无 Blueprint/Steps、无 Agent 调用或执行收据；Runtime 既有 PENDING→PLANNING 编排状态变化不是 Commit 对 Run 的写入。

## 6. 最终源码与验证

环境：Windows 11 build26100，Python3.14.5；默认计时，无1ms请求、xdist、旧断言/timeout 修改。以下最终范围全部固定于同一源码：441个 src/tests Python 文件聚合 SHA-256：

`18c378633691a305b15a9036bb6ccafb40987db27a872ede3238fcb82dfcb8f6`

算法与原 freeze_gate 一致：raw bytes 单文件SHA，仓库相对POSIX路径排序，LF连接`路径 空格 SHA`无尾LF，UTF-8清单再SHA。清单保存在 `tmp/c2a1-final-snapshot.json`。API独立SHA仍为 `b78ffdd8d0b1c004f9befdd63c7372070cf9a733c244f86591328897791ccc21`；freeze_gate脚本SHA为 `46e7460d12ab2cbe8435deb0b9f711fe48424e6c3efb28fe5dfe1d45f0132cfd`。

cwd=`apps/agentOS`，原始日志与JSON（含UTC起止、墙钟、退出码、运行前后摘要）位于 `tmp/c1_audit/c2a1_*`。Python runner只记录结果，不改变 pytest 选择或计时环境。

| 范围 | 实际命令 | 结果/耗时/退出码 |
|---|---|---|
| 最终来源/Commit/Graph Revision/合同/架构 | `python -m pytest -q tests/components/planner/test_initial_planning_sources.py tests/components/planner/test_planning_commit.py tests/components/planner/test_planning_commit_runtime.py tests/components/planner/test_planning_commit_audit.py tests/components/planner/test_graph_revision_commit.py tests/components/planner/test_graph_revision_audit.py tests/contracts tests/architecture --tb=short` | 280 passed；pytest152.76秒，墙钟155.144秒；0，source_unchanged=true |
| 最终扩大回归 | `python -m pytest -q tests/components/planner tests/contracts tests/architecture tests/runtime --tb=short` | 1233 passed，2 warnings；pytest1496.75秒，墙钟1500.118秒；0，source_unchanged=true |
| 最终 AgentOS 全量 | `python -m pytest -q --tb=short` | 1848 passed，3 warnings；pytest1518.77秒，墙钟1523.430秒；0，source_unchanged=true |

扩大与全量为本轮任务明确授权的完整验收范围，不冒称为300秒 L2 freeze_gate；本轮没有机械再运行一次默认冻结脚本。映射已更新供后续定向门禁复用。

三组最终命令退出码均0，运行前后均为上述441文件同一摘要，最终清单逐文件再次比较完全一致；API与冻结脚本独立摘要也一致。全量1848=原1814+新增34，扩大1233=原1199+新增34。全量3个 warning 为原 PyPDF2、Starlette/httpx、Pydantic 弃用提示；未改依赖以消除提示。全量仅指 AgentOS pytest，不代表 Java、Vue、浏览器或供应商模型验收。

最终 `git diff --check` 退出码0，HEAD仍为指定基线，index为空。范围是本阶段4修改+4新增（含本报告）；另有原样保留的上一轮 C2A 提案。临时日志、原基线探针与manifest均在 ignored tmp，不进入提交范围。没有 Commit、Push、Merge、部署、正式ADR或业务数据库升级。

## 7. 保留限制与 C2A-2 前置条件

- Workflow SQLite 内接受头、Record/outbox 为真实单事务；Registry、代码文件与 Identity 分属不同来源，没有联合 CAS。采用复制、摘要与重复校验，发现漂移即拒绝；最后一次外部读取到 Workflow commit 间的变化、精心安排的 Registry ABA 不能宣称已被原子排除。
- 来源读取/规范化是有大小与数量限制的同步操作，无可抢占硬截止期；实现摘要依赖本机可读源码文件及原始字节，行尾/打包方式变化也可能保守拒绝。不存在“按历史代码摘要自动安装/执行代码”的能力。
- 当前验证是模板与确定性非模板来源接受；未调用外部供应商模型或部署新生产装配。旧通用受信任 Provider 的兼容格式只代表历史/受信任接受事实，不是新版物化资格。
- 新 L1 Profile 本身仍是规划内容，不能代表完成事实、权限或资源预留；其冻结不扩大模型权威。
- 下一阶段必须明确 Initial/revision 来源分支、无源图→GraphVersion1 的正式合同、确定性 ID/时间、完整候选/Bindings/Package 持久化、最终来源与权限 fence、唯一物化 Journal、Head+Run 原子 CAS，以及无 Permit 真实派发拒绝。本轮没有提前实现这些行为。

结论：**SELF-TESTED；已具备进入 C2A-2 的来源合同自测前置条件，建议先进行独立验收。** 新 Initial Commit 有版本化、可重建且由唯一接受权威绑定的来源；历史无证明记录不自动升级；首次物化、GraphVersion1、ACTIVATED_PAUSED 和任何执行许可均未实施。本结论不替代独立 ACCEPT，也不将跨库剩余窗口宣布为已解决。
