# PR-UI-03｜Mission Lifecycle Experience 实施记录

日期：2026-11-01。状态：**SELF-TESTED**。本地自动化验证通过，等待独立复验；不代表 ACCEPT。

## 1. 实际基线与修改保护

- 初始分支：`master`。
- 初始 HEAD、`origin/master`：`c597e1750145bbf7aaacb7d31685304735801a12`，与任务提供的历史基线一致，但以本次实查为依据。
- 开始时工作区、暂存区、未跟踪文件均为空。后续查询 GitHub、Gitee 的 live master ref，均为同一提交。
- 已阅读 PR-UI-00 审计、PR-UI-01 实施记录、PR-UI-02B 实施记录及 R1 身份隔离记录，并检查真实源码及调用链。本轮不重新实施 Mission Launcher。
- 验证期间出现并行用户修改：`ops/scripts/infra/windows/native/persistent_runtime.py`，4 行新增、1 行删除。本轮未修改、暂存或回退该文件。首次观测时间为 `2026-11-01T11:28:04.3826566+08:00`，SHA-256 为 `0B2287F4E89AE75722C3F053C67C747234CBDF5BAE7371B8903415FFF9D362C8`。
- 原始实施任务要求暂不提交和推送；用户随后明确授权按功能分步提交并推送。本次仅提交本报告所列前端改造及报告，不清理用户修改、不修改依赖、测试排除配置或后端执行合同。

## 2. 改造前后真实调用链

改造前：Vue Router → WorkspaceViewHost / 缓存路由快照 → MissionWorkspaceView → Workspace API → Registry / EditorGroup；RuntimeObservationAdapter 并行获取 Run、执行树、Trace、Provenance，RunRuntimeStore 维护原有 SSE。Editor 初始选择与已打开文档关联，Run 默认选择存在 latest/current 混用。失败恢复重新生成请求身份，不能可靠核对未知响应；Artifact 内容读取的旧成功响应可能覆盖新 Run。

改造后保留上述链路，增加纯展示解释：

`Workspace / Run 持久事实 → projectLifecycle → Editor Selection Policy → 原 Registry / EditorGroup / Inspector → 用户意图 → 原 API 与授权检查`。

`lifecycleProjection.ts` 无 Vue、API、存储和副作用；`editorSelection.ts` 仅记录当前 Run 的 follow/user 展示意图。Run 事实仍来自既有 API/Observation。`recoveryIdentity.ts` 只保存待核对命令快照，不保存执行授权，不成为 Workspace 或 Run 状态真源。FormalExecutionControls 继续拥有既有正式控制链，本轮只向其传递更严格的只读门禁。

## 3. 生命周期事实来源矩阵

| 事实 | 实际来源 | 使用边界 |
| --- | --- | --- |
| 所选 Mission、Run、Workspace entries | MissionWorkspaceProjection | 校验 missionId 与请求 runId；activeRun 表示选中快照 |
| Run 状态、lifecyclePhase、失败、Review、Formal Control、lineage | 同 Mission、同 Run 的完整 WorkflowRun | 详情优先于 Workspace 摘要；跨 Run 详情不参与解释 |
| Graph / Task / Artifact 身份 | Workspace entries 的 canonical 标识及内容引用 | 保留原 Registry 的编辑器和图身份链 |
| Task 语义状态 | Workspace Task entry | 不使用某一次 Attempt 的状态替换 Task 状态 |
| 全部已返回 Attempt / Execution | 原 Observation 已获取的 executionTree | tree.run、Observation、Attempt 必须属于所选 Run；不新增请求 |
| Formal materialize / activation / permit / dispatch | Run.formalControl | 解释阶段，不把 eligible 或推荐动作视为 Mission 当前身份或执行授权 |
| 最终交付 | 本 Run canonical run_deliverable entry | 同时要求 Artifact ID 与有效内容引用；supporting Artifact 不提升为 final |
| Provenance | 原 RuntimeObservation.provenance | 与交付身份分开显示；缺失时明确 NOT_OBSERVED |
| SSE / Planner 流式输出 | 原 RunRuntimeStore / RunProgressEditor | 仅临时输出；不得覆盖持久 Run 状态 |
| Mission 当前有效 Run | 当前合同缺失 | currentRunId=null，身份未确认，执行门禁失败关闭 |
| Checkpoint 恢复授权、未完成副作用 | 本次已有输入未提供足够事实 | 明确 NOT_OBSERVED；不由 checkpoint 存在推断恢复权 |

