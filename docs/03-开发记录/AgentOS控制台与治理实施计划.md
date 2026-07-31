# AgentOS 控制台与治理实施计划

> **针对智能体工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实施本计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 交付一个可用的 AgentOS 控制台，能够查看 WorkflowRun 详情、审核记录、检查点、追踪和工作流指标。

**架构：** 保持 Python 作为 WorkflowRun 生命周期、审核记录、检查点和指标的truth来源。通过 `/ai/core/*` 暴露这些数据，然后让 Java 网关和 Vue 控制台消费相同的结构。前端应首先渲染一个可工作的控制台，然后在同一 API 层之上逐步增加专用面板。

**技术栈：** FastAPI、Pydantic、Python 运行时/存储类、Spring Boot WebClient 网关、Vue 3、TypeScript、Pinia 兼容的服务层、现有的应用路由/组件模式。

---

### 任务 1：扩展 Python 治理模型

**文件：**
- 修改：`agentOS/src/agentos/core/types.py`
- 修改：`agentOS/src/agentos/core/checkpoint.py`
- 修改：`agentOS/src/agentos/core/evaluation.py`
- 修改：`agent/app/api/agentos_core.py`
- 测试：`agent/tests/test_agentos_core.py`
- 测试：`agent/tests/test_sqlite_workflow_store.py`

- [ ] **步骤 1：编写会失败的测试**

```python
def test_workflow_api_exports_checkpoints_reviews_and_metrics(client):
    checkpoints = client.get("/ai/core/workflows/runs/run_001/checkpoints")
    reviews = client.get("/ai/core/workflows/runs/run_001/reviews")
    metrics = client.get("/ai/core/workflows/metrics")
    assert checkpoints.status_code == 200
    assert reviews.status_code == 200
    assert metrics.status_code == 200
```

- [ ] **步骤 2：运行测试确认其失败**

运行：`python -m pytest tests/test_agentos_core.py -q`
预期：失败，因为新端点和响应模型尚不存在。

- [ ] **步骤 3：编写最小实现**

```python
class ReviewRequest(BaseModel):
    step_id: str
    decision: ReviewDecisionType
    reviewer: str = "system"
    comment: str = ""

class ReviewLog(CoreModel):
    run_id: str = Field(alias="runId")
    step_id: str = Field(alias="stepId")
    decision: ReviewDecisionType
    reviewer: str
    comment: str = ""
```

- [ ] **步骤 4：运行测试确认其通过**

运行：`python -m pytest tests/test_agentos_core.py tests/test_sqlite_workflow_store.py -q`
预期：通过，检查点/审核/指标负载返回 JSON。

- [ ] **步骤 5：提交**

```bash
git add agentOS/src/agentos/core/types.py agentOS/src/agentos/core/checkpoint.py agentOS/src/agentos/core/evaluation.py agent/app/api/agentos_core.py agent/tests/test_agentos_core.py agent/tests/test_sqlite_workflow_store.py
git commit -m "feat: add AgentOS governance APIs"
```

### 任务 2：扩展 Python API 以支持控制台消费

**文件：**
- 修改：`agent/app/api/agentos_core.py`
- 修改：`agentOS/src/agentos/core/workflow_runtime.py`
- 修改：`agentOS/src/agentos/core/trace.py`
- 测试：`agent/tests/test_agentos_core.py`

- [ ] **步骤 1：编写会失败的测试**

```python
def test_workflow_run_detail_includes_checkpoints_and_trace_export(client):
    detail = client.get("/ai/core/workflows/runs/run_001")
    trace = client.get("/ai/core/workflows/runs/run_001/trace")
    checkpoints = client.get("/ai/core/workflows/runs/run_001/checkpoints")
    assert "trace" in detail.json()
    assert trace.json()["eventCount"] >= 1
    assert checkpoints.json()["items"]
```

- [ ] **步骤 2：运行测试确认其失败**

运行：`python -m pytest tests/test_agentos_core.py -q`
预期：失败，直到控制台负载被添加。

- [ ] **步骤 3：编写最小实现**

```python
@router.get("/core/workflows/runs/{run_id}/checkpoints")
async def list_checkpoints(run_id: str):
    run = runtime.get_status(run_id)
    return {
        "items": [checkpoint.model_dump(by_alias=True, mode="json") for checkpoint in run.checkpoints],
        "total": len(run.checkpoints),
        "runId": run_id,
    }
```

- [ ] **步骤 4：运行测试确认其通过**

运行：`python -m pytest tests/test_agentos_core.py -q`
预期：通过，详情、追踪和检查点端点对齐。

- [ ] **步骤 5：提交**

```bash
git add agent/app/api/agentos_core.py agentOS/src/agentos/core/workflow_runtime.py agentOS/src/agentos/core/trace.py agent/tests/test_agentos_core.py
git commit -m "feat: extend AgentOS console payloads"
```

### 任务 3：构建 Vue AgentOS 控制台外壳

**文件：**
- 创建：`frontend/src/views/AgentOsConsoleView.vue`
- 创建：`frontend/src/components/agentos/WorkflowRunPanel.vue`
- 创建：`frontend/src/components/agentos/WorkflowStepList.vue`
- 创建：`frontend/src/components/agentos/CheckpointPanel.vue`
- 创建：`frontend/src/components/agentos/TraceEventTimeline.vue`
- 创建：`frontend/src/components/agentos/HumanReviewPanel.vue`
- 修改：`frontend/src/router/index.ts`
- 修改：`frontend/src/services/api/agentos.ts`

