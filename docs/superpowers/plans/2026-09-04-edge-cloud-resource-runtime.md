# Edge-Cloud Resource Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成远程资源自动执行、执行签名、原子注册、持久化健康和真实端—边—云联调，并为模型层切分保留独立边界。

**Architecture:** `ResourceService` 继续拥有资源画像、快照和凭据；运行时按资源画像动态生成 Adapter，远程 HTTP 请求使用当前资源凭据签名。注册和凭据写入进入同一 Store 事务；健康指标进入独立可替换的持久化 Store；三进程联调放在独立 demo/测试目录，不改前端。

**Tech Stack:** Python 3、FastAPI、httpx、SQLite、Redis 可选协调器、pytest、Docker Compose。

---

### Task 1: Define the signed execution contract and automatic adapter factory

**Files:**
- Modify: `agentOS/src/components/resource/auth.py`
- Modify: `agentOS/src/components/resource/service.py`
- Modify: `agentOS/src/adapters/resource_execution.py`
- Modify: `agentOS/src/runtime/workflow_runtime.py`
- Test: `agentOS/tests/adapters/test_resource_execution.py`
- Test: `agentOS/tests/runtime/test_resource_binding.py`

- [ ] **Step 1: Write failing tests** for automatic adapter construction, endpoint path normalization, signed execution headers, and immediate use of a rotated credential.
- [ ] **Step 2: Run the tests and verify they fail because the runtime only accepts manually injected adapters and the HTTP adapter sends no resource signature.
- [ ] **Step 3: Implement a credential provider and `build_resource_execution_adapter` for HTTP/HTTPS resources; normalize endpoint paths and sign the exact request body.
- [ ] **Step 4: Change runtime binding to lazily create adapters from the authoritative profile and fail explicitly when a remote resource cannot be configured; preserve manually injected test adapters.
- [ ] **Step 5: Run adapter and binding tests and commit `feat: auto-wire signed remote resource execution`.

### Task 2: Make remote registration atomic

**Files:**
- Modify: `agentOS/src/components/resource/store.py`
- Modify: `agentOS/src/components/resource/service.py`
- Modify: `agentOS/tests/components/resource/test_store_contract.py`
- Modify: `agentOS/tests/components/resource/test_resource_auth.py`

- [ ] **Step 1: Write failing tests** for one-transaction remote registration and rollback when credential persistence fails.
- [ ] **Step 2: Run the tests and verify current `register_remote` leaves a resource row when the credential step fails.
- [ ] **Step 3: Add `register_remote` to the Store protocol; implement atomic memory and SQLite versions using the existing encryption and digest boundary.
- [ ] **Step 4: Route `ResourceService.register_remote` through the atomic operation without changing the public one-time secret response.
- [ ] **Step 5: Run all resource tests and commit `fix: make remote resource registration atomic`.

### Task 3: Persist and share resource health

**Files:**
- Create: `agentOS/src/components/resource/health_store.py`
- Modify: `agentOS/src/components/resource/health.py`
- Modify: `agentOS/src/components/resource/service.py`
- Modify: `agent/app/execution/wiring.py`
- Test: `agentOS/tests/components/resource/test_health_store.py`
- Test: `agentOS/tests/components/resource/test_remote_observation.py`
- Test: `agent/tests/test_execution_runtime_application_wiring.py`

- [ ] **Step 1: Write failing tests** proving two service instances sharing SQLite health storage see the same heartbeat/reliability and that stale persisted state is not healthy after timeout.
- [ ] **Step 2: Run the tests and verify health currently lives only in `ResourceHealthMonitor` memory.
- [ ] **Step 3: Implement a versioned SQLite health store with atomic upsert/read and explicit health timestamps; keep `InMemoryHealthStore` for isolated unit tests.
- [ ] **Step 4: Inject the store through the composition root and make `ResourceHealthMonitor` persist every heartbeat/observation/forced status change.
- [ ] **Step 5: Expose current health in the resource API and commit `feat: persist shared resource health`.

### Task 4: Add real three-process terminal/edge/cloud integration

**Files:**
- Create: `tools/edge_cloud_demo/terminal_node.py`
- Create: `tools/edge_cloud_demo/edge_node.py`
- Create: `tools/edge_cloud_demo/cloud_node.py`
- Create: `tools/edge_cloud_demo/run_demo.py`
- Create: `tools/edge_cloud_demo/README.md`
- Test: `agentOS/tests/integration/test_edge_cloud_processes.py`

- [ ] **Step 1: Write a process-level test contract** requiring terminal and edge registration, signed execution, edge failure, cloud rebinding, and post-restart heartbeat recovery.
- [ ] **Step 2: Run the test and verify the process fixtures are absent.
- [ ] **Step 3: Implement minimal node HTTP services with real request verification and deterministic AgentOutput responses; use explicit ports and temporary databases.
- [ ] **Step 4: Implement the runner that starts three processes, registers resources, executes one task, terminates edge, waits for cloud rebinding, and cleans up child processes.
- [ ] **Step 5: Run the process integration test and commit `test: add real edge-cloud process integration`.

### Task 5: Define the independent model-layer partition boundary

**Files:**
- Create: `agentOS/src/contracts/model_partition.py`
- Create: `agentOS/src/components/model_partition/service.py`
- Test: `agentOS/tests/components/test_model_partition.py`
- Modify: `docs/superpowers/specs/2026-09-04-edge-cloud-resource-runtime-design.md`

- [ ] **Step 1: Write failing tests** proving a partition plan has ordered layers, tensor boundary contracts, placement per layer, and rejects gaps/overlap; an unimplemented execution request returns `MODEL_PARTITION_UNAVAILABLE`.
- [ ] **Step 2: Implement contract validation and an explicit unavailable executor; do not call `ResourceService` as a substitute for layer partitioning.
- [ ] **Step 3: Run the model partition tests and commit `feat: define model partition boundary`.

### Task 6: Final verification and documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-edge-cloud-resource-runtime-design.md`
- Modify: `README.md` if endpoint/demo inventory needs updating

- [ ] **Step 1: Run focused resource, adapter, scheduler and model partition tests.
- [ ] **Step 2: Run `agentOS/tests` and `agent/tests` separately with the project virtual environment.
- [ ] **Step 3: Run the real three-process demo and preserve its machine-readable report.
- [ ] **Step 4: Run `git diff --check`, inspect all changed paths, and ensure no frontend files are staged.
- [ ] **Step 5: Commit only backend/demo/docs changes and report any root pytest collection dependency issue separately.
