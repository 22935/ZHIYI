# AgentOS Edge-Cloud Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent stale remote observations and stale scheduler decisions from changing the authoritative edge-cloud execution state.

**Architecture:** Keep `ResourceService`, `ResourceStore`, and `SchedulerService` as the existing Modules. Add a monotonic observation sequence to the resource Interface and reject older remote observations at the Store seam. Add a post-lease snapshot-version check in the scheduler so a binding is returned only when the selected resource is still based on the observed version.

**Tech Stack:** Python 3, Pydantic, pytest, FastAPI/HTTPX, SQLite.

---

### Task 1: Reject stale remote observations

**Files:**
- Modify: `agentOS/src/contracts/resource.py`
- Modify: `agentOS/src/components/resource/store.py`
- Modify: `agentOS/src/components/resource/service.py`
- Modify: `agent/app/api/agentos_v2.py`
- Test: `agentOS/tests/components/resource/test_remote_observation.py`
- Test: `agent/tests/test_agentos_v2_api.py`

- [x] Add a test showing observation sequence 2 is accepted and a later request carrying sequence 1 is rejected without changing the snapshot.
- [x] Run the focused resource test and confirm it fails because snapshots do not carry an observation sequence.
- [x] Add `observationSequence` as a non-negative integer to `ResourceSnapshot` and the remote observation request.
- [x] Add an explicit `StaleResourceObservation` error and enforce the sequence check in both in-memory and SQLite stores.
- [x] Make `ResourceService.observe_remote` pass the sequence through and return a conflict response from the API.
- [x] Run the focused resource and API tests.
- [x] Commit with `feat: reject stale edge resource observations`.

### Task 2: Guard scheduler bindings against snapshot races

**Files:**
- Modify: `agentOS/src/components/scheduler/service.py`
- Test: `agentOS/tests/components/scheduler/test_edge_cloud_placement.py`
- Test: `agentOS/tests/runtime/test_resource_binding.py`

- [x] Add a test where a candidate snapshot changes between candidate evaluation and lease acquisition; the scheduler must release the lease and not return a binding based on the old version.
- [x] Run the focused scheduler test and confirm it fails because the current scheduler does not re-check the version after acquiring a lease.
- [x] Re-read the current snapshot after lease acquisition, release the lease on version mismatch, and continue to the next candidate.
- [x] Include the confirmed snapshot version in the binding metadata and preserve the existing stable tie-break behavior.
- [x] Run all scheduler and resource-binding tests.
- [x] Commit with `fix: guard bindings against stale resource snapshots`.

### Task 3: Verification and documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-01-agentos-edge-cloud-adaptation-design.md`
- Modify: `README.md`

- [x] Document observation ordering and post-lease snapshot validation as consistency guarantees.
- [x] Run the complete AgentOS and backend test suites.
- [x] Inspect the branch diff and confirm no frontend files or compose files are included.
- [x] Record exact test counts and any remaining production-topology limitations.
