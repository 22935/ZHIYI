# AgentOS Remote Resource Registration and Authentication Design

## Goal

让端、边、云资源可以被明确登记、归属和认证。远程资源只能更新自己的资源快照，签名请求必须具备有效时间戳和一次性 nonce；资源密钥只在注册或显式轮换响应中返回一次，服务端不保存明文密钥。

## Current boundary

当前 AgentOS 已经能够保存资源画像、接收远程观测并按资源位置调度，但还存在三个实际缺口：

1. 没有正式的远程资源注册接口，资源只能由进程内代码直接登记。
2. `authReference` 只是凭据引用，尚未关联可验证的资源身份。
3. 观测请求没有资源级签名和重放保护，不能证明请求确实来自声明的资源节点。

本设计只增强“完整 Agent/模型运行在哪个端、边或云资源”的位置选择链路，不实现神经网络模型层切分。

## Architecture

资源注册由已经通过 `InternalServiceAuthMiddleware` 的内部调用方发起。注册时校验远程 endpoint、`resourceId` 和 `ownerScope`，生成一次性返回的资源密钥，并把加密密钥、独立摘要、凭据 ID 和归属保存到资源数据库。服务端保存的是受配置主密钥保护的密文和用于快速校验的摘要，不是可直接用于 HMAC 的派生值。

资源观测请求同时满足两层认证：

1. 继续经过现有服务级内部 Token，不改变 Python 业务路由的内部访问边界。
2. 额外携带资源级凭据 ID、时间戳、nonce 和 HMAC-SHA256 签名，服务端校验资源身份、归属、时间窗口和 nonce 唯一性。

签名覆盖 HTTP 方法、请求路径、时间戳、nonce 和请求体摘要。服务端在签名校验边界解密当前有效 secret，再使用注册 secret 的 SHA-256 派生值计算 HMAC；数据库泄露本身不能直接得到可签名密钥。签名成功后才调用 `ResourceService.observe_remote`；观测序号递增校验继续保留，旧观测仍返回冲突而不覆盖新状态。

凭据轮换使用独立的 `POST /agentos/v2/resources/{resource_id}/credential/rotate` 接口。只有资源所属租户的 `admin`、`operator` 或 `system` 可调用；服务端在资源数据库事务内生成并替换凭据记录，旧 credential ID 立即失效，新 secret 只返回本次响应。轮换不修改资源画像、快照或快照版本；如果生成或持久化失败，事务回滚且旧凭据保持有效。

## Data and error rules

- 资源密钥只返回一次，不写入 `ResourceProfile`、日志或 API 投影；服务端使用 `AGENTOS_RESOURCE_CREDENTIAL_KEY` 加密保存 secret，生产环境缺少该主密钥时启动失败。
- 未登记资源、凭据不存在、凭据不属于路径中的资源、签名不匹配、时间戳过期、nonce 重复分别返回明确的 401/404/409 错误。
- 重复注册同一资源 ID 不覆盖原资源；需要轮换凭据时必须使用显式的凭据轮换接口，注册接口不会自动替换已有凭据。
- 远程资源必须有非 local 的 deployment tier、非 local 的 execution endpoint、非空 owner scope；本地资源不能使用远程签名观测接口。
- 检测到旧版 `resource_credentials(secret_hash)` 表时拒绝启动；旧表不能恢复出原始 secret，必须由运维执行显式凭据迁移或重新登记，不能静默把旧摘要当作 HMAC 密钥。
- 不以 IDW、默认资源或其他资源替代失败认证或不可用资源。

## Testing and acceptance

测试覆盖：注册返回一次性密钥、数据库重启后凭据仍可验证、未认证注册被拒绝、错误资源凭据被拒绝、过期时间戳被拒绝、重复 nonce 被拒绝、签名成功后观测更新、旧 observation sequence 仍返回 409、轮换后旧凭据立即失效、新凭据生效、跨租户轮换被拒绝、轮换不改变资源画像和快照、持久化失败不破坏旧凭据。完整 AgentOS 和 agent 测试必须继续通过，且提交只包含后端 worktree 文件。
