# AgentOS 端边云适配第一阶段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将本地 Agent 资源调度扩展为可表达 terminal/edge/cloud、可远程观测、可通过执行 Adapter 调用并支持基础故障切换的端边云运行链路。

**Architecture:** 保留现有 `ResourceService`、`SchedulerService`、租约和 `WorkflowRuntime`，在共享合同中增加部署层级、端点和算力约束。调度器只负责选择并冻结执行目标，新增 `ExecutionAdapter` 接缝负责本地或 HTTP 调用；远程心跳由资源节点主动上报。

**Tech Stack:** Python 3、Pydantic、pytest、FastAPI/HTTPX（沿用现有 AgentOS 测试栈）、SQLite、Redis 租约协调。

---

### Task 1: Extend resource contracts

**Files:**
- Modify: `agentOS/src/contracts/resource.py`
- Test: `agentOS/tests/components/resource/test_edge_cloud_contracts.py`

- [ ] Write tests for deployment tier validation, endpoint fields, compute constraints, and placement requirements.
- [ ] Run the focused test and confirm it fails because the new fields and enum do not exist.
- [ ] Add `DeploymentTier`, endpoint and compute fields with strict validation and aliases.
- [ ] Extend `BindingRequirement` with allowed tiers, maximum latency, privacy level, remote-execution permission, and model requirements.
- [ ] Run the focused contract test and the existing resource/scheduler tests.

### Task 2: Add remote observation and authoritative heartbeat handling

**Files:**
- Modify: `agentOS/src/components/resource/health.py`
- Modify: `agentOS/src/components/resource/service.py`
- Modify: `agentOS/src/components/resource/store.py`
- Test: `agentOS/tests/components/resource/test_remote_observation.py`

- [ ] Write tests proving a remote heartbeat updates health, stale heartbeat makes a resource ineligible, and runtime-local heartbeat cannot revive a remote resource.
- [ ] Run the tests and confirm the stale-heartbeat and observation cases fail.
- [ ] Add a versioned observation method and persist the latest observation needed for restart-safe eligibility.
- [ ] Separate local-agent keepalive from externally reported heartbeat; remove automatic keepalive for non-local resources.
- [ ] Run resource and scheduler tests.

### Task 3: Deepen scheduling placement policy

**Files:**
- Create: `agentOS/src/components/scheduler/placement.py`
- Modify: `agentOS/src/components/scheduler/service.py`
- Modify: `agentOS/src/components/scheduler/models.py`
- Test: `agentOS/tests/components/scheduler/test_edge_cloud_placement.py`

- [ ] Write tests for hard filtering by tier, latency, privacy/data zone, model, and GPU memory, plus explainable score factors.
- [ ] Run the placement tests and confirm they fail before the placement policy exists.
- [ ] Implement a focused `PlacementPolicy` that returns eligible candidates and structured reasons without mutating resource state.
- [ ] Make `SchedulerService.schedule_ready` use the policy and persist the selected tier and score explanation in the binding metadata.
- [ ] Run all scheduler tests and verify stable tie-breaking remains unchanged.

### Task 4: Create local and HTTP execution adapters

**Files:**
- Create: `agentOS/src/components/executor/adapters.py`
- Modify: `agentOS/src/components/executor/node_runner.py`
- Modify: `agentOS/src/runtime/workflow_runtime.py`
- Test: `agentOS/tests/components/executor/test_execution_adapters.py`

- [ ] Write tests for local adapter compatibility and HTTP adapter success, timeout, malformed response, and idempotency key propagation.
- [ ] Run the adapter tests and confirm they fail because the adapter seam is absent.
- [ ] Define the minimal adapter interface and implement local and HTTP adapters without storing credentials in resource profiles.
- [ ] Route a scheduled binding to the matching adapter instead of always resolving a local Agent.
- [ ] Run executor and runtime tests.

### Task 5: Add remote resource API and failure-switch integration test

**Files:**
- Modify: `agent/app/api/agentos_v2.py`
- Modify: `agent/app/execution/wiring.py`
- Modify: `agentOS/src/runtime/workflow_runtime.py`
- Test: `agent/tests/test_agentos_v2_resource_observation.py`
- Test: `agent/tests/test_edge_cloud_failover.py`

- [ ] Write API tests for resource registration/heartbeat/observation and an integration test for edge failure followed by cloud rebind from a checkpoint.
- [ ] Run the tests and confirm the new endpoints and failover path fail.
- [ ] Add authenticated resource observation handling with strict resource ownership and sequence/version checks.
- [ ] Wire the adapter registry into the runtime and implement bounded rebind on remote timeout or stale health.
- [ ] Run the focused API and runtime integration tests.

### Task 6: Add runtime projection and evidence

**Files:**
- Modify: `agent/app/api/agentos_v2.py`
- Modify: `frontend/src/services/api/agentos.ts`
- Modify: `frontend/src/workbench/runtime/resourceObservation.ts`
- Modify: `frontend/src/workbench/contributions/resource/RunResourceInspector.vue`
- Test: existing frontend resource projection tests

- [ ] Write or extend tests for deployment tier, endpoint-safe display, placement reasons, and resource switch timeline.
- [ ] Run the frontend tests and confirm the new projection assertions fail.
- [ ] Expose only non-secret resource metadata and display terminal/edge/cloud, binding reason, and switch events.
- [ ] Run frontend unit tests and build.

### Task 7: Verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/04-演示与交付/ACG认知规划引擎（Cognitive Planning Engine）与 ACG 就绪集并行执行器（ACG Executor）技术报告.md`

- [ ] Run focused Python tests, full AgentOS tests, backend tests, frontend tests, and frontend build using the project-recommended environments.
- [ ] Inspect git diff and confirm the existing compose/image changes remain untouched.
- [ ] Update documentation to say model placement is implemented while model-layer splitting remains future work.
- [ ] Add a reproducible terminal-edge-cloud demo command and expected evidence fields.
