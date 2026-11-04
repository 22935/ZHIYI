# PR-UI-05C-R2：Reconciliation 状态下的进度观测隔离

日期：2026-11-04。基线：`7f672df661a44115067c5236517a94453c8f082e`。

## 问题

Run 与 Progress 属于同一 Mission/Run，但状态或 runtimeRevision 冲突时，生命周期投影虽然保留 Run 的权威状态并标记 RECONCILING，仍将 Progress 暴露给 UI。由此可能出现 Run 显示“已完成”，进度条却显示旧的 50%、步骤计数仍来自运行中的快照。

## 修复合同

- `progressObservation` 保留身份匹配的原始观测，仅供诊断。
- `progressObservationState` 明确区分 TRUSTED、RECONCILING、STALE、IDENTITY_MISMATCH、UNAVAILABLE。
- `progress` 只暴露 TRUSTED 观测；冲突、过期、身份不匹配的数据不得进入展示指标。
- ProgressBar 在隔离状态下显示“进度观测待核对 / 已过期 / 身份不匹配”，隐藏百分比，并将未知活动数显示为“—”。
- Run Summary 仅使用可信 Progress 或同身份 Run/ACG 步骤证据；没有证据时显示“—”，不把未知值伪装成 0。
- Chat 将同一个生命周期投影中的观测可信状态传给真实 ProgressBar 和 Summary 组件。

## 回归覆盖

- 同 revision、状态不一致：保留 Run 的 COMPLETED，隔离 RUNNING Progress。
- Progress revision 超前：即使状态相同，也隔离待核对观测。
- Progress revision 落后：隔离过期观测。
- Mission/Run 身份不匹配：不暴露观测。
- 仅有合法 Progress、尚无 Run detail：保留临时进度展示。
- 真实 Shell / Chat 组件集成：completed Run + running Progress，不显示旧百分比、旧步骤计数或旧运行文案。

## 范围

仅修改前端生命周期投影、ProgressBar、Run Summary 和相应测试；不修改后端 Runtime、Run 状态权威、Dispatch、权限或执行合同。

## 验证状态

已增加单元与真实组件集成回归测试。当前执行环境无法直接 clone GitHub 仓库，需在项目工作区运行定向测试、前端全量测试、vue-tsc 和 build:web 后再确认验收。