## 4. Lifecycle Projection 类型与映射

输出保留 rawStatus、normalizedStatus、phase、reason、Run 身份关系、只读状态、推荐 Editor/Inspector、availableActions、unavailableReasons、evidenceReferences、notObserved、交付与失败解释。availableActions 是查看、讨论、创建 successor 的意图提示，不能直接执行正式命令。

| 展示阶段 | 已实现的事实映射 |
| --- | --- |
| CREATED | Mission 存在且未选 Run |
| QUEUED | pending 且无更具体规划/正式阶段证据；兼容 queued 输入 |
| PLANNING | planning，或 pending + understanding/planning/graph_building 持久阶段 |
| AWAITING_CONFIRMATION | pending/planning + PLANNING_ACCEPTED、MATERIALIZED_INACTIVE、ACTIVATION_PREPARED 或 ACTIVATED |
| ACTIVATED_PAUSED | 正式状态 ACTIVATED_PAUSED |
| READY_TO_DISPATCH | ACTIVATED + ISSUED permit + dispatchEnabled + dispatchEligible |
| DISPATCHED | pending/planning 下存在属于所选 Run 的 dispatch 记录；受理不代表完成 |
| RUNNING | running |
| WAITING_REVIEW | waiting_review；与正式激活暂停分开 |
| RECOVERING | retrying，或 running + recovery 持久阶段 |
| FAILED | failed，或明确 Run failureCode/error.code；保留失败来源 |
| COMPLETED | completed/succeeded，normalizedStatus 统一 completed，rawStatus 保留 |
| CANCELLED | cancelled，独立于失败 |
| SUPERSEDED | superseded，独立于取消；lineage supersededByRunId 同时提供历史关系 |
| UNKNOWN | 未识别状态、无法解释的正式状态、缺失状态；不降级成 pending |

这些是展示阶段，不新增后端枚举。queued 字面值、通用 paused、skipped_by_condition 等不是本轮凭空增加的后端执行合同；paused、未知普通/正式状态按 UNKNOWN 处理。矩阵测试同时覆盖可解释输入和未观测/未知输入。

失败有真实 failed step 时定位 Task 与对象 ID；没有图且持久阶段是 planning 时显示 Planner；无法确认的失败层显示 `Run (layer NOT_OBSERVED)`。不根据“存在 formalControl”猜测失败层，不把 Attempt 状态当成 Task 结论。

## 5. Editor Follow 策略

- 每个新选中的 Run 默认进入 follow；用户主动打开文档、切换 Tab、选择文件/Task/Artifact/导航后进入 user。
- user 模式下刷新、Polling、SSE 与迟到 Artifact 只更新事实，不抢占 Editor。显式“跟随生命周期”恢复 follow。
- 使用 Run + phase + recommended entry + final contentRef 组成已处理交接键。同一事实重复刷新不重复交接；不再以 openEditors.length 判断自动转换。
- 首次规划打开 Progress；正式确认阶段在已有 Graph 可用时打开 Graph；审核定位实际 Review Task 并展示既有 Copilot/Review；失败定位失败 Task，无图时留在 Progress；完成等待经过身份校验的 canonical final。
- Artifact 延迟到达时，先显示 `Completed · Final deliverable missing`，最终引用齐备后交接一次。支持重新 follow、KeepAlive 离开恢复以及 Run 切换。
- 继续使用 WorkbenchLayout、EditorGroup、GraphEditor、TaskEditor、ArtifactEditor、Copilot 和 RuntimeInspector。侧栏按 EXPLORER / RUNS / TASKS / ARTIFACTS 组织既有贡献；Run 项执行 Run 选择，避免在错误投影中仅打开一个文档。

