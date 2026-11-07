# PR-TS-00B-运行命令与隔离结果

> 日期：2026-11-07，Asia/Shanghai；HEAD：`8775130f22b0440398c876a99206a47054e0b30c`，master。
>
> VERIFIED：本轮命令、隔离副本查询或源码证据；INFERRED：由证据推导的设计/分级；UNKNOWN：仍缺证据；BLOCKED：本轮授权或环境不支持的验证。仅进行审计，未实施TypeScript后端。

## 预检查（只读）

执行Git status/rev-parse/branch/log/diff/cached diff、rg/Get-Content源码审查；Get-PSDrive空间检查；N03 Python -B读取manifest/PID、psutil进程创建时间/端口、只读Win32独占句柄、postgres --version与pg_controldata。未调用persistent up/status/down/recover，不用native.down作为“锁探针”，因为该函数会停止进程/重命名目录/写回执。

## 获准后的操作入口与结果

| 实际入口 | 结果 |
| --- | --- |
| N03 python -B PR-TS-00B-run-isolated-audit.py | 工具进程非零；快照验证PASS；第一次PG启动返回1，未遗留服务；isolation-evidence保留 |
| N03 python -B PR-TS-00B-run-copy-retry.py | 工具进程非零，pg_ctl回执TimeoutExpired；同一副本实际ready/redo成功；attempt2独立保留 |
| N03 python -B PR-TS-00B-complete-owned-copy.py | exit0；只读业务SELECT、身份元数据对账成功；验证所属PG fast stop exit0 |
| N03 python -B PR-TS-00B-supplement.py | exit0；副本SQLite/Grant投影/恢复日志/旧manifest核对；不重启PG |
| N03 python -B PR-TS-00B-review-schema.py | exit0；确认avatar_url与Chroma FK兼容问题；不写库 |
| python -B PR-TS-00B-build-reports.py | 新增报告与增量清单；原报告不覆盖 |
| N03 python -B PR-TS-00B-package.py | 校验原Home/源码/既有证据/脱敏；桌面ZIP和SHA-256，结果另存final-verification |

入口均位于本审计目录；完整pg_ctl可执行路径和参数见command-log.json。参数绑定127.0.0.1:25432、显式copy data/hba/ident目录、default_transaction_read_only=on、archive/preload/ssl关闭；start日志只保存在受限private-evidence。所有SQL源码在run-isolated-audit.collect_pg与reconcile脚本中，使用SELECT允许集；BEGIN READ ONLY→SET LOCAL ROLE pg_read_all_data→SET LOCAL row_security=on→SELECT→ROLLBACK，不创建角色、不DML/DDL。

副本可能进行WAL重放和正常shutdown checkpoint；SQLite查询副本可能使用WAL/SHM。快照只读保留，原Home2533文件哈希0变化，快照2276文件查询后SHA仍匹配。无schema-only dump：已有足够结构查询证据，不额外暴露原始dump。无全产品恢复/业务HTTP/SSE测试，不把这些标PASS。

失败参数`''`仅存在第一轮的历史启动argv；第二轮改为Windows实际空值。后续接管仅针对核对过PID/created/exe/copy cmdline/loopback端口的13508进程，停止后端口释放。没有对原PID38832或其他用户进程发信号。

## 打包前结束状态补充（VERIFIED）

打包校验发现4个并发tracked删除，HEAD未变，staged为空；本轮未执行这些删除，原样保留。开始时tracked干净、结束时Dirty。详见[并发工作区变更记录](PR-TS-00B-并发工作区变更记录.md)和final-verification.json；此结束状态优先于前文生成时的Git观察。审计引用源码与旧产物哈希仍一致。
