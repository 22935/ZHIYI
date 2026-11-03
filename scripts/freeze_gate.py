#!/usr/bin/env python3
"""Run the AgentOS five-minute stage-freeze gate.

The gate compares the current src/tests tree with a source snapshot, maps
changed modules to focused contract tests, and never turns a timeout into a
pass. It intentionally does not enable pytest-xdist.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import tempfile
import uuid
from contextlib import contextmanager


ROOT = Path(__file__).resolve().parents[1]
AGENTOS = ROOT / "apps" / "agentOS"
# Exact src/tests manifest at INT-1 entry Commit 09860f8c (C2A-3 frozen).
DEFAULT_BASELINE = ROOT / "scripts" / "freeze_gate_baselines" / "c2b-int1-entry.json"
BASELINE_SHA256 = "54ccc02a3d0ba550fffff8dd23f259460977ae0a75f3d8eea4d7c1848ce1a591"
BASELINE_AGGREGATE = "cb5809b8a2e29278d39d6ab70c6bd1567da7073148195201d013f1105f9a2c47"
BASELINE_COMMIT = "09860f8c88c4b8d40cac2c80ca836f0bfa5a2c35"
DEFAULT_BUDGET_SECONDS = 300
SLOW_EXCLUSION = "not slow_benchmark and not slow_multiprocess and not slow_fault_injection"
FAST_OR_CRITICAL = (
    "freeze_gate or (not slow_benchmark and not slow_multiprocess "
    "and not slow_fault_injection)"
)

# Each changed source area must have a focused test module. Freeze-critical
# counterexamples in those modules carry @pytest.mark.freeze_gate. New rules
# should be added alongside the implementation that introduces the module.
SOURCE_TEST_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("apps/agent/packs/programmer/workflows/requirement_analysis.yaml", ("../agent/tests/test_execution_runtime_domain_packs.py",)),
    ("apps/agent/packs/legal/workflows/contract_review.yaml", ("../agent/tests/test_legal_execution_runtime_vertical_slice.py",)),
    ("apps/agent/packs/legal/planning/contract_review_blueprint.py", ("../agent/tests/test_legal_execution_runtime_vertical_slice.py",)),
    # PR-UI-04.2: retain the original INT-1 manifest; cover the real managed
    # cancellation chain and previously unmapped adapter/store deltas.
    ("src/support/async_tasks.py", ("../agent/tests/test_execution_adapter_settlement.py", "../agent/tests/test_managed_execution_settlement.py")),
    ("src/runtime/acg_execution.py", ("../agent/tests/test_managed_execution_settlement.py",)),
    ("src/runtime/workflow_runtime.py", ("../agent/tests/test_managed_execution_settlement.py",)),
    ("src/components/executor/graph.py", ("../agent/tests/test_execution_adapter_settlement.py",)),
    ("src/components/scheduler/binder.py", ("../agent/tests/test_managed_execution_settlement.py",)),
    ("src/adapters/audited_tool_runtime.py", ("tests/adapters/test_audited_tool_runtime.py", "tests/adapters/test_hands_integration.py")),
    ("src/adapters/guarded_tool.py", ("tests/adapters/test_guarded_runtime.py", "tests/adapters/test_hands_integration.py")),
    ("src/adapters/hands_http.py", ("tests/adapters/test_hands_integration.py", "../agent/tests/test_execution_adapter_settlement.py")),
    ("src/adapters/http_transport.py", ("tests/adapters/test_http_transport.py", "../agent/tests/test_execution_adapter_settlement.py")),
    ("src/adapters/model/native.py", ("tests/adapters/test_native_agent.py", "tests/adapters/test_model_audit_metadata.py", "../agent/tests/test_runtime_streaming_production_e2e.py")),
    ("src/adapters/openai_runtime.py", ("tests/adapters/test_model_runtime.py", "tests/adapters/test_model_runtime_streaming.py")),
    ("src/adapters/resource_execution.py", ("tests/adapters/test_resource_execution.py", "../agent/tests/test_execution_adapter_settlement.py")),
    ("src/components/memory/service.py", ("tests/components/memory/test_execution_memory.py", "tests/components/memory/test_hybrid_capsule.py", "tests/test_acg_execution_graph.py")),
    ("src/components/mission_manager/service.py", ("tests/support/test_branch_safe_mission_projection.py", "tests/runtime/test_mission_semantic_convergence.py")),
    ("src/support/acg/capabilities.py", ("tests/adapters/test_native_agent.py", "tests/components/executor/test_advanced_acg_capabilities.py")),
    ("src/support/stores/_policy.py", ("tests/support/test_workflow_store_contract.py", "tests/support/test_branch_safe_mission_projection.py")),
    ("src/support/stores/memory_workflow_store.py", ("tests/support/test_workflow_store_contract.py", "tests/support/test_execution_settlement_persistence.py", "tests/support/test_branch_safe_mission_projection.py")),
    ("src/support/stores/sqlite_workflow_store.py", ("tests/support/test_workflow_store_contract.py", "tests/support/test_execution_settlement_persistence.py", "tests/support/test_branch_safe_mission_projection.py")),
    ("src/support/stores/workflow_store.py", ("tests/support/test_workflow_store_contract.py", "tests/support/test_execution_settlement_persistence.py")),
    ("apps/agent/app/execution/coordinator.py", ("../agent/tests/test_execution_coordinator.py", "../agent/tests/test_managed_execution_settlement.py")),
    ("apps/agent/app/execution/model_runtime.py", ("../agent/tests/test_acg_model_runtime.py", "../agent/tests/test_execution_adapter_settlement.py")),
    ("apps/agent/app/tools/formal_workspace.py", ("tests/adapters/test_hands_integration.py", "../agent/tests/test_execution_adapter_settlement.py")),
    ("src/runtime/human_review_policy.py", ("tests/components/planner/test_human_review_policy.py",)),
    ("src/runtime/v2/queries.py", ("tests/runtime/v2/test_artifact_identity.py", "tests/runtime/v2/test_workspace_projection.py")),
    ("src/runtime/v2/workspace.py", ("tests/runtime/v2/test_artifact_identity.py", "tests/runtime/v2/test_workspace_projection.py")),
    ("scripts/freeze_gate.py", ("tests/storage/test_freeze_gate_integrity.py",)),
    ("scripts/freeze_gate_pytest_runner.py", ("tests/storage/test_freeze_gate_integrity.py",)),
    ("src/support/stores/c2_schema_upgrade.py", ("tests/storage/test_c2_schema_upgrade.py", "tests/storage/test_c2_schema_integrity.py", "tests/storage/v2/test_schema.py")),
    ("scripts/upgrade_agentos_c2_schema.py", ("tests/storage/test_c2_schema_upgrade.py",)),
    ("src/components/resource/__init__.py", ("tests/components/resource/test_node_store.py", "tests/components/resource/test_resource_auth.py")),
    ("src/components/resource/errors.py", ("tests/components/resource/test_remote_observation.py", "tests/components/resource/test_node_store.py")),
    ("src/components/resource/health_store.py", ("tests/components/resource/test_health_store.py",)),
    ("src/components/resource/node_health.py", ("tests/components/resource/test_node_store.py",)),
    ("src/components/resource/node_store.py", ("tests/components/resource/test_node_store.py",)),
    ("src/components/resource/service.py", ("tests/components/resource/test_remote_observation.py", "tests/components/resource/test_resource_auth.py", "tests/components/resource/test_node_store.py")),
    ("src/components/resource/sqlite_support.py", ("tests/components/resource/test_store_contract.py", "tests/components/resource/test_health_store.py", "tests/components/resource/test_node_store.py")),
    ("src/components/resource/store.py", ("tests/components/resource/test_store_contract.py", "tests/components/resource/test_remote_observation.py", "tests/components/resource/test_resource_auth.py")),
    ("src/contracts/resource.py", ("tests/components/resource/test_edge_cloud_contracts.py", "tests/components/scheduler/test_binder.py")),
    ("src/components/scheduler/binder.py", ("tests/components/scheduler/test_binder.py",)),
    ("src/components/scheduler/leases.py", ("tests/components/scheduler/test_redis_leases.py",)),
    ("src/components/scheduler/models.py", ("tests/components/scheduler/test_binder.py",)),
    ("src/runtime/initial_execution.py", ("tests/components/planner/test_initial_execution_permit.py",
        "tests/architecture/test_capability_upgrade_gates.py")),
    ("src/runtime/graph_handoff.py", ("tests/components/planner/test_initial_execution_permit.py",
        "tests/components/planner/test_graph_handoff.py::test_real_prefix_handoff_preserves_all_existing_facts",
        "tests/components/planner/test_graph_handoff.py::test_restart_reconstructs_same_preparation_but_cannot_execute")),
    ("src/runtime/execution_permit.py", ("tests/components/planner/test_initial_execution_permit.py",
        "tests/components/planner/test_execution_permit_audit.py")),
    ("src/contracts/graph_handoff.py", ("tests/components/planner/test_initial_execution_permit.py",)),
    ("src/contracts/execution_permit.py", ("tests/components/planner/test_initial_execution_permit.py",)),
    ("src/runtime/initial_graph_compilation.py", ("tests/components/planner/test_initial_graph_materialization.py",
        "tests/contracts/test_compiled_acg.py", "tests/contracts/test_binding_authority.py",
        "tests/architecture/test_capability_upgrade_gates.py")),
    ("src/runtime/graph_materialization.py", ("tests/components/planner/test_initial_graph_materialization.py",
        "tests/components/planner/test_graph_revision_commit.py::test_completed_prefix_pending_suffix_replacement",
        "tests/components/planner/test_graph_revision_commit.py::test_checkpoint_identity_and_control_evidence_are_required",
        "tests/components/planner/test_graph_materialization.py::test_inactive_package_is_complete_read_only_and_restartable",
        "tests/components/planner/test_graph_materialization.py::test_compile_window_changes_cannot_publish",
        "tests/components/planner/test_graph_materialization.py::test_atomic_faults_reconcile_original_key")),
    ("src/contracts/graph_materialization.py", ("tests/components/planner/test_initial_graph_materialization.py",
        "tests/components/planner/test_graph_materialization.py::test_corrupted_content_is_rejected")),
    ("src/runtime/graph_activation.py", ("tests/components/planner/test_initial_graph_materialization.py",
        "tests/components/planner/test_graph_activation.py::test_commit_switches_head_and_projection_atomically",
        "tests/components/planner/test_graph_activation.py::test_stale_sources_are_rejected_before_and_after_preparation",
        "tests/components/planner/test_graph_activation.py::test_activation_transaction_failure_rolls_back_completely",
        "tests/components/planner/test_graph_activation.py::test_scheduler_entries_refuse_the_paused_graph")),
    ("src/support/stores/graph_activation_store.py", (
        "tests/components/planner/test_initial_execution_permit.py",
        "tests/components/planner/test_initial_graph_materialization.py::test_initial_v1_paused_and_real_claim_denied",
        "tests/components/planner/test_initial_graph_materialization.py::test_real_process_exit_recovers_same_initial_fact",
        "tests/components/planner/test_initial_graph_materialization.py::test_initial_concurrent_activation_cannot_replace_head",
        "tests/components/planner/test_graph_activation.py::test_old_thread_snapshot_cannot_regress_the_graph_version")),
    ("src/contracts/graph_activation.py", ("tests/components/planner/test_initial_graph_materialization.py",)),
    ("src/runtime/workflow_runtime.py", ("tests/runtime/test_kernel_vertical_slice.py",)),
    ("src/runtime/workflow_runtime.py", ("tests/runtime/test_dispatch_admission.py",)),
    ("src/support/stores/execution_dispatch_store.py", ("tests/runtime/test_dispatch_admission.py",)),
    ("src/contracts/initial_planning.py", ("tests/components/planner/test_initial_planning_sources.py", "tests/components/planner/test_planning_commit_runtime.py")),
    ("src/contracts/planning_commit.py", ("tests/components/planner/test_initial_planning_sources.py", "tests/components/planner/test_planning_commit.py", "tests/components/planner/test_planning_commit_runtime.py")),
    ("src/components/planner/planning_commit.py", ("tests/components/planner/test_initial_planning_sources.py", "tests/components/planner/test_planning_commit.py", "tests/components/planner/test_planning_commit_runtime.py")),
    ("src/runtime/planning_commit.py", ("tests/components/planner/test_initial_planning_sources.py", "tests/components/planner/test_planning_commit_runtime.py", "tests/components/planner/test_graph_revision_commit.py")),
    ("src/runtime/initial_planning_sources.py", ("tests/components/planner/test_initial_planning_sources.py", "tests/components/planner/test_planning_commit_runtime.py")),
    ("apps/agent/app/api/agentos_v2.py", ("tests/runtime/test_kernel_vertical_slice.py", "tests/runtime/test_contract_review_delivery.py")),
    ("apps/agent/app/execution/wiring.py", ("tests/components/planner/test_production_authority_assembly.py",
        "tests/storage/test_runtime_assembly_failure_cleanup.py", "tests/storage/test_c2_schema_upgrade.py")),
    ("apps/agent/app/main.py", ("tests/storage/test_runtime_assembly_failure_cleanup.py",
        "tests/runtime/test_app_lifespan.py")),
    ("apps/agent/app/lifespan.py", ("tests/runtime/test_app_lifespan.py",)),
    ("apps/agent/app/execution/instance_lock.py", ("tests/storage/test_runtime_assembly_failure_cleanup.py",)),
    ("src/examples/", ("tests/runtime/test_kernel_vertical_slice.py", "tests/runtime/test_contract_review_delivery.py", "tests/runtime/v2/test_workspace_projection.py")),
    ("src/runtime/planning_loop.py", ("tests/runtime/test_kernel_vertical_slice.py",)),
    ("src/adapters/agent_invocation.py", ("tests/components/planner/test_permit_recovery.py",)),
    ("src/runtime/permit_recovery.py", ("tests/components/planner/test_permit_recovery.py",)),
    ("src/runtime/graph_handoff.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/graph_activation.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/binding.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/contracts/acg_lifecycle.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/ports.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/support/stores/graph_handoff_store.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/support/stores/graph_activation_store.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/workflow_runtime.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/acg_execution.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/runtime_recovery.py", ("tests/components/planner/test_permit_recovery.py",)),
    ("src/runtime/state_persistence.py", ("tests/runtime/test_checkpoint_promotion.py",)),
    ("src/components/recovery/checkpoint.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/components/executor/graph.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/components/executor/node_runner.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/components/executor/value_store.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/support/run_execution_fence.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/runtime/v2/identity_projection.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/components/scheduler/", ("tests/components/scheduler/test_binder.py", "tests/components/scheduler/test_redis_leases.py")),
    ("src/runtime/execution_permit.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/support/stores/execution_permit_store.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/contracts/execution_permit.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/contracts/graph_handoff.py", ("tests/components/planner/test_execution_permit.py",)),
    ("src/contracts/graph_activation.py", ("tests/components/planner/test_execution_permit.py",)),
)

# Accepted INT-1 entry content, never HEAD. API uses that Windows checkout's
# raw CRLF digest; the gate used LF. CLI did not exist at the accepted entry.
EXTERNAL_BASELINE = {
    # R1 domain compatibility fixes await independent reference acceptance.
    "apps/agent/packs/programmer/workflows/requirement_analysis.yaml": None,
    "apps/agent/packs/legal/planning/contract_review_blueprint.py": None,
    "apps/agent/packs/legal/workflows/contract_review.yaml": None,
    # Application entry reviewed at INT-2A-1-FIX-REVIEW-REMEDIATION (lifespan
    # cleanup extracted to app.lifespan); drift forces the mapped tests.
    "apps/agent/app/main.py": "f086ec71a00d5cb305fc6d68c34494bca011bc991b7d658caf4a400d4c56757d",
    # Lifespan cleanup contract at INT-2A-1-FIX-REVIEW-REMEDIATION-2
    # (cancellation safety); drift forces the lifespan cleanup tests.
    "apps/agent/app/lifespan.py": "1e4f5e7cabfd5df60ed8a7d3deb1ccd5e72b3f59499e6389ff01a422ced19b01",
    "apps/agent/app/api/agentos_v2.py": "b78ffdd8d0b1c004f9befdd63c7372070cf9a733c244f86591328897791ccc21",
    # PR-UI-04.2 assembly review: existing workspace authorization/composition
    # changes were rechecked against the assembly/schema suites. INT-1 stays fixed.
    "apps/agent/app/execution/wiring.py": "961b6810af095ebf7fb5b2cfe296844ac686fe1644f715bb68b9ac7e65aa5af6",
    # New ownership boundaries await independent reference acceptance. None
    # forces their real tests on every gate; actual bytes still fingerprint the run.
    "apps/agent/app/execution/coordinator.py": None,
    "apps/agent/app/execution/model_runtime.py": None,
    "apps/agent/app/tools/formal_workspace.py": None,
    # Instance lock reviewed at INT-2A-1-FIX-REVIEW-FIX;
    # drift forces the assembly failure-cleanup tests mapped above.
    "apps/agent/app/execution/instance_lock.py": "b52efb5e1fd6c193ffb63734f3e10bf83597277dbe5992bce59deb7a1b7ff757",
    "scripts/freeze_gate.py": "06816f400a6d5a6143ead0f9d32af1d70a2715202cbbcd7223e05df1469d0637",
    # Bounded pytest launcher born at INT-2A-1-FIX-REVIEW-REMEDIATION
    # (WinError 206); drift forces the gate integrity tests.
    "scripts/freeze_gate_pytest_runner.py": "68736bccd5b3cfaf0fbbd02a800ef23b12d03c269c471e4693a11ca77a8345ef",
    "scripts/upgrade_agentos_c2_schema.py": None,
}
# These test inputs live outside AgentOS's src/tests snapshot. Track their
# actual bytes in the external fingerprint and always select them until an
# independent review accepts a fixed reference; never reuse a partial profile.
APP_TEST_INPUTS = (
    "apps/agent/tests/test_execution_history_compatibility.py",
    "apps/agent/tests/test_execution_runtime_domain_packs.py",
    "apps/agent/tests/test_general_golden_recovery.py",
    "apps/agent/tests/test_general_golden_evolution.py",
    "apps/agent/tests/test_legal_execution_runtime_vertical_slice.py",
    "apps/agent/tests/test_execution_adapter_settlement.py",
    "apps/agent/tests/test_managed_execution_settlement.py",
    "apps/agent/tests/test_execution_coordinator.py",
    "apps/agent/tests/test_acg_model_runtime.py",
    "apps/agent/tests/test_runtime_streaming_production_e2e.py",
    "apps/agent/tests/test_mission_semantic_commands.py",
    "apps/agent/tests/test_execution_runtime_application_wiring.py",
    "apps/agent/tests/test_branch_safe_mission_lifecycle.py",
    "apps/agent/tests/conftest.py",
)
EXTERNAL_BASELINE.update(dict.fromkeys(APP_TEST_INPUTS))
EXTERNAL_SOURCES = tuple(EXTERNAL_BASELINE)
PYTHONPATH_SEPARATOR = os.pathsep


def external_snapshot() -> dict[str, str | None]:
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            if (ROOT / path).is_file() else None for path in EXTERNAL_SOURCES}


def changed_external_paths(snapshot: dict[str, str | None]) -> list[str]:
    return sorted(path for path in EXTERNAL_SOURCES if snapshot.get(path) != EXTERNAL_BASELINE[path])


class BaselineIntegrityError(ValueError):
    pass


def load_baseline(path: Path) -> dict:
    """Authenticate the accepted manifest before selecting any tests.

    --baseline may locate a byte-identical copy, never silently establish a
    different acceptance baseline. Missing/corrupt files cannot fall back to
    HEAD, even in a clean checkout.
    """
    try:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != BASELINE_SHA256:
            raise ValueError("content SHA-256 differs from accepted INT-1 entry")
        baseline = json.loads(raw)
        files = baseline["files"]
        if not isinstance(files, dict) or len(files) != 445:
            raise ValueError("invalid file manifest")
        manifest = "\n".join(f"{p} {d}" for p, d in sorted(files.items()))
        aggregate = hashlib.sha256(manifest.encode("utf8")).hexdigest()
        if baseline["aggregate"] != aggregate or aggregate != BASELINE_AGGREGATE:
            raise ValueError("manifest aggregate differs from accepted INT-1 entry")
        return baseline
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BaselineIntegrityError(f"baseline integrity failure: {path}: {exc}") from exc


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def source_snapshot() -> dict[str, object]:
    files: dict[str, str] = {}
    for folder in ("src", "tests"):
        for path in sorted((AGENTOS / folder).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = "\n".join(f"{path} {digest}" for path, digest in sorted(files.items()))
    return {
        "aggregate": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        "files": files,
    }


def changed_python_paths(current: dict[str, object], baseline_path: Path) -> tuple[list[str], str]:
    old_files = load_baseline(baseline_path)["files"]
    now_files = current["files"]
    assert isinstance(now_files, dict)
    changed = sorted(path for path in set(old_files) | set(now_files)
                     if old_files.get(path) != now_files.get(path))
    return changed, str(baseline_path)


def resolve_tests(changed_paths: list[str]) -> tuple[list[str], list[str]]:
    changed_sources = [
        path.removeprefix("apps/agentOS/")
        for path in changed_paths
        if (path.startswith("apps/agentOS/src/") or path in EXTERNAL_SOURCES)
        and path.endswith(".py") and path not in APP_TEST_INPUTS
    ]
    changed_tests = [
        path.removeprefix("apps/agentOS/")
        for path in changed_paths
        if path.startswith("apps/agentOS/tests/") and path.endswith(".py")
    ]
    changed_tests.extend("../agent/tests/" + Path(path).name for path in changed_paths
                         if path in APP_TEST_INPUTS and Path(path).name.startswith("test_"))
    if "apps/agent/tests/conftest.py" in changed_paths:
        changed_tests.extend("../agent/tests/" + Path(path).name for path in APP_TEST_INPUTS
                             if Path(path).name.startswith("test_"))
    selected: set[str] = set(changed_tests)
    uncovered: list[str] = []
    for source in changed_sources:
        rules = [tests for prefix, tests in SOURCE_TEST_RULES if source == prefix or source.startswith(prefix)]
        mapped = {test for group in rules for test in group}
        if not mapped:
            uncovered.append(source)
            continue
        selected.update(mapped)
    return sorted(selected), uncovered


def parse_pytest_counts(output: str) -> dict[str, int | None]:
    # Read pytest's final summary only. A timed-out partial run is explicitly
    # marked incomplete by the caller even if some tests already passed.
    summary = next((line for line in reversed(output.splitlines()) if re.search(r"\b(in|no tests ran)\b", line)), "")
    counts: dict[str, int | None] = {}
    for name in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed", "deselected"):
        found = re.search(rf"\b(\d+)\s+{name}\b", summary)
        counts[name] = int(found.group(1)) if found else (0 if summary else None)
    collected = re.search(r"\bcollected\s+(\d+)\s+items?\b", output)
    counts["collected"] = int(collected.group(1)) if collected else None
    counted = sum(counts[name] or 0 for name in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed", "deselected"))
    counts["not_completed"] = max(0, counts["collected"] - counted) if counts["collected"] is not None else None
    return counts


def measured_test_durations(output: str) -> dict[str, float]:
    durations: dict[str, float] = {}
    pattern = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)s\s+(?:setup|call|teardown)\s+(.+)$")
    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            seconds, node_id = float(match.group(1)), match.group(2).strip()
            durations[node_id] = durations.get(node_id, 0.0) + seconds
    return durations


def _normalize_history(payload: object) -> dict[str, dict[str, float]]:
    """Accept both the legacy max-only file and the {max, last} record file.

    Legacy flat entries are maxima from older gate runs; their last observation
    is genuinely unknown and stays unknown instead of being guessed.
    """
    if not isinstance(payload, dict):
        return {}
    history: dict[str, dict[str, float]] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            maximum = value.get("max")
            last = value.get("last")
            record = {"max": float(maximum)} if isinstance(maximum, (int, float)) else {}
            if isinstance(last, (int, float)):
                record["last"] = float(last)
            if record:
                history[str(key)] = record
        elif isinstance(value, (int, float)):
            history[str(key)] = {"max": float(value)}
    return history


def update_duration_history(durations: dict[str, float]) -> dict[str, object]:
    path = ROOT / "tmp" / "freeze_gate" / "test_durations.json"
    history: dict[str, object] = {}
    if path.is_file():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(history, dict):
                raise ValueError('invalid duration history')
        except (ValueError, TypeError) as exc:
            raise ValueError('refusing to overwrite invalid duration history') from exc
    # Preserve legacy flat values, old last fields, and unknown metadata. No
    # migration/reinterpretation into a complete profile takes place here.
    for node_id, seconds in durations.items():
        prior = history.get(node_id, 0.0)
        if isinstance(prior, dict):
            history[node_id] = {**prior, 'max': max(prior.get('max', 0.0), seconds)}
        elif isinstance(prior, (int, float)):
            history[node_id] = max(prior, seconds)
        else:
            raise ValueError('refusing to discard an unknown history record')
    atomic_json(path, history)
    return history


def load_duration_history() -> dict[str, dict[str, float]]:
    path = ROOT / "tmp" / "freeze_gate" / "test_durations.json"
    if not path.is_file():
        return {}
    try:
        return _normalize_history(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, TypeError):
        return {}


def atomic_json(path: Path, value, *, deadline=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                        delete=False, prefix='.gate-', suffix='.tmp') as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        if deadline is not None and time.perf_counter() > deadline:
            raise TimeoutError('profile publication exceeded gate budget')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def duration_cache_lock():
    """Nonblocking OS lock: concurrent publishers cannot lose historical max.

    The lock file is not a recovery marker; the OS releases it on process exit.
    """
    path = ROOT / 'tmp/freeze_gate/duration-cache.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if sys.platform == 'win32':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if sys.platform == 'win32':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def manifest_sha256(node_ids):
    return hashlib.sha256(('\n'.join(node_ids) + '\n').encode('utf-8')).hexdigest()


def profile_source_sha256(snapshot, external):
    # Include the launcher and external sources, not just the AgentOS subtree.
    return hashlib.sha256(json.dumps(dict(agentos=snapshot['aggregate'], external=external),
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def complete_profile(source_sha, node_ids, observation, *, invocation_id, exit_code,
                     timed_out, process_seconds):
    """Only exit 0 with every selected node fully passed is eligible (v1)."""
    def number(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    if timed_out or exit_code != 0:
        raise ValueError('PROCESS_INCOMPLETE_OR_UNSUCCESSFUL')
    if (not node_ids or len(set(node_ids)) != len(node_ids) or not number(process_seconds)
            or not isinstance(observation, dict) or type(observation.get('version')) is not int
            or observation.get('version') != 1
            or not invocation_id or observation.get('invocationId') != invocation_id
            or observation.get('manifestSha256') != manifest_sha256(node_ids)
            or type(observation.get('sessionExitCode')) is not int or observation.get('sessionExitCode') != 0
            or type(observation.get('processExitCode')) is not int or observation.get('processExitCode') != 0):
        raise ValueError('INVALID_EXECUTION_OBSERVATION')
    collected = observation.get('collectedNodeIds')
    if not isinstance(collected, list) or sorted(collected) != sorted(node_ids):
        raise ValueError('COLLECTION_MANIFEST_MISMATCH')
    phases = {node: {} for node in node_ids}
    reports = observation.get('reports')
    if not isinstance(reports, list):
        raise ValueError('MISSING_EXECUTION_REPORTS')
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError('INVALID_PHASE_REPORT')
        node, phase = report.get('nodeId'), report.get('phase')
        if (node not in phases or phase not in {'setup', 'call', 'teardown'}
                or phase in phases[node] or report.get('outcome') != 'passed'
                or report.get('expectedFailure') is not False or not number(report.get('durationSeconds'))):
            raise ValueError('INVALID_OR_DUPLICATE_PHASE')
        phases[node][phase] = report['durationSeconds']
    if any(set(value) != {'setup', 'call', 'teardown'} for value in phases.values()):
        raise ValueError('PARTIAL_NODE_EXECUTION')
    durations = {node: math.fsum(value.values()) for node, value in phases.items()}
    total = math.fsum(durations.values())
    if not math.isfinite(total):
        raise ValueError('INVALID_DURATION_TOTAL')
    return dict(version=1, sourceSha256=source_sha, manifestSha256=manifest_sha256(node_ids),
        nodeCount=len(node_ids), collectedCount=len(collected), executedCount=len(phases),
        nodeDurationsSeconds=durations, testDurationSumSeconds=total,
        processElapsedSeconds=process_seconds, estimateSeconds=max(total, process_seconds),
        observation=observation)


def complete_profile_path(source_sha, manifest_sha):
    # A bounded name also works inside Windows pytest temporary directories.
    key = hashlib.sha256((source_sha + ':' + manifest_sha).encode('ascii')).hexdigest()
    return ROOT / 'tmp/freeze_gate/complete_profiles' / (key + '.json')


def profile_path(source_sha, node_ids):
    return complete_profile_path(source_sha, manifest_sha256(node_ids))


def load_complete_estimate(source_sha, node_ids):
    try:
        with duration_cache_lock():
            return _load_complete_estimate(source_sha, node_ids)
    except OSError:
        return dict(status="UNKNOWN", reason="PROFILE_READ_LOCK_UNAVAILABLE", seconds=None)


def _load_complete_estimate(source_sha, node_ids):
    unknown = dict(status='UNKNOWN', reason='NO_MATCHING_COMPLETE_PROFILE', seconds=None)
    try:
        stored = json.loads(profile_path(source_sha, node_ids).read_text(encoding='utf-8'))
        if stored.get('sourceSha256') != source_sha or stored.get('manifestSha256') != manifest_sha256(node_ids):
            return {**unknown, 'reason': 'PROFILE_IDENTITY_MISMATCH'}
        observation = stored['observation']
        rebuilt = complete_profile(source_sha, node_ids, observation,
            invocation_id=observation['invocationId'], exit_code=0, timed_out=False,
            process_seconds=stored['processElapsedSeconds'])
        if rebuilt != stored:
            return {**unknown, 'reason': 'PROFILE_CONTENT_MISMATCH'}
        return dict(status='KNOWN', reason='MATCHING_COMPLETE_PROFILE', seconds=rebuilt['estimateSeconds'],
                    testDurationSumSeconds=rebuilt['testDurationSumSeconds'])
    except FileNotFoundError:
        return unknown
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {**unknown, 'reason': 'INVALID_OR_UNREADABLE_PROFILE'}
def pytest_environment():
    env = os.environ.copy()
    roots = (AGENTOS / "src", AGENTOS, ROOT / "apps/agent", AGENTOS / "tests/runtime",
             AGENTOS / "tests/components/planner", ROOT / "apps/agent/tests")
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = PYTHONPATH_SEPARATOR.join([*(str(path) for path in roots), *([prior] if prior else [])])
    env["PYTHONUTF8"] = "1"
    return env


def collect_node_ids(paths: list[str], timeout: float) -> tuple[list[str], int, str]:
    command = [
        sys.executable, "-m", "pytest", "--collect-only", "-q", *paths,
        "--rootdir", str(ROOT), "-c", str(AGENTOS / "pytest.ini"), "-m", FAST_OR_CRITICAL,
    ]
    completed = subprocess.run(
        command, cwd=AGENTOS, text=True, encoding="utf-8", errors="replace",
        capture_output=True, timeout=timeout, env=pytest_environment(),
    )
    node_ids = sorted({
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip().replace("\\", "/").startswith(("tests/", "apps/agentOS/tests/", "apps/agent/tests/")) and "::" in line
    })
    return node_ids, completed.returncode, completed.stdout + completed.stderr


PYTEST_RUNNER = ROOT / "scripts" / "freeze_gate_pytest_runner.py"


def write_node_manifest(node_ids: list[str], path: Path) -> None:
    """Persist the exact selection; the launch command stays length-bounded.

    Windows caps CreateProcess command lines at 32767 characters.  Passing
    every node ID as an argument crashed the gate with WinError 206 once the
    selection grew past that bound, so the selection travels as data.
    """
    path.write_text("\n".join(node_ids) + "\n", encoding="utf-8", newline="\n")


def build_pytest_command(manifest_path: Path) -> list[str]:
    """Constant-length pytest launch; the node IDs travel in the manifest."""
    return [
        sys.executable, str(PYTEST_RUNNER), str(manifest_path),
        "--rootdir", str(ROOT), "-c", str(AGENTOS / "pytest.ini"), "--tb=short", "--durations=0",
    ]


def check_diff_whitespace() -> tuple[int, str]:
    completed = subprocess.run(
        ["git", "diff", "--check", "HEAD"], cwd=ROOT,
        text=True, encoding="utf-8", errors="replace", capture_output=True,
    )
    return completed.returncode, (completed.stdout + completed.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                        help="prior src/tests snapshot manifest (default: frozen C2A-3 at INT-1 entry)")
    parser.add_argument("--budget-seconds", type=int, default=DEFAULT_BUDGET_SECONDS,
                        help="hard stage-freeze budget; values above 300 are rejected")
    parser.add_argument("--dry-run", action="store_true", help="show selected tests without executing pytest")
    args = parser.parse_args()
    if not 1 <= args.budget_seconds <= DEFAULT_BUDGET_SECONDS:
        parser.error("--budget-seconds must be between 1 and 300")

    baseline_path = args.baseline if args.baseline.is_absolute() else ROOT / args.baseline
    invocation_id = uuid.uuid4().hex
    artifact_id = new_artifact_id(invocation_id)
    started = utc_now()
    wall_start = time.perf_counter()
    before = source_snapshot()
    external_before = external_snapshot()
    try:
        changed, baseline_name = changed_python_paths(before, baseline_path)
    except BaselineIntegrityError as exc:
        return write_report({"artifact_id": artifact_id, "invocation_id": invocation_id, "started_utc": started, "budget_seconds": args.budget_seconds,
            "status": "BLOCKED_BASELINE_INTEGRITY", "baseline": str(baseline_path),
            "error": str(exc), "pytest_counts": None, "pytest_command": None,
            "source_aggregate_sha256": before["aggregate"]}, wall_start, 2)
    external_changed = changed_external_paths(external_before)
    changed = sorted(set(changed + external_changed))
    selected, uncovered = resolve_tests(changed)
    missing = [path for path in selected if not (AGENTOS / path.split("::", 1)[0]).is_file()]
    check_code, check_output = check_diff_whitespace()

    report: dict[str, object] = {
        "artifact_id": artifact_id,
        "invocation_id": invocation_id,
        "started_utc": started,
        "finished_utc": None,
        "budget_seconds": args.budget_seconds,
        "baseline": baseline_name,
        "baseline_commit": BASELINE_COMMIT,
        "baseline_sha256": BASELINE_SHA256,
        "external_baseline_sha256": EXTERNAL_BASELINE,
        "source_aggregate_sha256": before["aggregate"],
        "source_file_count": len(before["files"]),  # type: ignore[arg-type]
        "external_source_sha256": external_before,
        "changed_agentos_python_files": changed,
        "selected_test_paths": selected,
        "uncovered_source_paths": uncovered,
        "missing_test_paths": missing,
        "missing_external_source_paths": [p for p, digest in external_before.items() if digest is None],
        "git_diff_check_exit_code": check_code,
        "git_diff_check_output": check_output,
        "status": "NOT_STARTED",
        "pytest_command": None,
        "pytest_counts": None,
        "elapsed_seconds": 0.0,
        "log_path": None,
        "complete_profile_published": None,
    }
    if args.dry_run:
        report["status"] = "DRY_RUN"
        report["finished_utc"] = utc_now()
        report["elapsed_seconds"] = round(time.perf_counter() - wall_start, 3)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if not uncovered and not missing and not report["missing_external_source_paths"] and check_code == 0 else 2
    if uncovered or missing or report["missing_external_source_paths"] or check_code != 0:
        report["status"] = "BLOCKED_BEFORE_TESTS"
        return write_report(report, wall_start, 2)
    if not changed:
        report["status"] = "NO_AGENTOS_PYTHON_CHANGES"
        return write_report(report, wall_start, 0)
    if not selected:
        report["status"] = "NO_TESTS_SELECTED"
        return write_report(report, wall_start, 2)

    remaining = max(0.0, args.budget_seconds - (time.perf_counter() - wall_start))
    if remaining <= 0:
        report["status"] = "INCOMPLETE_TIMEOUT_DURING_DISCOVERY"
        return write_report(report, wall_start, 1)
    try:
        node_ids, collect_exit, collect_output = collect_node_ids(selected, remaining)
    except subprocess.TimeoutExpired:
        report["status"] = "INCOMPLETE_TIMEOUT_DURING_DISCOVERY"
        return write_report(report, wall_start, 1)
    report["collected_test_node_ids"] = node_ids
    report["collection_exit_code"] = collect_exit
    report["collection_output_tail"] = collect_output.splitlines()[-8:]
    if collect_exit != 0 or not node_ids:
        report["status"] = "BLOCKED_TEST_DISCOVERY" if collect_exit != 0 else "NO_TESTS_SELECTED"
        return write_report(report, wall_start, 2)

    duration_history = load_duration_history()
    source_sha = profile_source_sha256(before, external_before)
    estimate = load_complete_estimate(source_sha, node_ids)
    max_sum = sum(duration_history[node_id].get("max", 0.0) for node_id in node_ids
                  if node_id in duration_history)
    remaining = max(0.0, args.budget_seconds - (time.perf_counter() - wall_start))
    report['profile_source_sha256'] = source_sha
    report['node_manifest_sha256'] = manifest_sha256(node_ids)
    report['node_manifest_count'] = len(node_ids)
    report['duration_estimate'] = estimate
    report["historical_max_duration_sum_seconds"] = round(max_sum, 3)
    report["duration_unknown_test_node_ids"] = node_ids if estimate['status'] == 'UNKNOWN' else []
    if estimate['status'] == 'KNOWN' and estimate['seconds'] > remaining:
        report["status"] = "BLOCKED_KNOWN_DURATION_OVER_BUDGET"
        report["remaining_budget_before_tests_seconds"] = round(remaining, 3)
        return write_report(report, wall_start, 1)
    if remaining <= 0:
        report["status"] = "INCOMPLETE_TIMEOUT_DURING_DISCOVERY"
        return write_report(report, wall_start, 1)

    output_dir = ROOT / "tmp" / "freeze_gate"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = artifact_id
    log_path = output_dir / f"{stamp}.log"
    report_path = output_dir / f"{stamp}.json"
    manifest_path = output_dir / f"{stamp}.nodeids"
    write_node_manifest(node_ids, manifest_path)
    command = build_pytest_command(manifest_path)
    report["pytest_command"] = command
    report["node_manifest_path"] = str(manifest_path.relative_to(ROOT))
    report["node_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    report["node_manifest_count"] = len(node_ids)
    report["log_path"] = str(log_path.relative_to(ROOT))
    env = pytest_environment()
    env["PYTHONUTF8"] = "1"
    observation_path = output_dir / (stamp + '.observation.json')
    env['FREEZE_GATE_OBSERVATION_PATH'] = str(observation_path)
    env['FREEZE_GATE_INVOCATION_ID'] = invocation_id
    report['invocation_id'] = invocation_id
    report['observation_path'] = str(observation_path.relative_to(ROOT))
    timed_out = False
    launch_error: dict[str, object] | None = None
    remaining = max(0.0, args.budget_seconds - (time.perf_counter() - wall_start))
    process_started = time.perf_counter()
    with log_path.open("wb") as log:
        if remaining <= 0:
            process = None
            timed_out = True
        else:
            try:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
            except OSError as exc:
                # The launcher itself could not start (e.g. Windows WinError
                # 206 command-line overflow).  This is not a test run: report
                # the refusal while the manifest recorded above still
                # identifies the exact unexecuted selection.
                process = None
                launch_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback_tail": traceback.format_exc().strip().splitlines()[-4:],
                }
            if process is not None:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       cwd=ROOT, capture_output=True, check=False)
                    else:
                        process.kill()
                    process.wait()
    process_seconds = time.perf_counter() - process_started
    if launch_error is not None:
        report["pytest_launch_error"] = launch_error
        report["pytest_exit_code"] = None
        report["timed_out"] = False
        report["status"] = "INCOMPLETE_PYTEST_LAUNCH"
        return write_report(report, wall_start, 1, report_path)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    report["pytest_counts"] = parse_pytest_counts(output)
    observed_durations = measured_test_durations(output)
    report["measured_test_durations_seconds"] = observed_durations
    report["duration_history_file"] = "tmp/freeze_gate/test_durations.json"
    report["status"] = "INCOMPLETE_TIMEOUT" if timed_out else ("PASSED" if process and process.returncode == 0 else "FAILED")
    report["pytest_exit_code"] = process.returncode if process else None
    report["timed_out"] = timed_out
    try:
        load_baseline(baseline_path)
    except BaselineIntegrityError as exc:
        report["status"] = "INCOMPLETE_BASELINE_CHANGED"
        report["error"] = str(exc)
        return write_report(report, wall_start, 1, report_path)
    if source_snapshot()["aggregate"] != before["aggregate"] or external_snapshot() != external_before:
        report["status"] = "INCOMPLETE_SOURCE_CHANGED"
        return write_report(report, wall_start, 1, report_path)
    pending = None
    if report['status'] == 'PASSED':
        try:
            observation = json.loads(observation_path.read_text(encoding='utf-8'))
            pending = complete_profile(source_sha, node_ids, observation, invocation_id=invocation_id,
                exit_code=process.returncode, timed_out=timed_out,
                process_seconds=process_seconds)
            counts = report['pytest_counts']
            if counts['collected'] is not None and counts['collected'] != len(node_ids):
                raise ValueError('TERMINAL_COLLECTION_COUNT_MISMATCH')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            report['status'] = 'INCOMPLETE_EXECUTION_EVIDENCE'
            report['profile_rejection'] = str(exc)
            pending = None
    return write_report(report, wall_start, 0 if report['status'] == 'PASSED' else 1,
                        report_path, pending_profile=pending)


def new_artifact_id(invocation_id):
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + '-' + invocation_id


def restore_profile(path, previous):
    """Called under the publisher lock; never leave an uncommitted profile."""
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, prefix='.undo-') as stream:
                temporary = Path(stream.name)
                stream.write(previous)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def write_report(report: dict[str, object], wall_start: float, exit_code: int, report_path: Path | None = None,
                 *, pending_profile=None) -> int:
    # Success completes only after the final atomic report replacement returns
    # within budget. stdout is diagnostic and outside this persistence boundary.
    deadline = wall_start + report.get('budget_seconds', DEFAULT_BUDGET_SECONDS)
    report.setdefault('invocation_id', uuid.uuid4().hex)
    report.setdefault('artifact_id', new_artifact_id(report['invocation_id']))
    if report_path is None:
        report_path = ROOT / 'tmp/freeze_gate' / (report['artifact_id'] + '.json')
    report['budget_completion_boundary'] = 'FINAL_REPORT_ATOMIC_REPLACE_RETURNED'

    def stamp():
        report['elapsed_seconds'] = round(time.perf_counter() - wall_start, 6)
        report['finished_utc'] = utc_now()

    def check_deadline():
        if time.perf_counter() > deadline:
            raise TimeoutError('gate persistence exceeded budget')

    def publish_report():
        stamp()
        atomic_json(report_path, report, deadline=deadline)
        check_deadline()  # replace/fsync can itself consume the remaining budget

    path = None
    previous = None
    try:
        with duration_cache_lock():
            try:
                check_deadline()
                if report.get('status') == 'PASSED' and exit_code == 0 and pending_profile is not None:
                    if profile_source_sha256(source_snapshot(), external_snapshot()) != pending_profile['sourceSha256']:
                        report['status'] = 'INCOMPLETE_SOURCE_CHANGED'
                        exit_code = 1
                    elif hashlib.sha256((ROOT / report['node_manifest_path']).read_bytes()).hexdigest() != pending_profile['manifestSha256']:
                        report['status'] = 'INCOMPLETE_MANIFEST_CHANGED'
                        exit_code = 1
                    else:
                        update_duration_history(pending_profile['nodeDurationsSeconds'])
                        check_deadline()
                        candidate = complete_profile_path(pending_profile['sourceSha256'], pending_profile['manifestSha256'])
                        previous = candidate.read_bytes() if candidate.exists() else None
                        path = candidate
                        atomic_json(path, pending_profile, deadline=deadline)
                        check_deadline()
                        report['complete_profile_published'] = str(path.relative_to(ROOT))
                publish_report()
            except (OSError, ValueError, TypeError) as exc:
                if path is not None:
                    restore_profile(path, previous)
                report['complete_profile_published'] = None
                report['status'] = ('INCOMPLETE_GATE_BUDGET_EXCEEDED' if isinstance(exc, TimeoutError)
                                    else 'INCOMPLETE_PROFILE_STORAGE')
                report['profile_rejection'] = str(exc)
                exit_code = 1
                stamp()
                # Failure evidence is allowed after deadline; never a PASS.
                atomic_json(report_path, report)
    except OSError as exc:
        report['status'] = 'INCOMPLETE_PROFILE_STORAGE'
        report['profile_rejection'] = str(exc)
        report['complete_profile_published'] = None
        exit_code = 1
        stamp()
        atomic_json(report_path, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