## 6. selected / current / latest / historical / successor 规则

实际检查 `apps/agentOS/src/runtime/v2/workspace.py` 的 project / _select_run，以及 `apps/agent/app/api/agentos_v2.py` 的 Workspace handler：activeRun 和 runs[].isActive 跟随请求选中的 Run；无显式 Run 时默认选择最近运行。这些字段不能证明 Mission 当前有效执行版本。

完整 Run 的 `lineage.supersededByRunId` 或 superseded 状态可以证明历史身份；sourceRunId 只能证明来源，不能自动推断源已经被 supersede。FormalControl 的 eligibility 是单 Run 能力；MissionRunRevision 的 CURRENT 是语义修订身份，都不能充当 Mission 级 currentRunId。

- selectedRunId：URL/用户当前正在查看的 Run，必须与返回数据匹配。
- currentRunId：当前合同缺失，始终 null；isCurrent 为未确认，显式历史时为 false。即使只有一个 Run，也不推断 current。
- latestRunId：从返回 rows 的有效 createdAt 取唯一最大值，仅供“最新创建”导航；并列或数据不确定时不选，不用于授权。
- historical：明确 superseded 状态或 supersededByRunId。
- successor：后端返回且验证 lineage.sourceRunId 的新 runId；源 Run 保持原始证据。

由于缺失 current 权威关系，Workbench 本轮对未确认身份也设为只读。这会禁用当前视图中的停止、原地重试、正式控制、审批、工具授权及修订应用；这是明确的安全降级，不能宣称当前 Run 执行权限体验已完整恢复。终态源仍可由用户显式创建 successor，最终接受与否由后端验证。

## 7. 历史 Run 只读证据与范围

EditorGroup → MissionEditor → MissionRevisionNotice 传递只读；decision/apply 按钮及处理器均门禁。AcgCopilotPanel 的历史/readonly 同时阻止 command、review decision、Planner answer、权限升级等变更动作，保留 read_only 讨论。FormalExecutionControls 不挂载只读/历史工具授权入口，原正式操作禁用。既有 Progress、Graph、Task、Attempt、Artifact、Trace、Provenance 的读取链保留。

恢复入口只允许 `successor_run`，快照验证明确拒绝 `current_run`，响应必须属于同一 Mission、拥有不同 runId 且 sourceRunId 匹配。历史 source 可以成为新操作来源，不能成为执行目标。

没有修改后端 API 或删除兼容协议：旧的、实际路由未使用的 `AcgVisualizationView.vue` / retryModeChoice 仍保留原 API 兼容。真实 AcgVisualization 路由指向 AcgEntryView；本报告证明的是当前可达 Workbench 链路，不声称已全仓删除 current_run 字符串或后端能力。

## 8. URL 与跨 Run 请求一致性

- 用户选 Run 使用 router.push；初始补齐 URL 使用 replace；back/forward watcher 按 URL 加载，不再次 push。
- 切换开始即中止旧投影请求、停止旧 Observation、释放原 SSE store、清除旧投影/Artifact 状态，再写新 URL。新 Run 失败时不把旧事实贴在新 URL 下。
- API 返回检查 controller、可见工作区、Mission 和 Run；Observation 回调额外核对 selectedRunId 与 observation.run.missionId。
- 明确 runId 的 403/404/未知/超时不 fallback。错误文案区分无权、缺失和加载失败。
- ArtifactEditor 的成功和失败分支均绑定发起请求的 controller、Run 和内容引用，修复组件复用时旧正文覆盖新 Run。
- 保留同一 Run 刷新时已有文档，避免闪烁；可见工作区按既有周期刷新，包括终态，以接收延迟交付和外部 successor。离开 KeepAlive 后停止刷新及订阅；不是新增第二套状态存储。

## 9. Retry / Resume / Rerun 操作身份

使用 sessionStorage 保存账户/租户/Mission/sourceRun 隔离的待核对快照，包含完整原负载、clientRequestId、kind、stepId（如有）及 canonical payload fingerprint；复用已有 canonicalLaunchJson 工具，没有修改 Mission Launcher 内核或其身份规则。

