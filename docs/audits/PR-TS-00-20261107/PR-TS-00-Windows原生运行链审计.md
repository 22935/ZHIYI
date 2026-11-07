# PR-TS-00-Windows原生运行链审计

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 当前链（静态VERIFIED；运行BLOCKED）

N03 Home与所有服务观测见环境报告。端口组postgres15432 / redis16379 / ai18761 / host18765 / java18080 / frontend15200 / terminal18766 / debug19222，统一portOffset。不能把静态默认当运行监听；本轮均未监听。native-dependency-inventory.csv记录524处源码依赖引用（不是524个缺陷）。

| 源码证据 | 职责和迁移点 |
| --- | --- |
| `ops/scripts/infra/windows/native/persistent_runtime.py:154`（`def java_environment`） | 现有DB/Redis/JWT/内部auth/CORS环境映射；TS只退役用户JWT部分 |
| `ops/scripts/infra/windows/native/persistent_runtime.py:387`（`java = start('java'`） | java -jar → 平台backend描述符 node dist/main.js |
| `ops/scripts/infra/windows/native/persistent_runtime.py:241`（`def prepare_workspace_grants`） | PG权威表存在后投影；禁止TS另建授权真源 |
| `ops/scripts/infra/windows/native/persistent_runtime.py:560`（`def down`） | 显式服务顺序停机；保留创建时间/用户/可执行文件身份检查 |
| `ops/scripts/infra/windows/native/persistent_runtime.py:611`（`def backup`） | 停栈、全冷备、路径/哈希/reparse检查 |
| `ops/scripts/infra/windows/native/persistent_runtime.py:643`（`def restore`） | 原Home/PG版本/DPAPI检查、保留pre-restore |
| `ops/scripts/release/product_runtime.py:248`（`def ensure_local_account`） | 产品自动注册/登录与账户凭据持久化→LocalIdentity准备 |
| `ops/scripts/release/product_runtime.py:444`（`java = start_service`） | 发行版bundled JRE/JAR→bundled Node24和dist |
| `ops/scripts/release/product_runtime.py:151`（`def occupied_ports`） | 产品端口占用报错；不能继承开发takeover杀进程 |
| `ops/scripts/release/assemble_portable.py:116`（`def build_jre`） | jlink/JRE组装退役；检查Node24二进制签名/hash与许可证 |
| `ops/scripts/release/assemble_portable.py:168`（`def copy_backend_jar`） | JAR拷贝退役；dist+生产依赖+配置schema+版本manifest |
| `.github/workflows/backend-ci.yml:64`（`Package production jar`） | Maven/JDK gate在等价TS gate通过和最终切换前保留 |


## N03 开发启动

persistent_runtime.up核对Home/普通用户/非reparse、锁/陈旧进程/端口；PG与Redis准备完成后启动Java和Vite；Python native_startup预加载只读定义，release-file/nonce/launcher PID/creation-time门约束其正式装配。SQLite schema检查与PG权威表可用后的Grant准备并行，join后才放行AI；terminal、Hands按依赖就绪；最终AI/Java/frontend健康门通过才打开Electron。参考：`ops/scripts/infra/windows/native/persistent_runtime.py:413`（`with ThreadPoolExecutor(max_workers=2`）、`ops/scripts/infra/windows/native/persistent_runtime.py:399`（`--owner-created`）。

Java命令为PATH java -jar backendJar，Vite是node vite.js --mode electron，AI为venv python -m app.native_startup，Hands使用现有tsx service-main.ts路径，terminal为node src/main.mjs，Electron通过desktop_shell描述符启动。实际cwd/env参数以函数源码为准，敏感env不复制到报告；运行进程当前不存在，因此没有本轮实际cmdline可核实。

健康门：Java `/actuator/health/readiness`，AI `/health/ready`，Vite后端代理readiness；PG通过SQL SELECT1，Redis ping，Hands/terminal按自身检查。不要删除Actuator路径后忘记更新supervisor；可先由TS提供兼容readiness和live/ready路径，等描述符切换再明确退役别名。

