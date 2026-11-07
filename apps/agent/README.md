# 知弈 Python Agent

`agent/` 是 Python FastAPI 应用层，负责暴露 AI 服务入口、加载通用 Pack、承载 LLM Gateway、Evidence Retriever 和 AgentOS Core API。AgentOS Core 的源码位于 `apps/agentOS/src/`。

## 当前职责

- FastAPI 应用入口：`app/main.py`
- AgentOS Core API：`app/api/agentos_v2.py`
- 通用 Workspace Pack：`packs/workspace/`
- LLM Gateway：`app/llm/`
- Code index builder：`app/rag/code_index_builder.py`

AgentOS Core 提供任务、运行记录、Trace、Review、Checkpoint 与通用执行协议；通用任务由 Core Native ACG 执行。

## 启动

在 `apps/agent/` 目录运行：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

健康检查：

```bash
curl http://localhost:8000/health
```

## 测试

在 `apps/agent/` 目录运行：

```bash
python -m pytest tests
```

## 主要 API

通过本地 TypeScript Gateway 访问时，前端主要使用 `/ai/core/**`。Python Agent 直接暴露同名 AgentOS Core API：

```text
POST /ai/core/tasks
GET  /ai/core/tasks
POST /ai/core/workflows/runs
POST /ai/core/workflows/start
GET  /ai/core/workflows/runs
GET  /ai/core/workflows/metrics
GET  /ai/core/workflows/runs/{runId}
GET  /ai/core/workflows/runs/{runId}/checkpoints
GET  /ai/core/workflows/runs/{runId}/trace
GET  /ai/core/workflows/runs/{runId}/reviews
POST /ai/core/workflows/runs/{runId}/reviews
POST /ai/core/workflows/runs/{runId}/resume
POST /ai/core/workflows/runs/{runId}/cancel
```

## 能力边界

- 不再内置律师、教师、程序员、作家、工业职业 Pack；这些目录已从当前树删除（git 历史仍可追溯）。
- 当前保留的唯一应用 Pack 是 `workspace`：在受审计的 Hands 资源中修改文件并运行真实测试。
- 通用任务通过 `native_acg_runtime_v1` 执行，不依赖职业专用 workflow。

## V1.0.6 代码边界

- AgentOS Core 不直接 import 应用层业务模块。
- ACG 通过就绪集调度执行 Pack agents，并保留 Trace、Review、Checkpoint、数据血缘和自愈。
- Core 侧 `model_adapter.py` 只保留模型协议和注册入口，具体 `app.services.aiservice.AIService` 由 `app/integrations/model_adapter.py` 注册。