网络结果未知、刷新或重新挂载后，优先读原快照并重发同一命令、ID、负载与版本，不生成新操作掩盖未知结果。损坏、source 不符或 fingerprint 不符时失败关闭。确认后端返回合法 successor 才移除快照。sessionStorage 只用于操作核对，不授予执行权限。

- failed 且有真实失败 step：读取源 Run 的 runtimeRevision，调用既有 retryWorkflowStepAsync，mode 固定 successor_run。
- 规划失败且没有 Graph/失败 step：读取源 history config，使用原输入与插件/review 配置调用既有 rerunWorkflowAsync 创建新 Run。
- 其他允许的终态再次运行：同样从原配置创建 successor。
- 新响应验证 missionId、不同 runId 和 lineage.sourceRunId。源 Run 不更新、不重新激活。
- 每次选 Run 的恢复 UI 代次隔离旧操作的导航、error、finally/loading。已提交旧请求继续执行；不因切换取消已提交任务，也不阻塞新 Run 自己的恢复请求。

未知结果、冲突或损坏快照可能需要人工核对；本轮没有新增跨设备/跨标签页 operation 查询协议，不以重置身份自动“修复”。

## 10. 失败与 Canonical Deliverable 交接

在原 Inspector 贡献中复用 LifecycleEvidence，显示所选/最新/后继/未确认 current、失败对象与原因、checkpoint/副作用是否观测、禁止动作以及最终 Artifact 和 Provenance。Task Inspector 展开同 Run 的全部已返回 Attempt/Execution，不用最新失败 Attempt 覆盖 Task 已完成状态。

final 必须同时满足：成功终态、entry.kind=artifact、artifactKey=final、artifactType=run_deliverable、identityQuality=canonical、entry.runId=selectedRunId、非空 artifactId 和 contentRef。supporting、legacy、外来 Run、无内容引用都不能自动交付。

交付身份通过只表示可以打开现有 ArtifactEditor；内容、大小与下载仍由所选 Run 的原 Artifact API 读取与校验。Provenance 单独展示，存在 Artifact 不意味着 provenance 已验证。无 final 时保留成功事实并显示缺失，不把成功伪装成已交付。

## 11. 测试、失败反例与最终快照

分阶段执行，失败未跳过：

| 阶段 | 当阶段闭环结果 | 原始日志（临时目录） |
| --- | --- | --- |
| A 生命周期 | 22 tests 通过，后续矩阵增加至 24 | pr-ui-03-phase-a.log |
| B 跟随策略 | 25 tests；真实 Host 集成 3 tests 通过 | pr-ui-03-phase-b.log / phase-b-integration-2.log |
| C 身份/恢复 | 5 files / 54 tests 通过 | pr-ui-03-phase-c-closed.log |
| D 交付/失败 | 4 files / 54 tests 通过 | pr-ui-03-phase-d.log |
| E 导航/兼容 | 4 files / 70 tests 通过 | pr-ui-03-phase-e-third.log |
| 无图规划失败补丁 | 3 files / 52 tests 通过 | pr-ui-03-planning-recovery-after.log |

保留的确定性红灯证据：

1. `pr-ui-03-phase-d-before.log`：真实 ArtifactEditor 组件复用，B 正文先到、A 旧正文后到，A 覆盖 B；加请求所有权后回归通过。
2. `pr-ui-03-phase-c-integration.log`：replace 导致浏览器返回不能恢复原 Run；用户选择改为 push 后通过。
3. `pr-ui-03-recovery-owner-before.log`：A 仍 pending 时切 B，B 的恢复 API 未调用（预期 2 次，实际 1 次）；局部恢复 UI 代次修复后通过。
4. `pr-ui-03-planning-recovery-before.log`：没有 Graph 的 Planner 失败没有调用新 Run API（预期 1 次，实际 0 次）；原输入 successor rerun 补丁后通过。

其中按 `-t` 运行单一失败反例时，Vitest 将不匹配用例显示为 skipped；未使用 it.skip、@Disabled、excludes 或减少全量测试。原始失败日志保留，后续通过结果不覆盖失败证据。早期 fixture/期望不符的阶段日志亦保留，没有用这些失败日志宣称通过。