## 产品发行链

assemble_portable组装Python/JRE/Node/PG/Memurai、Java JAR、Hands及Electron renderer壳；build_jre用jlink，包校验与version manifest仍列JRE/JAR。product_runtime使用包内解释器；AI直接uvicorn单worker，Java用bundled java -jar。产品无Vite/CDP，桌面进程存活+窗口出现作为就绪；ensure_local_account注册/登录后Main再bootstrap会话。产品端口被占用仅拒绝，不杀用户程序。

开发stack现有takeover与产品fail-on-occupied是已存在差异，不能把其整个生命周期实现互换。TS迁移需共用一个ServiceSpec/进程身份/备份/停止合同，以profile显式选择开发热更新与发行静态资源、端口冲突策略；产品拒绝占用的策略必须保留。开发是否继续takeover由后续明确决策，不以新增Node后端为由扩大杀进程范围。

## JVM/Maven/JRE退役闭包

变更范围不止一行java.exe：persistent ports键/java_environment/backendJar、product PATH/required paths、assemble build_jre/copy_backend_jar/--jar/manifest/包自检、CI JDK/Maven/test/package、健康脚本、状态回执/停止顺序和相关测试均须同步。`native-dependency-inventory.csv` 可按java_jar筛选；只删apps/backend会让现有Windows入口直接失败。

Node24编译产物入口设计为固定包内 `runtime/node/node.exe apps/backend-ts/dist/main.js`（仅设计路径，本轮未创建backend-ts）。开发也运行dist同一入口，由单独构建watch更新产物；不以tsx/watch进程替代正式服务所有者。进程记录从java迁移到backend，legacy记录只做有版本的兼容读取，必须校验PID+创建时间+可执行身份后才能停机，不能只按端口/PID终止。

## 数据/恢复约束

保持PG cluster与受限应用角色、Redis DB0缓存/DB1协调/DB2 provider state、Python SQLite/Checkpoint、Artifact、uploads、环境和DPAPI不变；用户JWT字段最终退役但内部token/HMAC/数据库凭据不能轮换或删除。产品内存储Redis授权限制未进行运行核验，不把Memurai开发版当已验证无限期发行方案。

backup要求所有受管业务进程停止、PG/Redis正常退出，sqlite句柄/OS锁释放后做完整冷拷贝；禁跟reparse，逐文件哈希。restore核对同Home/PG版本和DPAPI后保留pre-restore，再恢复数据。TS新增LocalIdentity映射与版本化schema状态需加入同一冷备清单；恢复不能只还原PG遗漏Artifact/SQLite/Grant epoch。依据：`ops/scripts/infra/windows/native/persistent_runtime.py:605`（`def require_stopped`）、`ops/scripts/infra/windows/native/persistent_runtime.py:658`（`previous = home.with_name`）。

## Node graceful shutdown 与验收

Windows控制台/桌面关闭、supervisor协议、SIGINT/SIGTERM可达性要实际测试；不能假定Windows会像Linux一样传SIGTERM。先拒绝新请求、ready=false、停止接收新流，给在途流bounded drain；截止时Abort上游、执行已定义的Chat失败落库，再关PG/Redis连接，最后报告退出。supervisor只在正常退出超时后按已验证身份回收。停止顺序保持Desktop→Frontend→AI→Host→Terminal→Backend→Redis→PostgreSQL；调整应用层drain需与Python可用窗口协调，不能仅改名称。

验收矩阵：冷启动、重复up拒绝、端口冲突、PID复用拒绝、部分启动失败回收、关闭中SSE、PG未就绪、AI失败、Hands失败、同Home恢复、冷备/损坏hash/旧身份映射恢复。现有 test_persistent_startup/test_native_stop/test_native_ai_preload/test_desktop_open/test_desktop_shell/test_terminal_service 属合同基线；本轮未运行，不宣称已通过。运行服务与发行包实测均BLOCKED。
