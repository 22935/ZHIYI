# Resource Credential Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为远程端/边/云资源增加显式、可审计且原子性的凭据轮换能力，并让旧凭据立即失效。

**Architecture:** 轮换沿用现有 `ResourceService` 和资源真源数据库。存储层增加原子 `rotate_credential` 操作，内存实现用锁保护，SQLite 实现用事务保护；服务层只负责校验资源、生成新凭据和构造一次性响应。HTTP 层复用已有 operator/admin/system 与 owner scope 检查，不触碰资源画像、快照和调度逻辑。

**Tech Stack:** Python 3、FastAPI、Pydantic、SQLite、pytest、现有 AgentOS ResourceService。

---

### Task 1: Lock down credential rotation behavior with service and store tests

**Files:**
- Modify: `agentOS/tests/components/resource/test_resource_auth.py`
- Modify: `agentOS/tests/components/resource/test_store_contract.py`

- [x] **Step 1: Write the failing tests**

  Add tests asserting that both `InMemoryResourceStore` and `SQLiteResourceStore` can atomically replace a resource credential, that the returned record has a different credential ID and encrypted secret, and that the resource profile and snapshot version remain unchanged. Add a service test asserting `rotate_credential("edge-auth")` returns a new one-time secret while the previous credential no longer verifies.

- [x] **Step 2: Run the focused tests and verify the expected failure**

  Run `E:\Project\Kinlin_AI\agent\.venv\Scripts\python.exe -m pytest -q agentOS/tests/components/resource/test_resource_auth.py agentOS/tests/components/resource/test_store_contract.py`.

  Expected result: the new tests fail because `rotate_credential` is not yet part of the store/service API; existing tests should remain green.

### Task 2: Implement atomic credential replacement in both stores

**Files:**
- Modify: `agentOS/src/components/resource/store.py`

- [x] **Step 1: Add the `rotate_credential` protocol method**

  Define `rotate_credential(record: ResourceCredentialRecord) -> None` with the contract that an unknown resource or missing current credential raises explicitly and no partial replacement is allowed.

- [x] **Step 2: Implement the in-memory replacement**

  Under the existing `RLock`, verify the resource exists and has a current credential, then replace the record. Do not modify `_profiles` or `_snapshots`.

- [x] **Step 3: Implement the SQLite transaction**

  Under the existing lock, run `BEGIN IMMEDIATE`, verify the resource credential exists, update all credential columns by `resource_id`, require exactly one affected row, commit on success, and rollback/re-raise on every error. Preserve the existing credential row if update fails.

- [x] **Step 4: Run the focused store tests**

  Run `E:\Project\Kinlin_AI\agent\.venv\Scripts\python.exe -m pytest -q agentOS/tests/components/resource/test_store_contract.py`.

  Expected result: all store contract tests pass.

### Task 3: Add service-level credential rotation

**Files:**
- Modify: `agentOS/src/components/resource/service.py`
- Modify: `agentOS/tests/components/resource/test_resource_auth.py`

- [x] **Step 1: Implement the minimal service method**

  Add `ResourceService.rotate_credential(resource_id)` using the same remote-resource validation as `issue_credential`, generate a fresh URL-safe secret and credential ID, persist its encrypted secret plus independent digest through `store.rotate_credential`, and return `IssuedResourceCredential`. The method must not call resource registration or update snapshots.

- [x] **Step 2: Verify service behavior and old-secret invalidation**

  Run `E:\Project\Kinlin_AI\agent\.venv\Scripts\python.exe -m pytest -q agentOS/tests/components/resource/test_resource_auth.py`.

  Expected result: the new rotation tests and all existing authentication tests pass.

### Task 4: Expose the protected HTTP rotation endpoint

**Files:**
- Modify: `agent/app/api/agentos_v2.py`
- Modify: `agent/tests/test_agentos_v2_api.py`

- [x] **Step 1: Write failing API tests**

  Add tests for unauthenticated 401, non-operator 403, cross-tenant 403, successful rotation, old credential rejected by observation, new credential accepted by observation, repeated rotation producing a new credential, and unchanged profile/snapshot projection.

- [x] **Step 2: Run the API tests and verify failure**

  Run `E:\Project\Kinlin_AI\agent\.venv\Scripts\python.exe -m pytest -q agent/tests/test_agentos_v2_api.py -k credential_rotation`.

  Expected result: the new endpoint test fails with 404 because the route is absent.

- [x] **Step 3: Implement the route**

  Add `POST /resources/{resource_id}/credential/rotate`; load the resource profile first and return 404 for unknown resources, apply `require_resource_operator(profile.owner_scope)`, call `resource_service.rotate_credential`, map storage/service errors to explicit 404/409 responses, and return the same credential response shape as registration with `signatureAlgorithm` set to the existing HMAC contract.

- [x] **Step 4: Run the API tests**

  Run `E:\Project\Kinlin_AI\agent\.venv\Scripts\python.exe -m pytest -q agent/tests/test_agentos_v2_api.py -k credential_rotation`.

  Expected result: all rotation API tests pass.

### Task 5: Correct documentation and run the full verification suite

**Files:**
- Modify: `docs/superpowers/specs/2026-09-02-agentos-remote-resource-auth-design.md`
- Modify: `README.md` if the endpoint inventory needs updating

- [x] **Step 1: Check documentation consistency**

  Ensure all references say the server stores encrypted secret plus independent digest, rotation is explicit, and model-layer splitting remains out of scope.

- [x] **Step 2: Run focused and full suites**

  Run `E:\Project\Kinlin_AI\agent\.venv\Scripts\python.exe -m pytest -q agentOS/tests/components/resource agent/tests/test_agentos_v2_api.py`.

  Then run the same interpreter separately against `agentOS/tests` and `agent/tests`. A root-level collection run is currently not a valid gate because two existing tests share the basename `test_model_runtime.py`, and `tools/tui/tests/test_app.py` requires the separately managed `textual` dependency.

  Expected result: both scoped suites pass with only the repository's existing deprecation warnings.

- [x] **Step 3: Inspect the final diff and commit only backend changes**

  Run `git diff --check`, `git status --short`, and `git diff --stat`; leave the pre-existing untracked test `data/` directory untouched unless it is confirmed to be reproducible test output. Commit the source, tests, plan, and documentation with `feat: add remote resource credential rotation`.