独立新增测试共 51 项：lifecycleProjection 24、editorSelection 3、recoveryIdentity 3、MissionLifecycle.integration 18、ArtifactEditor.identity 1、全部 Attempt 1、现有 MissionRevisionNotice 新增 readonly 1。关键集成使用真实 Vue Router、Pinia、WorkspaceViewHost、MissionWorkspaceView、Registry、EditorGroup、GraphEditor、ObservationAdapter 和 SSE store；布局/重型图绘制仅做展示替身，API 边界用 Deferred Promise 与假时钟控制。不靠固定 sleep。

覆盖规划→运行→审核/失败/完成、延迟 final、user/follow、KeepAlive、历史成功/新失败、历史失败/新成功、successor 再创建 successor、只读讨论与正式操作拒绝、外部 Run、URL back/forward、跨 Run 投影/Graph/Observation/正文迟到、403/404/超时、恢复丢响应/重载/重复提交、A 与 B 恢复 finally/loading 隔离及无图规划失败。每例卸载后检查 SSE 已释放；未知 API 访问失败，不隐藏 Promise rejection。

原 MissionWorkspace 31、Continuity 20、Copilot 20、RunProgress 30 等用例全部保留。调整的是与已确认合同冲突的期望（latest≠current、readonly 拒绝命令、SSE 不覆盖持久状态）以及缺少 canonical/lineage 的 fixture；原有普通 Chat、Launcher、正式控制/Review、Graph、Observation 等仍进入最终回归。

最终交付快照证据根目录：`C:\Users\LZX\AppData\Local\Temp\pr-ui-03\delivery`。该目录与早期迭代日志区分：早期两次全量 1039 tests 仅作迭代证据，不作为最后无图恢复补丁的验收结果。

| 最终命令（apps/frontend） | 结果 | 原始证据 |
| --- | --- | --- |
| npm test -- --maxWorkers=2 --minWorkers=1，加定向路径 | 41 files / 409 tests 通过，100.64s | targeted.log / targeted-result.json |
| npm test -- --maxWorkers=2 --minWorkers=1 | 142 files / 1040 tests 通过，253.15s（命令总计 255.64s），exit 0 | full.log / full-result.json |
| npx vue-tsc -p tsconfig.json --noEmit | exit 0，14.71s | types.log / types-result.json |
| npm run build:web | exit 0，38.74s；Vite 21.50s | build.log / build-result.json |
| git diff --check；新增文件尾空格/EOF 检查 | 通过，新增 11 个文件检查通过 | 最后工作区核对 |

全量日志保留既有测试中的 jsdom XHR AggregateError stderr 和 Vue Suspense 提示；不把“命令通过”描述成零日志警告。新增真实集成套件独立拒绝未声明 API 调用并检查订阅释放。项目原有 retry:1 配置未修改；最终 Vitest 无失败、无 skipped，未报告未处理异常。

源码快照覆盖 `git ls-files --cached --others --exclude-standard apps/frontend` 排序去重后的 612 个文件。对每个文件计算原始字节 SHA-256，以 `{path, sha256}` 数组写入 UTF-8 JSON 清单，再计算清单 SHA-256：

`8A5363B8AD7A6BB1DD9733580BE81F3D3C259194CA4A3F637B83B49FCA053C05`

source-before.json 与 source-after.json 的路径/逐文件字节摘要均一致，changes=0，清单 SHA 也相同。最终报告不在前端源码范围内；测试、类型检查和构建期间没有再修改前端文件。用户并行 Python 文件的 SHA 也与首次观测一致。

## 12. 修改文件与必要性

本轮前端共 32 个文件：22 个已跟踪文件修改，10 个新增文件；另新增本报告。无 backend、agentOS Runtime、Scheduler、Launcher 内核或 Workspace Store 改动。

