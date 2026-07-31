# 动态 ACG MVP 阶段 5 手动验收说明

本文用于人工演示三类受控动态图能力。三组验收均以 Chat、AgentOS Console 和 ACG View 中一致的“动态运行摘要”为入口，并以 ACG 图和“运行时变化时间线”为审计依据。

## 验收前准备

1. 启动 Agent、Java Backend 和 Frontend，确认运行详情、Progress 与 ACG View 可正常读取。
2. 准备能够稳定产生指定 Fault Injection 或结构化 `runtimeSignals` 的测试 Agent/测试配置。
3. 打开 Chat 发起任务，同时在 Console 或 ACG View 中用相同 Run ID 观察运行。
4. 不通过客户端提交 Patch；所有图变化必须来自运行内核的确定性链路。

## 脚本 A：动态扩图

1. 启动会在 `risk_analysis` 产生 `EVIDENCE_MISSING` 的合同审查任务。
2. 启动时确认摘要中的图版本为 `v1`、动态步骤为 `0`。
3. 第一次 `risk_analysis` Attempt 结束后观察时间线：
   - 出现“检测到证据缺口”；
   - 随后出现“补救子图已应用”；
   - 显示 `v1 → v2`、目标节点和原因码。
4. 观察 ACG 图新增 `evidence_retrieval → evidence_validation`，新增节点带“+”标记，原入边显示为当前 API 暴露的失活/历史状态。
5. 确认新增节点状态依次变为 running、completed，证明它们真实参与执行。
6. 点击 `risk_analysis`，确认 Attempt 历史保留第一次结果，并出现第二次 Attempt。
7. 最终确认 Run 完成，摘要的动态图版本、动态步骤数和 Patch 数与时间线一致。

## 脚本 B：绑定切换

1. 启动存在 primary/backup 两个候选 Binding 的合同审查或代码审查任务。
2. 令 primary 在首次执行时产生 `BINDING_UNAVAILABLE`。
3. 观察时间线先显示“执行绑定不可用”，再显示“备用执行绑定已启用”和“执行绑定切换”。
4. 确认节点数量和边数量没有变化，图版本只增加一次。
5. 点击目标节点，确认：
   - 当前 Binding 已变为 backup；
   - Binding 历史保留 primary 与 backup；
   - Attempt 1 的失败记录仍存在；
   - Attempt 2 使用 backup。
6. 确认摘要中的 Binding 切换数增加，Run 可继续完成。

## 脚本 C：条件分支

分别执行 high 与 low 两组输入。

1. 启动包含 IF 与 Join 的确定性条件工作流。
2. IF 完成后观察时间线中的“条件分支决策”和“条件分支已激活”：
   - 显示条件节点；
   - 显示选中的 case；
   - 显示终结边数与跳过节点数；
   - 显示图版本变化。
3. 在图上确认选中边为 ACTIVE，未选边为 TERMINATED；尚未激活的边使用 INACTIVE 样式。
4. 确认未选路径节点为 `SKIPPED_BY_CONDITION`，节点弱化且没有 Agent Attempt。
5. 确认选中路径执行后 Join 继续，后续节点最终完成。
6. 对 high、low 两组输入重复检查，确认各自只激活一条路径且结果稳定。

## 通过标准

- Chat、Console、ACG View 的摘要统计一致；
- Progress 发现 `graphVersion` 变化后自动刷新图和时间线；
- 图结构不变时状态更新不会重置当前选中节点和视图位置；
- 时间线是可读说明而非原始 JSON dump，展开详情会隐藏敏感字段；
- 三类变化均能从 Event/Decision 追溯到 Patch、图版本和目标节点；
- 页面在旧 Run 缺少新增字段时仍可正常显示。
