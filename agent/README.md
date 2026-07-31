# 知弈 Python Agent

`agent/` 是 Python FastAPI 应用层，负责暴露 AI 服务入口、加载行业 Pack、承载 LLM Gateway、Evidence Retriever 和 AgentOS Core API。AgentOS Core 的源码位于仓库根目录的 `agentOS/src/agentos/`。

## 当前职责

- FastAPI 应用入口：`agent/app/main.py`
- AgentOS Core API：`agent/app/api/agentos_core.py`
- Legal Pack：`agent/packs/legal/`
- 合同审查 workflow definition：`agent/packs/legal/workflows/contract_review.yaml`
- ACG 合同审查实现：`agent/packs/legal/agents/contract_review_migration.py`
- LLM Gateway：`agent/app/llm/`
- keyword Evidence Retriever：`agent/app/rag/providers/keyword_retriever.py`

AgentOS Core 提供任务、运行记录、Trace、Review、Checkpoint 与通用执行协议；合同审查由 Core Native ACG 执行。

## 当前 Workflow

```text
id: legal_contract_review_v1
runtimeEngine: acg
```

artifacts 契约：

```text
risks: output.artifacts.risk_detect.risks
evidences: output.artifacts.legal_evidence_match.evidences
report: output.artifacts.report_generate.report_markdown
```

## 启动

在 `agent/` 目录运行：

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

健康检查：

```bash
curl http://localhost:8000/health
```

## 测试

在 `agent/` 目录运行：

```bash
python -m pytest tests
```

## 主要 API

通过 Spring Boot Gateway 访问时，前端主要使用 `/ai/core/**`。Python Agent 直接暴露同名 AgentOS Core API：

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

不恢复旧 V0.7 合同审查专用 API。律师合同审查工作台也走统一的 AgentOS Core workflow API。

## 能力边界

当前 Evidence 是演示级本地知识库 + keyword 检索，不是完整法律法规库、案例库或正式法律 RAG。当前报告不是正式法律意见，需要律师复核。

## V1.0.6 代码边界

- AgentOS Core 不直接 import 应用层业务模块。
- ACG 通过就绪集调度执行 Pack agents，并保留 Trace、Review、Checkpoint、数据血缘和自愈。
- 合同审查业务逻辑位于 `agent/packs/legal/agents/contract_review_migration.py`，artifact 路径由标准 workflow 契约定义。
- Core 侧 `model_adapter.py` 只保留模型协议和注册入口，具体 `app.services.aiservice.AIService` 由 `agent/app/integrations/model_adapter.py` 注册。