| 文件/组（相对 apps/frontend/src） | 必要性 |
| --- | --- |
| workbench/runtime/lifecycleProjection.ts、editorSelection.ts、recoveryIdentity.ts 及各自 spec | 纯展示映射、follow 意图、未知恢复操作核对 |
| views/MissionWorkspaceView.vue / spec、MissionLifecycle.integration.spec.ts | 生命周期接入、URL/异步所有权、历史门禁、真实集成 |
| workbench/runtime/observation.ts、types.ts、context.ts | 保留已获取的同 Run 执行树，向原上下文传递派生生命周期 |
| workbench/contributions/project/LifecycleEvidence.vue、ProjectRunSidebarView.vue、index.ts | 在原 Registry/Inspector 组织事实与诊断 |
| ProjectTaskExecutionInspector.vue / attempts.spec.ts | 全部同 Run Attempt，保护 Task 语义状态 |
| components/workspace/WorkspaceExplorer.vue / spec | 原贡献按 Explorer/Runs/Tasks/Artifacts 组织，Run 导航真实切换 |
| EditorGroup.vue、MissionEditor.vue、MissionRevisionNotice.vue / spec | 历史与未确认身份只读贯穿修订控件 |
| FormalExecutionControls.vue、components/workbench/AcgCopilotPanel.vue / spec | 复用原正式控制链，阻止只读视图变更 |
| components/workspace/RuntimeInspector.vue、RunProgressEditor.vue / spec | 订阅生命周期与持久状态展示、诊断/交付缺失 |
| ArtifactEditor.vue / identity.spec.ts | 正文异步响应按 Run/内容身份隔离 |
| components/app/WorkspaceContinuity.spec.ts | 保留原双视图合同，纠正 latest/current 混用期望 |

用户并行修改的 `ops/scripts/infra/windows/native/persistent_runtime.py` 不属于以上清单，不作为本轮验证覆盖或交付内容。

## 13. 最小后端合同提案（未实施）

建议后续单独提供 Mission 级、同一原子快照中的 selectedRunId、currentRunId、current identity revision、明确的 supersession/source 关系和服务端计算的操作 capabilities。selected 与 current 可以不同，latest 仍只作展示。

必须定义 current 的权威语义、终态/并行运行/恢复后的指针更新、source 与 supersedes 的差异、未知身份处理及权限裁剪。变更 API 应在服务端复核 Mission 当前身份/版本和操作能力；前端不得以缓存或时间戳授予执行权。已有 operation ID / fingerprint / runtimeRevision 仍按原合同核对。

在该合同完成独立验证前，不解除本轮的身份不确定只读门禁，也不修改 Runtime 生命周期来迁就前端。此提案未修改任何后端代码或 API。

## 14. 限制与独立验收建议

- 本轮是本地自动化自测，不代表独立 ACCEPT、真实后端/模型 E2E、真实浏览器视觉验收或 GitHub Actions 已通过。
- 缺失 Mission current authority 是已证实的合同限制；正式操作在 Workbench 失败关闭，需后续合同落地后另验，不能把 latest/selected 当成补丁授权。
- Checkpoint 恢复授权、未完成副作用、下载真实字节与 Provenance 完整性未通过真实运行环境验证。已有输入无法证明时明确 NOT_OBSERVED。
- sessionStorage 支持同标签页未知结果核对，不解决跨设备操作发现；身份损坏/权限变化/409 需核对原操作，不自动新建身份。
- 可见终态 Workspace 继续原周期投影读取以发现延迟 Artifact/外部 successor；隐藏工作区会停止。后续可由既有事件合同优化，但本轮不增加状态层。
- 建议独立复验真实规划、正式确认、审核、Planner 失败无图、带 Attempt 失败、迟到交付与源历史证据；身份 authority 缺失时先验证执行按钮确实禁用，再按单独后端合同推进授权体验。

本轮结论：**SELF-TESTED，可提交独立复验**。所有最终门禁对应同一前端源码快照。代码与报告按生命周期策略、Workbench 集成与回归、实施记录三个功能边界提交；推送配置的 GitHub/Gitee 双远端并核验 live refs 后，最终提交号与远端结果以 Git 记录和交付回复为准。用户并行 Python 修改保持独立、未纳入提交。
