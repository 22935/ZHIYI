# 本地工具资源商店设计

## 目标

在资源商店中提供两个由平台维护、可安装、可健康检查并可调度的本地工具服务：PDF 解析器和文件格式转换器。它们属于受控本地 Runtime，而不是由浏览器或用户命令直接启动的临时脚本。

本期同时完成能够在当前单机部署中验证的资源器可观测性 TODO；分布式存储、KMS/HSM、跨进程密钥轮换和租户配额等需要外部基础设施的 TODO 保持原状，并补充其依赖前提，避免伪完成。

## 边界

```text
平台 catalog JSON + signed/hashed ZIP bundle
  -> MarketplaceService install
  -> LocalPackageLauncher (shell=False)
  -> local Tool Service /health + /execute
  -> ResourcePlane Runtime registration
  -> ResourceBinder candidate
  -> agentos_http signed invocation
```

目录项和包仅由平台维护。安装程序校验 ZIP 包 SHA-256、归档路径、受控入口文件和回环地址。用户不能提交 shell 命令、可执行路径、下载 URL 或任意网络服务地址。

两个 Runtime 都使用 `tool_service`、`agentos_http`、`device` placement 和 `tool.invoke` 能力。工具服务自行校验输入、输出和文件工作目录；AgentOS 仅向固定的 `/execute` 合同发送 HMAC 签名请求。

## 工具包

### PDF 解析器

- 目录 ID：`tool.pdf-parser`。
- 开源基础：PyMuPDF；没有可提取文本的扫描 PDF 返回明确的 `OCR_NOT_AVAILABLE`，不伪造文本。
- 输入：平台管理的附件引用或工作目录内受控相对路径，以及页码范围和最大页数。
- 输出：按页文本、页数、提取器版本和受限元数据；不写入原文件。
- 限制：PDF 签名、页数、单文件大小、总文本大小和超时时间均受配置上限约束。

### 文件格式转换器

- 目录 ID：`tool.file-converter`。
- 开源基础：Pandoc 用于文本/Markdown/HTML/CSV/JSON/Docx 互转；LibreOffice headless 是可选的受控后端，用于 Office/PDF 需要时的文档转换。
- 首期白名单：`txt`、`md`、`html`、`csv`、`json`、`docx`、`xlsx`、`pdf`。具体支持矩阵由工具包声明，未声明组合返回 `FORMAT_NOT_SUPPORTED`。
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

## 测试

- 合同测试：目录包路径、输入格式和转换矩阵校验。
- 服务测试：ZIP 校验、启动、健康门槛、失败回滚、卸载。
- 工具测试：PDF 文本提取、扫描 PDF 明确失败、格式转换白名单、输出路径隔离和禁止覆盖。
- 资源测试：结构化事件涵盖登记、轮换、观测拒绝和 CAS 冲突。
- API/前端测试：目录展示、安装状态与非调度状态边界。
