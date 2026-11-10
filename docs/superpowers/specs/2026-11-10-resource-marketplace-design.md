# 资源商店与资源管理设计

## 目标

在 AgentOS 内将“可安装的本地能力”与“已经运行、可调度的资源”分离。平台先维护受控本地目录与安装任务；用户可从商店安装模型、工具服务和执行服务，也可进入自定义资源配置。安装后的服务只有完成 Runtime 登记并通过健康检查，才进入端、边、云调度候选。

## 页面

资源中心调整为两个主页面：

1. 资源概览：展示端、边、云资源数量、健康、容量、运行模型与安装任务摘要。该页提供进入资源商店和资源管理的动作，不承载配置表单。
2. 资源管理：按 Device、Edge、Cloud 分层呈现 Node、Runtime、Model Endpoint，展示健康、容量、租约和运行状态。

资源商店为独立页面，包含三个视图：平台目录、已安装内容、自定义资源。目录项不会被当成可调度资源；已安装但未运行或未健康的内容也不会进入资源候选。

## 架构

商店是独立控制面组件，不放入 `components/resource` 的领域模型。

```text
marketplace/catalog      平台受控安装包描述与版本
marketplace/application  安装任务编排、状态迁移、Runtime 登记
marketplace/ports        Catalog、安装任务、包存储和本地启动器接口
marketplace/infrastructure 本地目录、任务存储、受控包校验与启动实现
components/resource      已启动 Runtime 的登记、健康、容量和调度事实
```

目录项包含 ID、类型、版本、展示信息、包路径、SHA-256、硬件要求、受控启动模板及 Runtime 声明。首期包路径必须位于平台配置的本地包根目录；不接入 URL、外部仓库或页面提交 shell 命令。

## 安装状态机

```text
queued -> installing -> registering -> running
                   \-> failed
running -> stopped | uninstalling -> removed
```

`installing` 校验受控包与依赖，`registering` 由本地启动器启动服务并调用 ResourcePlane 登记 Runtime，`running` 要求健康检查通过。失败状态必须保存无敏感信息的错误摘要，并且不得留下可调度 Runtime。

自定义资源不执行用户提供的命令。用户只能提交经过合同校验的本地服务地址、模型/能力声明和适配器；其记录走同一安装任务状态机，在登记成功后成为本地资源。

对于模型服务，前端默认声明 `agentos_model_http`，使通过健康检查的 OpenAI Compatible 本地服务不仅进入资源目录，也能成为实际推理调用目标。该适配器以外的协议依然必须先实现对应调用 adapter，资源登记本身不会生成协议执行能力。

## 数据流

```text
CatalogItem / CustomResourceRequest
  -> InstallationJob(queued)
  -> 本地包边界、校验和、硬件与声明校验
  -> LocalLauncher.start(受控模板)
  -> ResourcePlane.register_runtime()
  -> heartbeat / health check
  -> InstallationJob(running)
  -> ResourceBinder 候选与冻结绑定
```

卸载先停止服务、撤销 Runtime 与模型端点，再移除受控安装目录；删除失败不得伪造“已移除”状态。

## API 与前端

后端提供目录列表、安装任务创建/查询、停止、卸载和自定义资源创建接口。前端使用对应 API，而不是维护本地虚假的安装状态。

资源概览使用摘要 API，资源管理使用现有资源 Plane 的 Node/Runtime/模型端点数据，商店使用 Catalog 与 InstallationJob API。安装进度以轮询或实时事件刷新；首期采用轮询，后续可接入现有事件通道。

## 错误与安全

- 拒绝包根目录外的路径、校验和不匹配、缺少硬件和非法 Runtime 声明。
- 包安装、启动、登记、健康检查任一失败时进入 `failed`，并尽力停止已启动进程及撤销登记。
- 不在 Job、日志或前端返回包内敏感配置、凭据、提示词或模型响应。
- 目录来源、包版本与 SHA-256 是审计字段；外部仓库接入将在此合同稳定后单独实现。

## 验证

- 后端：状态机、受控包路径、校验失败、登记/回滚和健康门槛测试。
- 前端：页面路由、页面切换、目录安装动作、失败/进行中/运行中状态测试。
- 集成：成功安装后 Runtime 与模型端点在 ResourcePlane 中可见，只有健康后能进入候选。
