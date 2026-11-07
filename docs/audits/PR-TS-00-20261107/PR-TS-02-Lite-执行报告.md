# PR-TS-02-Lite 执行报告

日期：2026-11-07（Asia/Shanghai）。基线 HEAD：`af826587f05320e905c224aceae9f1d0c12a170f`。

结论：**PASS，限本机受控身份配置验证。** 用户明确批准后，新增当前受保护 N03 Home 内的 `identity/local-identity.json`；沿用 `zhiyi-local-identity-v1` 六字段格式。报告不包含真实 UUID、配置正文、凭据或完整私有路径。

## 可信来源与写入边界

- VERIFIED：PR-TS-00B 冷快照 manifest SHA-256 与已记录值匹配；全部 2,276 个快照文件哈希匹配。
- VERIFIED：原 Home 的 2,533 个历史文件与 PR-TS-00B 私有指纹逐项匹配。因此，本轮使用的历史身份来源与此前 PostgreSQL 单用户对账保持同一数据基线；本轮没有重新查询或启动 PostgreSQL。
- VERIFIED：以 `mode=ro&immutable=1` 读取已核验快照的 workflows/identity SQLite；两个来源数据库均无非空 WAL，完整性检查通过。Run、Task、Mission 各 1 条，唯一 owner 一致，tenant 保持 null。该 owner 对应 PR-TS-00B 已确认的唯一 PostgreSQL 用户 U01；明确排除了两个测试 fixture UUID。
- VERIFIED：Home manifest 的格式和 Home 归属匹配。配置的 ActorId、legacyUserId 沿用上述历史 UUID；Home binding 使用已核验 `environment.json` 的 SHA-256，不生成替代 UUID。
- VERIFIED：Home、来源文件和目标路径的既有祖先未发现重解析点；Home ACL 关闭继承，未发现非受信写权限。新目录与文件均仅允许当前用户、SYSTEM、Administrators，DACL 已保护，所有者可信。
- VERIFIED：首次创建采用同目录排他临时文件、flush/fsync、无覆盖 rename。权限设置中 `Set-Acl` 遇到 `PrivilegeNotHeldException`；改用 `icacls <本轮新建路径> /inheritance:d` 仅设置 DACL 后，目录和文件权限复核均通过。未修改 Home 根目录 ACL。

## 实际验证结果

| 验证 | 结果 |
| --- | --- |
| Node.js | VERIFIED：v24.19.0 |
| `npm run typecheck` | VERIFIED：通过 |
| `npm test`（包含 TypeScript 编译） | VERIFIED：4 个测试文件、76 项测试通过 |
| 现有 `loadIdentity` 读取真实配置 | VERIFIED：成功，ActorId 等于独立取得的历史 owner，tenant=null |
| 编译后的真实入口进程启动/关闭两次 | VERIFIED：均绑定 127.0.0.1 随机端口，live=200、ready=200，正常退出 0 |
| 重启稳定性 | VERIFIED：两次加载 ActorId 相同，且均匹配可信来源 |
| 临时业务探针 | VERIFIED：正确配置得到服务端历史身份；探针仅注册在临时验证实例，未加入生产代码 |
| 缺失文件、坏 JSON、篡改 ActorId、错误 Home binding、未知版本 | VERIFIED：5 种隔离配置均为 live=200、ready=503、业务访问=503，业务处理器执行 0 次 |
| 真实身份文件完整性 | VERIFIED：验证前后字节哈希和修改时间一致；负面验证仅修改受限临时副本 |
| 历史数据完整性 | VERIFIED：原有 2,533 个文件及快照 2,276 个文件哈希仍一致；Home 唯一新增文件为身份配置 |
| 清理 | VERIFIED：本轮服务均停止，验证临时目录全部删除，无残留验证进程 |

本轮执行了只读 Python 哈希/SQLite 核对、现有 Node `loadIdentity`、编译入口子进程重启、真实 loopback HTTP 请求和临时负面合同验证。未读取数据库密码，未接入外部服务；真实身份只在受保护文件和进程内存中使用，未写入仓库或测试 fixture。

## 范围与后续使用

`apps/backend-ts` 源码、目录结构和依赖均未变化。仅新增本报告和 Home 身份文件；四个预存 tracked 删除保持原状态。未提交、未推送。

本轮验证进程通过独立可信来源在内存中提供现有三个身份配置环境变量，未持久化用户/系统环境变量，也未接入 Native/Electron 启动器。因此，直接运行未配置这些变量的 `npm start` 仍按现有合同返回 ready=503。后续正式启动必须由可信启动方提供身份文件路径、预期旧 UUID 与 Home binding；不得从 HTTP 请求取得预期身份，不得把配置自身当作独立身份来源。

路径、ACL 和历史来源检查属于本轮受控导入步骤；现有 `loadIdentity` 没有新增自动数据库、ACL 或重解析点扫描能力。本轮验证不代表已完成整个 AgentOS 身份切换。
