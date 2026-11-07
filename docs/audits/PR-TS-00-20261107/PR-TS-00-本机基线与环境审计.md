# PR-TS-00-本机基线与环境审计

> 基线：`8775130f22b0440398c876a99206a47054e0b30c`，master；审计日期：2026-11-07（Asia/Shanghai）。本轮只生成审计材料，未实施迁移。
>
> VERIFIED = 本轮源码/命令证据；INFERRED = 基于源码的分析或目标设计；UNKNOWN = 证据不足；BLOCKED = 本轮无法安全检查。静态路由存在不等于运行成功；测试声明数不等于测试通过数。

## 结论：BLOCKED

源码盘点和迁移方案已经交付；真实数据库、运行 API/SSE 与冷启动验收没有证据，不能宣称全面审计已验收。`PR-TS-01: NO-GO`，先补齐本轮门禁，不自动实施下一阶段。

## Git 冻结

| 项目 | 本轮证据 |
| --- | --- |
| HEAD / branch | `8775130f22b0440398c876a99206a47054e0b30c` / `master` |
| 远端 master | `git ls-remote origin refs/heads/master` 返回相同 SHA |
| 参考 SHA | `1f3e37701b4977f452514bafd208092a2ac1d80a` |
| 拓扑关系 | `git rev-list --left-right --count REF...HEAD` = `0 23`，参考为当前 HEAD 的祖先 |
| 开始时 tracked / staged / untracked | 均为空，`git status --short --branch` 仅 `## master...origin/master` |
| 其他未提交 PR | 开始时未发现；本轮新增审计目录不会进入业务基线 |
| diff / cached diff | 开始均为空；结束复查见 `verification.json` |

已执行用户要求的六条初始 Git 命令；另做只读 ls-remote 与拓扑检查，未 fetch、切换、清理、暂存、提交或推送。初始干净状态来自本轮终端输出；`environment-evidence.json` 是随后快照，包含本轮自建目录。

完整参考差异在 `reference-delta.txt`。Java 生产差异集中于 AiSseGatewayService、ChatStreamPersistenceService、MessageMetadataQuery、MessageProjectionMapper 和 application.yml；相关测试也变化。因此 SSE 最大时长、取消落库、usage/上下文压缩字段按当前 HEAD 冻结，不能从旧 SHA 推断。证据：`git diff --numstat REF HEAD -- apps/backend`。

## 本机环境（VERIFIED）

| 项目 | 观测 |
| --- | --- |
| Windows | Windows 11 专业版，10.0.26100，build 26100（Win32_OperatingSystem） |
| Node / npm / pnpm | v24.19.0 / 11.17.0 / 10.14.0 |
| TypeScript | PATH 无全局 tsc；frontend 已安装 5.4.5，hands/electron 已安装 5.9.3；未安装/升级 |
| Java / Maven | Temurin OpenJDK 21.0.11 / Maven 3.9.12；pom 编译目标仍是 17，Spring Boot 3.2.0 |
| Python | 全局与 N03 venv 的解释器观测均为 3.14.5 |
| PostgreSQL | 本地二进制 `postgres --version` = 15.19；服务端版本 UNKNOWN |
| Redis / Memurai | memurai.exe 文件版本 4.1.2.0；运行 Redis 协议版本 UNKNOWN，未连接 INFO |
| Electron | node_modules 元数据 45.1.0；本轮未启动 Electron |

软件证据在 `environment-evidence.json`，npm/pnpm/全局 tsc 的结果来自本轮终端版本命令；不是依赖兼容性测试。pom：`apps/backend/pom.xml:23`（`<java.version>17</java.version>`）。

## N03 Home 与当前状态

扫描 `%LOCALAPPDATA%/ZhiyiNative` 下含 environment.json 的目录，发现 Home：`<LOCALAPPDATA>/ZhiyiNative/default-clean-20261106`；不是文档默认值 `default`。未读取/解密 credentials.dpapi。

`environment-evidence.json` 的 `2026-11-07T14:53:20.101918+08:00` 快照：environment format=`zhiyi-windows-persistent-v1`，portOffset=0。runtime-state 记录 8 个进程，但 psutil 确认全部 PID 已不存在；八个配置端口 loopback TCP connect 均失败，Get-NetTCPConnection 也未发现监听。因此 VERIFIED 当前观测为停栈/陈旧进程记录，不能凭状态文件声称 UP。实际启动命令、健康路径与所有权检查见原生运行链报告，当前进程健康 UNKNOWN。

对 environment.json、runtime-state.json 和最新日志文件保留 SHA-256。只保存日志名、字节数和 ERROR/WARN 数，不保存正文、完整 Workspace 路径或业务数据。共有 12 个日志会话目录；最新 java.log 含 ERROR 2 / WARN 6，不能由此推断当前故障根因或健康。历史启动回执不代替本轮启动验证。

## 安全边界与未执行事项

未运行业务服务 up/status/recover 命令（status 内部会连接依赖）；未连接或修改数据库；未执行 schema-only dump；未运行 mvn test、前端测试或原生生命周期测试。虽然 NativePostgres/NativeRedis 设计为随机端口临时实例，整个测试套件的文件删除、默认 URL、环境继承尚未逐一证明隔离，故本轮只审阅测试源码。详见模块报告与 `test-inventory.csv`。

## 产物与证据层级

所有写入限定本目录新建审计材料。八份报告和四份必需 CSV 外，增加源码哈希索引、Python 路由声明、身份触点、原生依赖、测试清单及安全环境快照。审计脚本只读源码、输出本目录；数据库 SQL 是未执行计划。机器清单是静态提取，UNKNOWN 字段保留原始表达式供复核，不能将它们当成运行合同证明。

## 结束校验（VERIFIED）

299个生产Java文件与源码索引范围内全部文件的SHA-256均与盘点时一致；tracked diff、staged diff为空；git diff --check成功；只新增本审计目录。145行route均唯一且行号指向Mapping注解，13个migration/115个测试源码文件与实际目录一致。审计Python脚本通过语法解析（未执行应用测试）。详见verification.json；这些检查不证明业务功能或数据库迁移成功。