- [ ] **步骤 1：编写会失败的测试**

```ts
import { mount } from '@vue/test-utils'
import AgentOsConsoleView from '@/views/AgentOsConsoleView.vue'

test('renders the AgentOS console shell', () => {
  const wrapper = mount(AgentOsConsoleView)
  expect(wrapper.text()).toContain('AgentOS')
})
```

- [ ] **步骤 2：运行测试确认其失败**

运行：`npm run test -- AgentOsConsoleView`
预期：失败，因为视图和组件尚不存在。

- [ ] **步骤 3：编写最小实现**

```vue
<template>
  <div class="agentos-console">
    <WorkflowRunPanel />
    <WorkflowStepList />
    <CheckpointPanel />
    <TraceEventTimeline />
    <HumanReviewPanel />
  </div>
</template>
```

- [ ] **步骤 4：运行测试确认其通过**

运行：`npm run build`
预期：构建成功，控制台路由可解析。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/views/AgentOsConsoleView.vue frontend/src/components/agentos frontend/src/router/index.ts frontend/src/services/api/agentos.ts
git commit -m "feat: add AgentOS console shell"
```

### 任务 4：添加检查点和审核交互连线

**文件：**
- 修改：`frontend/src/components/agentos/HumanReviewPanel.vue`
- 修改：`frontend/src/components/agentos/CheckpointPanel.vue`
- 修改：`frontend/src/components/agentos/WorkflowRunPanel.vue`
- 修改：`frontend/src/services/api/agentos.ts`

- [ ] **步骤 1：编写会失败的测试**

```ts
test('review panel submits a decision and refreshes the run', async () => {
  // 挂载面板，桩审核 API，断言提交处理函数调用刷新
})
```

- [ ] **步骤 2：运行测试确认其失败**

运行：`npm run test`
预期：失败，直到面板和刷新契约被实现。

- [ ] **步骤 3：编写最小实现**

```ts
await agentosApi.applyWorkflowReview(runId, {
  stepId,
  decision,
  reviewer,
  comment
})
```

- [ ] **步骤 4：运行测试确认其通过**

运行：`npm run build`
预期：编译通过，审核操作已连线。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/components/agentos/HumanReviewPanel.vue frontend/src/components/agentos/CheckpointPanel.vue frontend/src/components/agentos/WorkflowRunPanel.vue frontend/src/services/api/agentos.ts
git commit -m "feat: wire AgentOS review and checkpoint actions"
```

### 任务 5：将评估转为一等控制台指标

**文件：**
- 修改：`agentOS/src/agentos/core/evaluation.py`
- 修改：`agent/app/api/agentos_core.py`
- 修改：`frontend/src/services/api/agentos.ts`
- 修改：`frontend/src/views/AgentOsConsoleView.vue`

- [ ] **步骤 1：编写会失败的测试**

```python
def test_workflow_metrics_include_failure_and_recovery_rates(client):
    metrics = client.get("/ai/core/workflows/metrics")
    payload = metrics.json()
    assert "failureRate" in payload
    assert "recoverySuccessRate" in payload
```

- [ ] **步骤 2：运行测试确认其失败**

运行：`python -m pytest tests/test_agentos_core.py -q`
预期：失败，直到指标端点和负载被实现。

- [ ] **步骤 3：编写最小实现**

```python
class WorkflowMetric(BaseModel):
    total_runs: int = Field(alias="totalRuns")
    completion_rate: float = Field(alias="completionRate")
    failure_rate: float = Field(alias="failureRate")
    recovery_success_rate: float = Field(alias="recoverySuccessRate")
```

- [ ] **步骤 4：运行测试确认其通过**

运行：`python -m pytest tests/test_agentos_core.py -q`
预期：通过，返回工作流运行的指标汇总。

- [ ] **步骤 5：提交**

```bash
git add agentOS/src/agentos/core/evaluation.py agent/app/api/agentos_core.py frontend/src/services/api/agentos.ts frontend/src/views/AgentOsConsoleView.vue
git commit -m "feat: add AgentOS governance metrics"
```

### 任务 6：同步文档并验证全栈

**文件：**
- 修改：`docs/02-项目开发日志/core-todo.md`
- 修改：`README.md`
- 修改：`agent/README.md`
- 修改：`docs/README.md`

- [ ] **步骤 1：编写会失败的检查**

```bash
rg -n "checkpoints|reviews|metrics|AgentOsConsoleView" docs README.md agent/README.md
```

- [ ] **步骤 2：运行检查**

运行：`rg -n "checkpoints|reviews|metrics|AgentOsConsoleView" docs README.md agent/README.md`
预期：每个公共 API 和控制台界面都出现在文档中。

- [ ] **步骤 3：编写最小文档更新**

```md
- `GET /ai/core/workflows/runs/{runId}/checkpoints`：查询恢复点列表。
- `GET /ai/core/workflows/metrics`：查询工作流治理指标。
- `POST /ai/core/workflows/runs/{runId}/reviews`：提交人工审核结果。
```

- [ ] **步骤 4：运行完整验证**

运行：`python -m pytest tests/test_agentos_core.py tests/test_sqlite_workflow_store.py -q`
运行：`mvn clean compile`
运行：`git diff --check`

- [ ] **步骤 5：提交**

```bash
git add docs/02-项目开发日志/core-todo.md README.md agent/README.md docs/README.md
git commit -m "docs: sync AgentOS console and governance work"
```
