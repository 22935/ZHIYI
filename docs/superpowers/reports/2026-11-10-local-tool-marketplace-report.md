# 本地工具资源商店阶段交付报告

日期：2026-11-10。功能分支：`feat/local-tool-marketplace`。工作树：`E:/Project/Kinlin_AI/.worktrees/local-tool-marketplace`。基线：`cf00fbb8`。

## 已交付

| 内容 | 结果 |
| --- | --- |
| PDF 解析 | 平台目录项、安装包、真实文字提取、页范围、页码/元数据/提取器版本；扫描 PDF 和加密 PDF 明确拒绝 |
| 文件格式转换 | 文本/HTML/Markdown、CSV/JSON、DOCX 文字表格、XLSX 活动表和 PDF 文字导出；仅支持声明组合 |
| 运行链路 | 确定性 ZIP、SHA-256、固定 Python 模块、独立目录/端口/凭据、loopback HMAC 与 nonce 防重放 |
| 商店操作 | 平台启动生成目录；安装后可上传文件、解析、转换、下载结果、停止和卸载 |
| 资源接入 | `device / tool_service / agentos_http`，分别声明 `pdf.parse`、`file.convert`，真实 ACG HTTP 适配器合同测试通过 |
| 生命周期 | 周期探活、停机清理、重启任务收敛、进程绑定凭据保护、Windows 删除锁有界重试、巡检/卸载串行提交 |
| 审计 | 资源登记、凭据轮换、观测拒绝、CAS 冲突、模型观测写入失败；内存/SQLite、过滤查询及分类计数 |

工具实现属于 `components/marketplace/builtins`；安装编排属于 `marketplace/application`；资源生命周期事实仍由 `components/resource/application` 管理。资源领域层不承担文档解析或启动进程。

## 如何使用

平台维护者先在运行 AgentOS 的 Python 环境配置文档工具依赖：

```powershell
python -m pip install -r apps/agentOS/requirements-local-tools.txt
```

启动平台后进入“资源商店”，安装“PDF 解析”或“文件格式转换”。任务为 running 后，在“已安装”点击“使用工具”，选文件并执行。PDF 文字直接显示，转换结果通过下载按钮保存。

代码包不包含 Python 解释器或第三方依赖，安装 API 不执行 pip、不联网下载。缺少平台依赖时安装失败；本次工作实现的是受控本地目录分发，外部仓库接入仍不在本期范围。

## 支持格式与限制

| 输入 | 输出 |
| --- | --- |
| txt | md、html |
| md | txt、html |
| html | txt、md |
| csv | json |
| json（对象数组） | csv |
| docx | txt、md、html |
| xlsx | csv、json |
| pdf（文字层） | txt、md；解析器另外输出按页文字与元数据 |

单文件最多 20 MiB，PDF 最多 200 页，文本最多 100 万字符，表格最多 5 万数据行，工具工作进程最多 30 秒。输出写入 `outputs/<任务 UUID>/result.<格式>`，不覆盖源文件。Office ZIP 解析前校验展开大小及压缩比；公式只读取缓存值，CSV 导出防止公式注入。

DOCX/XLSX 是内容提取与表格转换，Markdown 导出采用文本转义，不承诺 Office 排版保真；不执行宏、联网外链或公式，不生成 PDF/DOCX/XLSX，不支持 OCR。ACG 任务仍需明确能力、策略和工作区输入，安装不会自动生成业务 Agent 或 Planner 模板。

停止后的工具需卸载后重装才能重新运行；重启后旧任务置为 stopped，并禁用旧 Runtime。卸载会删除该安装的输入和结果文件，请提前下载需要保留的输出。进程绑定凭据不能单独通过通用接口轮换，需要重装更新。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| 资源、商店、模型适配器和 HTTP 执行适配器 | 192 passed |
| 平台装配与商店 API（含实际安装/上传/执行/下载及跨租户拒绝） | 10 passed |
| 资源中心组件、商店 API 前端与页面测试 | 23 passed |
| `npm run build:web` | 通过 |
| `git diff --check` | 通过 |

后端组件验证命令（在 `apps/agentOS`，使用支持 pytest-asyncio 的 Python 环境）：

```text
python -m pytest -q --asyncio-mode=auto tests/components/marketplace tests/components/resource tests/adapters/test_resource_model_execution.py tests/adapters/test_resource_execution.py
```

平台装配/API 验证命令（仓库根）：

```text
python -m pytest -q apps/agent/tests/test_execution_runtime_application_wiring.py apps/agent/tests/test_agentos_v2_api.py::test_marketplace_catalog_requires_backend_and_install_is_tenant_scoped apps/agent/tests/test_agentos_v2_api.py::test_marketplace_real_tool_upload_execute_download_and_owner_isolation
```

前端验证命令（`apps/frontend`）：

```text
npx vitest run src/components/resource-center src/services/api/agentos/api/marketplace.spec.ts src/views/ResourceMarketplaceView.spec.ts --reporter=dot
npm run build:web
```

测试 API 使用工作树内的隔离验证环境；验证过程中补齐了已有应用依赖。对 Python 3.13 全局环境中被替换的既有依赖已恢复原版本，后续验证依赖留在隔离环境内。

## 已有失败的基线对照

为确认扩大回归中的失败来源，单独检出未改动的 `cf00fbb8` 做同环境对照：

- `test_agentos_v2_api.py` 和平台装配测试合计：改动前后均为 27 failed、42 passed，失败用例集合一致。包含旧 Workflow/ACG fixture、资源投影和工作区预览等已有问题；新增商店用例另行验证通过。
- `serverAsr.spec.ts`：改动前后均为 8 failed、5 passed，失败集合一致。未把这些失败写成“全项目测试通过”。
- 生产构建原有 ASR `ArrayLike` 可写类型错误已单独修正，只改变类型声明，构建通过；没有扩展修改语音行为。

## TODO 与提交

完成并移除 `resource-plane-observability`、`resource-observability`；修正 `scheduling-policy` 过时注释。集中式数据库、KMS/HSM、密钥宽限期、配额权威源、Agent 热迁移、shell 授权和公共 API 弃用等 TODO 保留真实前提，详见资源器 README。

| 提交 | 阶段 |
| --- | --- |
| `ab07c40d` | 本地工具设计 |
| `2423362a` | 实施计划 |
| `73921130` | 资源生命周期审计 |
| `ffebe548` | 安全工具合同 |
| `30df96a4` | PDF / 文件转换实现 |
| `f486d38f` | 可校验安装包与真实工具服务 |
| `95527c70` | 独立修正 ASR 构建类型错误 |
| `faea2a01` | 商店 API、健康生命周期和前端使用入口 |
| `20876bc5` | 失败结果的 ACG 执行语义 |
| 分支 HEAD | 最终审计、生命周期加固、TODO 注释及文档报告 |

按用户要求保留功能分支和工作树，未合并主分支、未推送远端。主工作区的既有及会话期间新增改动没有纳入这些提交。

临时基线对照工作树 `E:/Project/Kinlin_AI/.worktrees/local-tools-baseline` 也予以保留：清理操作被自动审批策略拒绝，返回 `blocked by policy`；没有继续尝试删除。
