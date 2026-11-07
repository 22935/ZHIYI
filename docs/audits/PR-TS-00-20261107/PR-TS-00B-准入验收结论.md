# PR-TS-00B-准入验收结论

> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

## PR-TS-00B：CONDITIONAL ACCEPT

真实数据补证成功，先前“数据库不可用、历史owner未知”的阻断已解除。**PR-TS-00可作为迁移准入审计有条件关闭，PR-TS-01：GO（仅架构/受限骨架）**。这不是TypeScript业务切换、真库迁移、旧Java删除或发行部署许可。本轮结束停止，等待正式验收，不继续实现。

## 判定依据

| 项目 | 状态/结果 |
| --- | --- |
| 当前Git | VERIFIED master/8775130f；tracked/staged diff为空；原审计未跟踪文件全部保留 |
| 冷快照与副本 | VERIFIED 2276文件、109592569字节、SHA-256一致；PG副本redo、查询、fast stop成功；原2533文件哈希0变化 |
| 真Flyway | VERIFIED V1–V13成功、script/checksum逐条匹配，不靠表存在推断 |
| 真实身份 | VERIFIED PG唯一U01，与所有非空历史owner一致；tenant原始缺失、Grant归一sentinel；唯一冻结Run授权一致 |
| LocalIdentity | INFERRED规范可冻结：保留旧users.id，raw tenant缺失，Home版本映射，失配fail closed；未实施 |
| 未解决P0实际不一致 | 本轮未发现阻断**只搭骨架**的owner/Grant/schema/恢复副本P0不一致；未来P0控制仍为强制门禁，未实现不称已修复 |
| 原快照完整性限制 | 外部Workspace两处未包含；只读审计无写影响；涉及外部项目写入/产品恢复前另补备份和演练 |
| Chroma | VERIFIED供应商FK指向不存在的单数collection；实际collections关联0缺失；P2单列，未修库 |
| HTTP/SSE/应用E2E | UNKNOWN/NOT RUN；未取得整套应用启动或业务测试执行证据，本轮仅源码合同与隔离计划 |

## PR-TS-01的明确允许范围

可在随后正式授权的PR中创建TS骨架、锁定候选依赖、定义ports/DTO/error/LocalIdentity/本机准入/ServiceSpec、建立纯架构与独立fixture测试；使用独立临时目录与端口，不连接本机真库，不写用户数据，不打开真实Workspace，不替换18080，不修改Python/Hands执行语义。

此GO是阶段范围判定，不代表本轮已开始PR-TS-01。任何真库/外部Workspace写入、旧数据迁移、产品切换均需对应前置条件和正式审批/验收，不能由本结论自动继承。

## 剩余P1/P2及延后条件

| 事项 | 等级 | 可延后至 | 不可跨过的门禁 |
| --- | --- | --- | --- |
| context-packs/node enabled活动Java缺口 | P1 | TS-05 | 正式gateway+closed projection+owner/status合同测试，不复制Python逻辑 |
| History RAG下载缺口 | P1 | TS-04/05 | 受控文档定位/owner/二进制下载合同，不能直接开放路径 |
| SSE sid替换/取消落库恢复 | P1 | TS-05 | 无登录准入、timeout/Abort/事务/幂等负面测试通过 |
| 旧suite全套隔离证明与等价测试 | P1 | 首次运行各suite及对应迁移PR | 不碰真实数据/固定生产端口；PG15/Redis/真实SSE不能用H2代替 |
| 全产品冷启动/停止/恢复/外部项目备份 | P1 | TS-07及任何外部文件写入测试前 | 无误杀、进程身份正确、全恢复一致；目前只是PG副本恢复验证 |
| 无登录Host/Origin/IPC联动 | P1 | TS-01合同/TS-02接真数据前 | 实测否定伪造身份和跨站操作；不能只删JWT |
| 两条无消费者Chat wrapper/休眠ASR | P2 | TS-06 | 显式弃用记录；未来恢复入口重审合同，不本轮删源码 |
| Chroma供应商FK定义 | P2 | RAG依赖/存储迁移前 | 隔离验证FK行为；禁止顺手改原库或重建索引 |

所有P0迁移风险（Actor/Grant错配、服务身份/本机准入、进程所有权、schema单写与备份）仍在目标设计/各阶段强制验收，不以当前只有一用户免除隔离、安全与恢复测试。

## 停止边界与命令证据

所有有运行/写入效果的操作只在新审计文件、E盘快照/查询副本/私有证据、桌面ZIP及其摘要。初始/失败/重试/最终停止证据独立保留；首次错误与管道超时如实记录，不挑选绿色结果覆盖失败。原cluster没有启动，原Home/业务源码没有修改，未安装依赖、未建backend-ts、未删除Java、未提交或推送。

未运行任何现有业务测试；本轮通过的是备份哈希、副本PG查询、SQLite元数据完整性与引用检查、主清单完整性和产物脱敏检查，不能报告成mvn/Vitest/E2E通过。最终命令/进程/端口/哈希与ZIP验证见 `PR-TS-00B-final-verification.json`、运行命令报告和交付manifest。

## PR-TS-00主清单的增量引用

不改旧报告、旧README或四个主CSV。新增 `PR-TS-00B-主清单引用与完整性核对.csv` 将四个原CSV的行数/SHA-256与本轮补证关联，`PR-TS-00B-route-supplement.csv` 对五缺口逐项补充处置；`PR-TS-00B-交付索引.md` 链接全部历史和本轮报告。这是在“不覆盖历史报告”约束下的增量补齐。

## 打包前结束状态补充（VERIFIED）

打包校验发现4个并发tracked删除，HEAD未变，staged为空；本轮未执行这些删除，原样保留。开始时tracked干净、结束时Dirty。详见[并发工作区变更记录](PR-TS-00B-并发工作区变更记录.md)和final-verification.json；此结束状态优先于前文生成时的Git观察。审计引用源码与旧产物哈希仍一致。
