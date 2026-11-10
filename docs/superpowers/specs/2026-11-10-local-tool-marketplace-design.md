# 本地工具资源商店设计

## 目标

在资源商店中提供两个由平台维护、可安装、可健康检查并可调度的本地工具服务：PDF 解析器和文件格式转换器。它们属于受控本地 Runtime，而不是由浏览器或用户命令直接启动的临时脚本。

本期同时完成能够在当前单机部署中验证的资源器可观测性 TODO；分布式存储、KMS/HSM、跨进程密钥轮换和租户配额等需要外部基础设施的 TODO 保持原状，并补充其依赖前提，避免伪完成。

## 边界

```text
平台 catalog JSON + SHA-256 校验 ZIP bundle
  -> MarketplaceService install
  -> LocalPackageLauncher (shell=False)
  -> local Tool Service /health + /execute
  -> ResourcePlane Runtime registration
  -> ResourceBinder candidate
  -> agentos_http signed invocation
```

目录项和包仅由平台维护。安装程序校验 ZIP 包 SHA-256、归档路径、受控入口文件和回环地址。用户不能提交 shell 命令、可执行路径、下载 URL 或任意网络服务地址。

两个 Runtime 都使用 `tool_service`、`agentos_http`、`device` placement，分别只声明真实执行能力 `pdf.parse` 和 `file.convert`，不把通用 `tool.invoke` 当成已实现协议。工具服务自行校验输入、输出和文件工作目录；AgentOS 仅向固定的 `/execute` 合同发送 HMAC 签名请求。

## 工具包

### PDF 解析器

- 目录 ID：`tool.pdf-parser`。
- 开源基础：pypdf 7.0.0（替代计划中已弃用的 PyPDF2）；没有可提取文本的扫描 PDF 返回明确的 `OCR_NOT_AVAILABLE`，不伪造文本。
- 输入：工作目录内受控相对路径及页码范围；附件需先导入该安装工作区，页数上限由平台固定。
- 输出：按页文本、页数、提取器版本和受限元数据；不写入原文件。
- 限制：PDF 签名、页数、单文件大小、总文本大小和超时时间均受配置上限约束。

### 文件格式转换器

- 目录 ID：`tool.file-converter`。
- 开源基础：python-docx、openpyxl、Python Markdown 与标准库；首期不启动 Pandoc/LibreOffice，不隐式下载外部引擎。
- 输入白名单：`txt`、`md`、`html`、`csv`、`json`、`docx`、`xlsx`、`pdf`；输出只支持 `txt`、`md`、`html`、`csv`、`json`。具体支持矩阵见资源器 README，未声明组合返回 `FORMAT_NOT_SUPPORTED`，不宣称任意互转或高保真排版。
- 输入：受控工作目录内的源文件、明确的目标格式；输出必须写入独立任务输出目录，禁止覆盖源文件和写入工作目录外。
- 禁止宏执行、外部链接解析、公式计算、任意模板、任意命令参数和联网下载。

## TODO 完成范围

本期新增 `ResourcePlane` 的结构化资源事件端口和内存/SQLite 实现，覆盖：Runtime/Node 登记、凭据轮换、观测拒绝与 CAS 冲突。`resource_model_execution` 在观测写入失败时记录同一结构化事件。完成后移除这两处 observability TODO。

其余 TODO 按真实前提保留：

- 集中式数据库与跨主机 nonce 协调：需要 PostgreSQL/Redis 等部署依赖。
- KMS/HSM：需要密钥管理服务和密钥轮换流程。
- 密钥宽限期双验：需要密钥版本策略和部署协调。
- 成本、地域、租户配额调度：需要计费和配额权威数据源。
- 细粒度 shell 授权、Agent 热更新迁移、分布式健康：需要独立的安全/运行时项目。

## API 与商店体验

平台目录继续使用 `/agentos/v2/marketplace/catalog`。安装任务和 Runtime 的状态不可提前显示为可调度；仅在 `running` 且健康检查通过后显示为已连接工具。

资源商店目录项展示工具支持格式、是否需要额外本地引擎和磁盘需求。工具详情不展示启动参数、可执行路径、包内容或凭据。

首期交付还包括“已安装 → 使用工具”的受控文件上传、解析文字展示及转换结果下载。安装生成独立 Runtime ID、工作目录、随机 loopback 端口和签名凭据；相同目录项可由不同租户独立安装。代码包不包含 Python 或第三方依赖；平台部署需安装 `requirements-local-tools.txt`。安装 API 不执行 pip，也不访问外部仓库。

服务固定暴露 `/health` 和 `/execute`。执行成功返回 200 `AgentOutput`，工具失败返回 422；HMAC 验证包含时间窗和原子 nonce 去重。独立工作进程有 30 秒超时，单实例同时只执行一项文档任务，健康路由不被文档处理阻塞。进程绑定凭据拒绝数据库单边轮换，更新需重装服务。

后台健康巡检、正常关闭与重启状态收敛已接入；重启后旧任务置为 stopped 并禁用调度，不伪造自动恢复。停止后可卸载，卸载会删除该安装的输入和结果文件。ACG HTTP 执行适配器已做真实调用合同验证；Planner 业务模板与任务附件导入策略保持显式配置。

## 测试

- 合同测试：目录包路径、输入格式和转换矩阵校验。
- 服务测试：ZIP 校验、启动、健康门槛、失败回滚、卸载。
- 工具测试：PDF 文本提取、扫描 PDF 明确失败、格式转换白名单、输出路径隔离和禁止覆盖。
- 资源测试：结构化事件涵盖登记、轮换、观测拒绝和 CAS 冲突。
- API/前端测试：目录展示、安装状态与非调度状态边界。
