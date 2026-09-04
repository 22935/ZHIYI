# Edge-Cloud Resource Runtime Completion Design

## Goal

把资源器从“可以登记、筛选和模拟绑定”推进到可真实运行的端—边—云资源闭环，同时保持资源位置选择与神经网络模型层切分两个概念独立。

## Scope and boundaries

本阶段包含五个互相衔接的资源运行时能力：

1. 根据已登记的远程资源画像自动构造执行 Adapter，并支持资源注册后动态生效；
2. 远程执行请求复用资源凭据，使用 method、path、timestamp、nonce 和 body digest 做 HMAC 签名；
3. 资源画像、首份快照和初始凭据在同一资源存储事务中完成注册；
4. 将心跳、可靠性、延迟和强制健康状态持久化，并在多个 AgentOS 进程之间共享；
5. 提供真实 HTTP 端节点、边节点、云节点联调样例和可重复验收脚本。

神经网络模型层切分不复用 `ResourceProfile` 的 deployment tier，也不把一个完整步骤的资源绑定描述成层切分。本阶段只定义独立的切分合同和拒绝未实现切分请求的边界；真正的层切分在后续独立阶段实现。

当前已落地的模型层边界位于 `contracts.model_partition` 和
`components.model_partition`：它能校验连续层区间、每层唯一放置、跨层
Tensor 边界和形状合同；执行器目前明确返回
`MODEL_PARTITION_UNAVAILABLE`。这表示合同和失败语义已经固定，但不表示
神经网络已经完成跨进程层间传输或实际推理。

## Architecture

`ResourceService` 继续是资源画像、快照和凭据的权威入口。运行时增加一个按资源 ID 延迟构造的 Adapter 工厂：本地资源继续走进程内 Agent；HTTP/HTTPS 远程资源由 `HttpResourceExecutionAdapter` 根据当前凭据动态签名；不支持的协议或缺失凭据直接报出明确配置错误，不回退到本地执行。

远程执行请求使用与观测相同的 canonical signing 规则。Adapter 每次请求都从凭据提供器读取当前 credential ID 和 secret，因此显式轮换后下一次执行立即使用新凭据。请求路径由 endpoint 统一规范化：地址已经包含 `/execute` 时不重复拼接。

资源注册通过 `ResourceStore.register_remote` 完成单事务写入；内存实现使用同一把锁，SQLite 实现使用 `BEGIN IMMEDIATE`。健康状态拆出持久化 `ResourceHealthStore`，内存实现用于单进程测试，SQLite 实现用于默认运行时；健康读取按时间计算超时，且不把持久化的旧 ONLINE 状态当作当前健康证明。

真实联调使用三个独立 HTTP 进程：terminal、edge、cloud。云端 AgentOS 负责资源注册、调度和签名执行；edge/terminal 节点提供最小 `/execute` 与 `/observation` 服务。联调验证成功执行、签名失败、nonce 重放、边节点超时后的云端重绑定和节点重启后的健康恢复。

## Failure rules

- 远程资源没有凭据、endpoint 或支持的协议时，绑定/执行明确失败；不得静默使用本地 Agent、默认资源或 IDW 类替代逻辑。
- 注册事务任何一步失败，画像、快照和凭据全部不落库。
- 执行超时只记录失败并触发既有受限重绑定；无法找到健康候选时明确失败，不伪造输出。
- 健康数据库不可用时，生产运行时拒绝启动或明确进入不可调度状态；不退回进程内健康真源。
- 真实联调脚本必须检查响应签名、请求 nonce、资源 ID、运行 ID 和步骤 ID，不能只检查 HTTP 200。

## Acceptance

- 自动 Adapter 测试证明：资源画像注册后无需手工注入即可执行；凭据轮换后新请求使用新 credential；地址规范化不会产生 `/execute/execute`。
- 安全测试证明：改 body、path、timestamp、nonce、credential 任一字段均失败，旧凭据轮换后立即失败，重放请求返回冲突。
- 事务测试证明：凭据写入失败或资源写入失败不会留下半注册资源。
- 跨进程健康测试证明：进程 A 上报的状态可被进程 B 读取，重启后旧状态按策略过期，新的远程心跳可以恢复调度资格。
- 三进程联调脚本可重复运行，并输出每一步的资源绑定、签名结果、故障切换和恢复结果。
- 层切分请求必须使用独立合同；当前未实现层切分时返回明确的 `MODEL_PARTITION_UNAVAILABLE`，不得伪装成端边云资源绑定。
