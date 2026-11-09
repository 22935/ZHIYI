"""Mapping and fail-closed reporting, without a real 300-second timeout."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]


def load():
    return runpy.run_path(str(ROOT / "scripts/freeze_gate.py"))


@pytest.mark.parametrize("damage", ["missing", "digest", "aggregate", "replacement"])
def test_untrusted_baseline_never_falls_back_to_clean_head(tmp_path, damage):
    gate = load()
    path = tmp_path / "baseline.json"
    original = json.loads(gate["DEFAULT_BASELINE"].read_text(encoding="utf8"))
    if damage == "digest":
        original["files"][next(iter(original["files"]))] = "0" * 64
        manifest = "\n".join(f"{p} {d}" for p, d in sorted(original["files"].items()))
        original["aggregate"] = hashlib.sha256(manifest.encode()).hexdigest()
    elif damage == "aggregate":
        original["aggregate"] = "0" * 64
    elif damage == "replacement":
        original = gate["source_snapshot"]()
    if damage != "missing":
        path.write_text(json.dumps(original), encoding="utf8")
    with pytest.raises(ValueError, match="baseline"):
        gate["changed_python_paths"](gate["source_snapshot"](), path)


def test_missing_default_baseline_blocks_before_test_discovery(tmp_path, monkeypatch, capsys):
    gate = load()
    ns = gate["main"].__globals__
    monkeypatch.setitem(ns, "ROOT", tmp_path)
    monkeypatch.setitem(ns, "AGENTOS", tmp_path / "apps/agentOS")
    monkeypatch.setitem(ns, "DEFAULT_BASELINE", tmp_path / "missing.json")
    monkeypatch.setitem(ns, "collect_node_ids", lambda *a: pytest.fail("test discovery before baseline validation"))
    monkeypatch.setattr(sys, "argv", ["freeze_gate.py", "--dry-run"])
    assert gate["main"]() != 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED_BASELINE_INTEGRITY"
    assert result["pytest_counts"] is None


@pytest.mark.parametrize("source", ["scripts/freeze_gate.py", "apps/agent/app/api/agentos_v2.py",
                                    "apps/agent/app/main.py",
                                    "apps/agent/app/execution/wiring.py",
                                    "apps/agent/app/execution/instance_lock.py",
                                    "apps/agent/app/execution/coordinator.py",
                                    "apps/agent/app/execution/model_runtime.py",
                                    "apps/agent/app/tools/formal_workspace.py",
                                    "scripts/upgrade_agentos_c2_schema.py"])
def test_committed_external_changes_use_fixed_reference_not_head(tmp_path, monkeypatch, source):
    gate = load()
    ns = gate["external_snapshot"].__globals__
    target = tmp_path / source
    target.parent.mkdir(parents=True)
    target.write_text("# accepted\n", encoding="utf8")
    accepted = hashlib.sha256(target.read_bytes()).hexdigest()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True)
    git("init", "-q")
    git("add", ".")
    git("-c", "user.name=fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "accepted")
    target.write_text("# committed change\n", encoding="utf8")
    git("add", ".")
    git("-c", "user.name=fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "changed")
    assert git("diff", "HEAD", "--", source) == ""
    monkeypatch.setitem(ns, "ROOT", tmp_path)
    monkeypatch.setitem(ns, "EXTERNAL_SOURCES", (source,))
    monkeypatch.setitem(ns, "EXTERNAL_BASELINE", {source: accepted})
    changed = gate["changed_external_paths"](gate["external_snapshot"]())
    assert changed == [source]
    selected, uncovered = gate["resolve_tests"](changed)
    assert selected and not uncovered
    assert all((ROOT / "apps/agentOS" / p.split("::", 1)[0]).is_file() for p in selected)


@pytest.mark.parametrize("source,required", [
    ("src/components/executor/graph.py", "tests/test_acg_execution_graph.py"),
    ("src/components/executor/graph.py", "tests/components/executor/test_advanced_acg_capabilities.py"),
    ("src/components/executor/compiler.py", "tests/test_acg_execution_graph.py"),
    ("src/components/executor/compiler.py", "tests/components/planner/test_acg_semantic_preservation.py"),
    ("src/runtime/acg_execution.py", "tests/runtime/test_resource_binding.py"),
    ("src/components/resource/__init__.py", "tests/components/resource/test_resource_auth.py"),
    ("src/components/resource/errors.py", "tests/components/resource/test_remote_observation.py"),
    ("src/components/resource/health_store.py", "tests/components/resource/test_health_store.py"),
    ("src/components/resource/node_health.py", "tests/components/resource/test_node_store.py"),
    ("src/components/resource/node_store.py", "tests/components/resource/test_node_store.py"),
    ("src/components/resource/service.py", "tests/components/resource/test_resource_auth.py"),
    ("src/components/resource/sqlite_support.py", "tests/components/resource/test_store_contract.py"),
    ("src/components/resource/store.py", "tests/components/resource/test_store_contract.py"),
    ("src/contracts/resource.py", "tests/components/resource/test_edge_cloud_contracts.py"),
    ("src/components/resource/scheduler/binder.py", "tests/components/scheduler/test_binder.py"),
    ("src/components/resource/scheduler/leases.py", "tests/components/scheduler/test_redis_leases.py"),
    ("src/components/resource/scheduler/models.py", "tests/components/scheduler/test_binder.py"),
    ("src/support/stores/c2_schema_upgrade.py", "tests/storage/test_c2_schema_integrity.py"),
    ("scripts/upgrade_agentos_c2_schema.py", "tests/storage/test_c2_schema_upgrade.py"),
    ("apps/agent/app/execution/wiring.py", "tests/components/planner/test_production_authority_assembly.py"),
    ("apps/agent/app/execution/instance_lock.py", "tests/storage/test_runtime_assembly_failure_cleanup.py"),
    ("apps/agent/app/main.py", "tests/storage/test_runtime_assembly_failure_cleanup.py"),
    ("src/support/async_tasks.py", "../agent/tests/test_execution_adapter_settlement.py"),
    ("apps/agent/app/execution/coordinator.py", "../agent/tests/test_managed_execution_settlement.py"),
    ("apps/agent/app/execution/model_runtime.py", "../agent/tests/test_execution_adapter_settlement.py"),
    ("apps/agent/app/tools/formal_workspace.py", "../agent/tests/test_execution_adapter_settlement.py"),
])
def test_relevant_source_resolves_real_related_tests(source, required):
    gate = load()
    path = source if source.startswith(("scripts/", "apps/agent/")) else "apps/agentOS/" + source
    selected, uncovered = gate["resolve_tests"]([path])
    assert not uncovered
    assert required in selected
    assert all((gate["AGENTOS"] / item.split("::", 1)[0]).is_file() for item in selected)


def test_entire_original_baseline_delta_is_mapped_without_moving_baseline():
    gate = load()
    baseline = gate["DEFAULT_BASELINE"]
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == "54ccc02a3d0ba550fffff8dd23f259460977ae0a75f3d8eea4d7c1848ce1a591"
    changed, _ = gate["changed_python_paths"](gate["source_snapshot"](), baseline)
    selected, uncovered = gate["resolve_tests"](changed)
    assert not uncovered, uncovered
    assert selected and len(selected) == len(set(selected))
    assert all((gate["AGENTOS"] / item.split("::", 1)[0]).is_file() for item in selected)


def test_production_composition_root_is_pinned_and_drift_forces_assembly_tests():
    """The wiring.py external entry must protect the assembly, not just list it."""
    gate = load()
    source = "apps/agent/app/execution/wiring.py"
    assert source in gate["EXTERNAL_SOURCES"]
    current = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    assert gate["EXTERNAL_BASELINE"][source] == current
    selected, uncovered = gate["resolve_tests"]([source])
    assert uncovered == []
    assert "tests/components/planner/test_production_authority_assembly.py" in selected
    assert "tests/storage/test_c2_schema_upgrade.py" in selected
    # Any content drift on the composition root is flagged and maps to the
    # assembly tests: the baseline digest may only move together with them.
    drifted = dict(gate["external_snapshot"]())
    drifted[source] = "0" * 64
    assert source in gate["changed_external_paths"](drifted)
    selected, uncovered = gate["resolve_tests"](gate["changed_external_paths"](drifted))
    assert uncovered == [] and "tests/components/planner/test_production_authority_assembly.py" in selected


@pytest.mark.parametrize("source", ["apps/agent/app/execution/coordinator.py",
    "apps/agent/app/execution/model_runtime.py", "apps/agent/app/tools/formal_workspace.py"])
def test_execution_owners_are_tracked_and_drift_forces_real_settlement_tests(source):
    gate = load()
    assert source in gate["EXTERNAL_SOURCES"]
    assert gate["external_snapshot"]()[source] == hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    drifted = dict(gate["external_snapshot"]())
    drifted[source] = "0" * 64
    assert source in gate["changed_external_paths"](drifted)
    selected, uncovered = gate["resolve_tests"]([source])
    assert not uncovered
    assert any(path.endswith(("test_managed_execution_settlement.py", "test_execution_adapter_settlement.py")) for path in selected)


def test_external_app_test_bytes_participate_in_the_source_fingerprint(tmp_path, monkeypatch):
    gate = load()
    source = 'apps/agent/tests/test_execution_adapter_settlement.py'
    assert source in gate['EXTERNAL_SOURCES']
    ns = gate['external_snapshot'].__globals__
    monkeypatch.setitem(ns, 'ROOT', tmp_path)
    path = tmp_path / source
    path.parent.mkdir(parents=True)
    path.write_text('before', encoding='utf-8')
    before = gate['external_snapshot']()
    path.write_text('after', encoding='utf-8')
    after = gate['external_snapshot']()
    assert before[source] != after[source]
    selected, uncovered = gate['resolve_tests']([source])
    assert not uncovered and '../agent/tests/test_execution_adapter_settlement.py' in selected


def test_real_cross_root_collection_and_manifest_execution_cannot_drop_app_tests(tmp_path):
    gate = load()
    nodes, code, output = gate['collect_node_ids']([
        '../agent/tests/test_execution_adapter_settlement.py::test_repeated_parent_cancellation_waits_for_child_cleanup',
        'tests/support/test_execution_settlement_persistence.py::test_stale_event_snapshot_cas_preserves_run_mission_and_outbox[memory]',
    ], timeout=120)
    assert code == 0, output
    assert set(nodes) == {
        'apps/agent/tests/test_execution_adapter_settlement.py::test_repeated_parent_cancellation_waits_for_child_cleanup',
        'apps/agentOS/tests/support/test_execution_settlement_persistence.py::test_stale_event_snapshot_cas_preserves_run_mission_and_outbox[memory]',
    }
    manifest = tmp_path / 'cross-root.nodeids'
    gate['write_node_manifest'](nodes, manifest)
    observed = tmp_path / 'observed.json'
    env = {**gate['pytest_environment'](), 'FREEZE_GATE_OBSERVATION_PATH': str(observed),
           'FREEZE_GATE_INVOCATION_ID': 'cross-root'}
    done = subprocess.run(gate['build_pytest_command'](manifest), cwd=gate['ROOT'], env=env,
                          capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    evidence = json.loads(observed.read_text())
    assert sorted(evidence['collectedNodeIds']) == nodes
    assert {entry['nodeId'] for entry in evidence['reports']} == set(nodes)


def test_instance_lock_is_pinned_and_drift_forces_cleanup_tests():
    """The instance lock entry must protect failure cleanup, not just exist."""
    gate = load()
    source = "apps/agent/app/execution/instance_lock.py"
    assert source in gate["EXTERNAL_SOURCES"]
    current = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
    assert gate["EXTERNAL_BASELINE"][source] == current
    selected, uncovered = gate["resolve_tests"]([source])
    assert uncovered == []
    assert "tests/storage/test_runtime_assembly_failure_cleanup.py" in selected
    # Any content drift on the lock is flagged and maps to the failure-cleanup
    # tests: the baseline digest may only move together with them.
    drifted = dict(gate["external_snapshot"]())
    drifted[source] = "0" * 64
    assert source in gate["changed_external_paths"](drifted)
    selected, uncovered = gate["resolve_tests"](gate["changed_external_paths"](drifted))
    assert uncovered == [] and "tests/storage/test_runtime_assembly_failure_cleanup.py" in selected


@pytest.mark.parametrize("fault,status", [("sources", "INCOMPLETE_SOURCE_CHANGED"),
    ("schema_failure", "FAILED"), ("timeout", "INCOMPLETE_TIMEOUT"),
    ("baseline", "INCOMPLETE_BASELINE_CHANGED"),
    ("launch", "INCOMPLETE_PYTEST_LAUNCH")])
def test_gate_never_reports_success_for_changed_sources_failed_preflight_or_timeout(tmp_path, monkeypatch, fault, status):
    gate = load()
    ns = gate["main"].__globals__
    test_file = tmp_path / "agentOS/tests/test_target.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_target(): pass\n", encoding="utf8")
    baseline = tmp_path / "accepted.json"
    baseline.write_bytes(gate["DEFAULT_BASELINE"].read_bytes())
    snapshots = iter(("initial", "changed" if fault == "sources" else "initial"))
    # Control the child-process boundary only. Real SQLite failure/refusal is
    # exercised separately in test_c2_schema_integrity, not mocked here.
    class Child:
        def __init__(self, command, **kwargs):
            kwargs["stdout"].write(b"1 failed in 0.01s\n" if fault == "schema_failure" else b"1 passed in 0.01s\n")
            self.returncode = 1 if fault == "schema_failure" else 0
            if fault == "baseline":
                baseline.write_text("{}", encoding="utf8")
        def wait(self, timeout=None):
            if timeout is not None and fault == "timeout":
                raise subprocess.TimeoutExpired("pytest", timeout)
            return self.returncode
        def kill(self):
            pass

    def launch_refused(command, **kwargs):
        # Injectable stand-in for OS launch failures (WinError 206 et al.).
        raise OSError("[WinError 206] 文件名或扩展名太长。")
    for key, value in {
        "ROOT": tmp_path, "AGENTOS": test_file.parents[1],
        "source_snapshot": lambda: {"aggregate": next(snapshots), "files": {"source": "hash"}},
        "external_snapshot": lambda: {}, "check_diff_whitespace": lambda: (0, ""),
        "changed_python_paths": lambda *a: (["source"], "fixed original baseline"),
        "resolve_tests": lambda *a: (["tests/test_target.py"], []),
        "collect_node_ids": lambda *a: (["tests/test_target.py::test_target"], 0, ""),
        "load_duration_history": lambda: {}, "update_duration_history": lambda *a: None,
        "os": SimpleNamespace(environ={}, name="posix", fsync=os.fsync, replace=os.replace),
        "subprocess": SimpleNamespace(check_output=lambda *a, **kw: "",
                                      Popen=launch_refused if fault == "launch" else Child,
                                      STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired),
    }.items():
        monkeypatch.setitem(ns, key, value)
    monkeypatch.setattr(sys, "argv", ["freeze_gate.py", "--baseline", str(baseline)])
    assert gate["main"]() != 0
    import json
    reports = list((tmp_path / "tmp/freeze_gate").glob("*.json"))
    assert len(reports) == 1
    result = json.loads(reports[0].read_text(encoding="utf8"))
    assert result["status"] == status
    assert result["status"] != "PASSED"
    if fault == "launch":
        error = result["pytest_launch_error"]
        assert error["type"] == "OSError"
        assert "WinError 206" in error["message"]
        assert result["node_manifest_count"] == 1, "the unexecuted selection stays identified"
        assert result["pytest_counts"] is None, "a launch failure is not a test run"
        assert result["source_aggregate_sha256"] == "initial"


def test_wall_clock_over_budget_cannot_be_a_success(tmp_path, monkeypatch):
    gate = load()
    ns = gate["write_report"].__globals__
    monkeypatch.setitem(ns, "time", SimpleNamespace(perf_counter=lambda: 301))
    report = {"status": "PASSED", "budget_seconds": 300}
    assert gate["write_report"](report, 0, 0, tmp_path / "report.json") == 1
    assert report["status"] == "INCOMPLETE_GATE_BUDGET_EXCEEDED"


def test_pytest_launch_command_is_bounded_and_preserves_the_selection(tmp_path):
    """Windows caps CreateProcess command lines at 32767 chars (WinError 206).

    The selection travels as a manifest file: the launch command must stay
    short for any selection size, and the manifest must round-trip the exact
    node list without reordering, dropping, or degrading to whole files.
    """
    gate = load()
    ids = [f"tests/storage/test_synthetic_{index:04d}.py::test_case_{index}[{index}-{'x' * 48}]"
           for index in range(500)]
    naive = subprocess.list2cmdline(
        [sys.executable, "-m", "pytest", "-q", *ids, "--tb=short", "--durations=0"])
    assert len(naive) > 32767  # per-node argv genuinely cannot start on Windows
    manifest = tmp_path / "selected.nodeids"
    gate["write_node_manifest"](ids, manifest)
    command = gate["build_pytest_command"](manifest)
    assert len(subprocess.list2cmdline(command)) < 4096
    assert [line for line in manifest.read_text(encoding="utf-8").splitlines() if line] == ids


def test_manifest_runner_executes_exactly_the_listed_nodes_and_propagates_exit_status(tmp_path):
    """Short command + manifest drives the same pytest selection end to end."""
    gate = load()
    runner = gate["ROOT"] / "scripts" / "freeze_gate_pytest_runner.py"
    assert runner.is_file(), "the bounded launcher script must exist"
    good = tmp_path / "good.nodeids"
    gate['write_node_manifest']([
        'tests/storage/test_freeze_gate_integrity.py::test_missing_default_baseline_blocks_before_test_discovery'], good)
    observed = tmp_path / 'observation.json'
    env = {**os.environ, 'FREEZE_GATE_OBSERVATION_PATH': str(observed),
           'FREEZE_GATE_INVOCATION_ID': 'real-one-node'}
    done = subprocess.run([sys.executable, str(runner), str(good), "--tb=short"],
                          cwd=gate["AGENTOS"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120, env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 passed" in done.stdout
    nodes = good.read_text().splitlines()
    evidence = json.loads(observed.read_text())
    profile = gate['complete_profile']('a' * 64, nodes, evidence,
        invocation_id='real-one-node', exit_code=done.returncode, timed_out=False, process_seconds=1.0)
    assert profile['nodeCount'] == profile['executedCount'] == profile['collectedCount'] == 1
    assert set(evidence['reports'][0]) >= {'nodeId', 'phase', 'durationSeconds', 'outcome'}
    bad = tmp_path / "bad.nodeids"
    bad.write_text("tests/storage/test_freeze_gate_integrity.py::definitely_not_a_test\n",
                   encoding="utf-8")
    failed = subprocess.run([sys.executable, str(runner), str(bad), "--tb=short"],
                            cwd=gate["AGENTOS"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120)
    assert failed.returncode != 0, failed.stdout + failed.stderr


def test_duration_history_preserves_maxima_and_records_last_observation(tmp_path, monkeypatch):
    """Legacy last stays archived, never refreshed or used as a profile."""
    gate = load()
    ns = gate["update_duration_history"].__globals__
    monkeypatch.setitem(ns, "ROOT", tmp_path)
    history_path = tmp_path / "tmp/freeze_gate/test_durations.json"
    history_path.parent.mkdir(parents=True)
    history_path.write_text(json.dumps({"tests/a.py::x": 5.0, "tests/b.py::y": 7.0,
        'legacy': {'max': 9.0, 'last': 8.0, 'note': 'retain'}}),
                            encoding="utf-8")
    gate["update_duration_history"]({"tests/a.py::x": 3.0, "tests/c.py::z": 2.0})
    stored = json.loads(history_path.read_text(encoding="utf-8"))
    assert stored["tests/a.py::x"] == 5.0
    assert stored["tests/b.py::y"] == 7.0, "untouched history is never erased"
    assert stored['legacy'] == {'max': 9.0, 'last': 8.0, 'note': 'retain'}
    assert stored["tests/c.py::z"] == 2.0
    gate['update_duration_history']({'tests/a.py::x': 8.0, 'legacy': 10.0})
    stored = json.loads(history_path.read_text())
    assert stored['tests/a.py::x'] == 8.0
    assert stored['legacy'] == {'max': 10.0, 'last': 8.0, 'note': 'retain'}
    loaded = gate["load_duration_history"]()
    assert loaded["tests/b.py::y"] == {"max": 7.0}


def _gate_harness(tmp_path, monkeypatch, gate, history, popen):
    ns = gate["main"].__globals__
    test_file = tmp_path / "tests/test_target.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_target(): pass\n", encoding="utf-8")
    (tmp_path / 'pytest.ini').write_text('[pytest]\n', encoding='utf-8')
    baseline = tmp_path / "accepted.json"
    baseline.write_bytes(gate["DEFAULT_BASELINE"].read_bytes())

    class Child:
        def __init__(self, command, **kwargs):
            kwargs["stdout"].write(b"1 passed in 0.01s\n")
            self.returncode = 0
            ids = Path(command[2]).read_text().splitlines()
            evidence = observation(gate, ids, invocation=kwargs['env']['FREEZE_GATE_INVOCATION_ID'])
            Path(kwargs['env']['FREEZE_GATE_OBSERVATION_PATH']).write_text(json.dumps(evidence))

        def wait(self, timeout=None):
            return 0

    for key, value in {
        "ROOT": tmp_path, "AGENTOS": test_file.parents[1],
        "source_snapshot": lambda: {"aggregate": "initial", "files": {"source": "hash"}},
        "external_snapshot": lambda: {}, "check_diff_whitespace": lambda: (0, ""),
        "changed_python_paths": lambda *a: (["source"], "fixed original baseline"),
        "resolve_tests": lambda *a: (["tests/test_target.py"], []),
        "collect_node_ids": lambda *a: (["tests/test_target.py::test_target"], 0, ""),
        "load_duration_history": lambda: history,
        "update_duration_history": lambda *a: None,
        "os": SimpleNamespace(environ={}, name="posix", fsync=os.fsync, replace=os.replace),
        "subprocess": SimpleNamespace(Popen=popen or Child, STDOUT=subprocess.STDOUT),
    }.items():
        monkeypatch.setitem(ns, key, value)
    monkeypatch.setattr(sys, "argv", ["freeze_gate.py", "--baseline", str(baseline)])


def test_stale_maxima_alone_do_not_block_launch(tmp_path, monkeypatch):
    """A fresh clone has no history and launches; a host whose maxima ratcheted
    past the budget from mixed runs must stay equivalent to that fresh clone."""
    gate = load()
    _gate_harness(tmp_path, monkeypatch, gate,
                  history={"tests/test_target.py::test_target": {"max": 999.0}}, popen=None)
    assert gate["main"]() == 0
    result = last_report(tmp_path)
    assert result["status"] == "PASSED"
    assert result["historical_max_duration_sum_seconds"] == 999.0
    assert result['duration_estimate']['status'] == 'UNKNOWN'
    assert result['duration_estimate']['seconds'] is None
    assert result['complete_profile_published']


def test_recent_over_budget_last_observations_block_before_launch(tmp_path, monkeypatch):
    """Fail-closed direction is unchanged: when the latest complete profile
    already exceeds the remaining budget, pytest is never started."""

    def refuse(*args, **kwargs):
        pytest.fail("pytest launched although the recent profile exceeded the budget")

    gate = load()
    _gate_harness(tmp_path, monkeypatch, gate,
                  history={"tests/test_target.py::test_target": {"max": 400.0, "last": 300.5}},
                  popen=refuse)
    ids = ['tests/test_target.py::test_target']
    source = gate['profile_source_sha256']({'aggregate': 'initial'}, {})
    profile = make_profile(gate, source, ids, seconds=300.5)
    gate['atomic_json'](gate['profile_path'](source, ids), profile)
    assert gate["main"]() != 0
    result = last_report(tmp_path)
    assert result["status"] == "BLOCKED_KNOWN_DURATION_OVER_BUDGET"
    assert result['duration_estimate']['seconds'] == 300.5
    assert "pytest_exit_code" not in result and result["pytest_command"] is None


def observation(gate, ids, *, invocation='observation', seconds=1.0):
    return dict(version=1, invocationId=invocation, manifestSha256=gate['manifest_sha256'](ids),
        collectedNodeIds=ids, sessionExitCode=0, processExitCode=0,
        reports=[dict(nodeId=node, phase=phase, outcome='passed', expectedFailure=False,
                      durationSeconds=seconds if phase == 'call' else 0.0)
                 for node in ids for phase in ('setup', 'call', 'teardown')])


def last_report(tmp_path):
    paths = [p for p in (tmp_path / 'tmp/freeze_gate').glob('20*.json')
             if not p.name.endswith('.observation.json')]
    return json.loads(sorted(paths)[-1].read_text(encoding='utf-8'))


def make_profile(gate, source, ids, *, seconds=1.0):
    return gate['complete_profile'](source, ids, observation(gate, ids, seconds=seconds),
        invocation_id='observation', exit_code=0, timed_out=False, process_seconds=seconds)


def test_profiles_never_splice_last_values_from_different_runs(tmp_path, monkeypatch):
    gate = load()
    monkeypatch.setitem(gate['main'].__globals__, 'ROOT', tmp_path)
    history = tmp_path / 'tmp/freeze_gate/test_durations.json'
    history.parent.mkdir(parents=True)
    ids = ['tests/a.py::a', 'tests/b.py::b']
    history.write_text(json.dumps({ids[0]: {'max': 200, 'last': 1},
                                   ids[1]: {'max': 200, 'last': 200}}))
    before = history.read_bytes()
    estimate = gate['load_complete_estimate']('a' * 64, ids)
    assert estimate['status'] == 'UNKNOWN' and estimate['seconds'] is None
    assert history.read_bytes() == before
    # An exact whole observation, rather than the fictional 1+200 mixture.
    profile = make_profile(gate, 'a' * 64, ids, seconds=2.0)
    gate['atomic_json'](gate['profile_path']('a' * 64, ids), profile)
    assert gate['load_complete_estimate']('a' * 64, ids)['seconds'] == 4.0


@pytest.mark.parametrize('damage', ['partial', 'missing_phase', 'collection', 'duplicate',
                                   'foreign', 'nan', 'negative', 'skip', 'invocation', 'exit'])
def test_incomplete_observations_cannot_form_profiles(damage):
    gate = load()
    ids = ['tests/a.py::a', 'tests/b.py::b']
    data = observation(gate, ids)
    if damage == 'partial':
        data['reports'] = data['reports'][:3]
    elif damage == 'missing_phase':
        data['reports'].pop()
    elif damage == 'collection':
        data['collectedNodeIds'] = ids[:1]
    elif damage == 'duplicate':
        data['reports'].append(dict(data['reports'][0]))
    elif damage == 'foreign':
        data['reports'][0]['nodeId'] = 'tests/other.py::x'
    elif damage == 'nan':
        data['reports'][0]['durationSeconds'] = float('nan')
    elif damage == 'negative':
        data['reports'][0]['durationSeconds'] = -1.0
    elif damage == 'skip':
        data['reports'][0]['outcome'] = 'skipped'
    elif damage == 'invocation':
        data['invocationId'] = 'previous-process'
    else:
        data['sessionExitCode'] = 1
    with pytest.raises(ValueError):
        gate['complete_profile']('a' * 64, ids, data, invocation_id='observation',
            exit_code=0, timed_out=False, process_seconds=1.0)


@pytest.mark.parametrize('change', ['source', 'manifest', 'count', 'mapping'])
def test_profile_mismatch_is_explicitly_unknown(tmp_path, monkeypatch, change):
    gate = load()
    monkeypatch.setitem(gate['main'].__globals__, 'ROOT', tmp_path)
    ids, source = ['tests/a.py::a'], 'a' * 64
    profile = make_profile(gate, source, ids)
    gate['atomic_json'](gate['profile_path'](source, ids), profile)
    if change == 'source':
        estimate = gate['load_complete_estimate']('b' * 64, ids)
    elif change == 'manifest':
        estimate = gate['load_complete_estimate'](source, ['tests/b.py::b'])
    else:
        if change == 'count':
            profile['nodeCount'] = 2
        else:
            profile['nodeDurationsSeconds'] = {}
        gate['atomic_json'](gate['profile_path'](source, ids), profile)
        estimate = gate['load_complete_estimate'](source, ids)
    assert estimate['status'] == 'UNKNOWN' and estimate['seconds'] is None


@pytest.mark.parametrize('fault', ['timeout', 'launch', 'failed', 'partial', 'source', 'late_source', 'manifest', 'budget'])
def test_failed_or_incomplete_run_preserves_existing_complete_profile(tmp_path, monkeypatch, fault):
    gate = load()
    ids = ['tests/test_target.py::test_target']
    source = gate['profile_source_sha256']({'aggregate': 'initial'}, {})

    class Child:
        returncode = 1 if fault == 'failed' else 0
        def __init__(self, command, **kwargs):
            kwargs['stdout'].write(b'1 passed in 0.01s\n')
            data = observation(gate, ids, invocation=kwargs['env']['FREEZE_GATE_INVOCATION_ID'])
            if fault == 'partial':
                data['reports'].pop()
            Path(kwargs['env']['FREEZE_GATE_OBSERVATION_PATH']).write_text(json.dumps(data))
            if fault == 'manifest':
                Path(command[2]).write_text('tests/other.py::changed\n')
        def wait(self, timeout=None):
            if timeout is not None and fault == 'timeout':
                raise subprocess.TimeoutExpired('pytest', timeout)
            return self.returncode
        def kill(self):
            pass

    def launch(command, **kwargs):
        if fault == 'launch':
            raise OSError('injected startup refusal')
        return Child(command, **kwargs)

    _gate_harness(tmp_path, monkeypatch, gate, history={}, popen=launch)
    monkeypatch.setitem(gate['main'].__globals__['subprocess'].__dict__, 'TimeoutExpired', subprocess.TimeoutExpired)
    if fault in {'source', 'late_source'}:
        captures = iter(('initial', 'drifted') if fault == 'source' else ('initial', 'initial', 'drifted'))
        monkeypatch.setitem(gate['main'].__globals__, 'source_snapshot',
            lambda: {'aggregate': next(captures), 'files': {}})
    profile = make_profile(gate, source, ids)
    path = gate['profile_path'](source, ids)
    gate['atomic_json'](path, profile)
    previous = path.read_bytes()
    if fault == 'budget':
        # The process can finish, yet the overall gate budget can expire before
        # publication; write_report must refuse to refresh its complete profile.
        ns = gate['main'].__globals__
        real = ns['write_report']
        def expired(report, started, code, target=None, **kwargs):
            return real(report, started - 301, code, target, **kwargs)
        monkeypatch.setitem(ns, 'write_report', expired)
    assert gate['main']() != 0
    assert path.read_bytes() == previous


def test_atomic_publication_failure_keeps_previous_profile(tmp_path, monkeypatch):
    gate = load()
    path = tmp_path / 'profile.json'
    path.write_bytes(b'original-complete-profile')
    monkeypatch.setattr(os, 'replace', lambda *a: (_ for _ in ()).throw(OSError('disk failure')))
    with pytest.raises(OSError):
        gate['atomic_json'](path, {'new': 'profile'})
    assert path.read_bytes() == b'original-complete-profile'
    assert list(tmp_path.iterdir()) == [path]


def test_full_profile_sums_all_phases_and_accounts_for_process_overhead():
    gate = load()
    ids = ['tests/a.py::a', 'tests/b.py::b']
    data = observation(gate, ids)
    for report, seconds in zip(data['reports'], [.1, 1.2, .3, .4, .5, .6]):
        report['durationSeconds'] = seconds
    profile = gate['complete_profile']('a' * 64, ids, data, invocation_id='observation',
        exit_code=0, timed_out=False, process_seconds=4.5)
    assert profile['nodeDurationsSeconds'][ids[0]] == pytest.approx(1.6)
    assert profile['nodeDurationsSeconds'][ids[1]] == pytest.approx(1.5)
    assert profile['testDurationSumSeconds'] == pytest.approx(3.1)
    assert profile['estimateSeconds'] == 4.5


def test_real_one_node_gate_publishes_and_reuses_matching_complete_profile(tmp_path, monkeypatch):
    gate = load()
    _gate_harness(tmp_path, monkeypatch, gate, history={}, popen=subprocess.Popen)
    ns = gate['main'].__globals__
    ns['os'].environ = dict(os.environ)
    ns['subprocess'].TimeoutExpired = subprocess.TimeoutExpired
    assert gate['main']() == 0
    ids = ['tests/test_target.py::test_target']
    source = gate['profile_source_sha256']({'aggregate': 'initial'}, {})
    profile = json.loads(gate['profile_path'](source, ids).read_text())
    assert profile['collectedCount'] == profile['executedCount'] == profile['nodeCount'] == 1
    assert gate['load_complete_estimate'](source, ids)['status'] == 'KNOWN'
    # Re-running this isolated fixture, not the real gate selection, consumes
    # the same matching complete profile and replaces it as one whole record.
    assert gate['main']() == 0
    report = last_report(tmp_path)
    assert report['duration_estimate']['status'] == 'KNOWN'


def test_cache_lock_refuses_concurrent_writer_and_releases_on_exception(tmp_path, monkeypatch):
    gate = load()
    monkeypatch.setitem(gate['main'].__globals__, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='injected'):
        with gate['duration_cache_lock']():
            with pytest.raises(OSError):
                with gate['duration_cache_lock']():
                    pytest.fail('concurrent writer acquired the cache lock')
            raise RuntimeError('injected')
    with gate['duration_cache_lock']():
        pass


def test_expired_publication_deadline_keeps_previous_complete_profile(tmp_path, monkeypatch):
    gate = load()
    path = tmp_path / 'profile.json'
    path.write_bytes(b'previous')
    monkeypatch.setitem(gate['atomic_json'].__globals__, 'time', SimpleNamespace(perf_counter=lambda: 301))
    with pytest.raises(TimeoutError):
        gate['atomic_json'](path, {'new': 'profile'}, deadline=300)
    assert path.read_bytes() == b'previous'
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('stage', ['history', 'profile_before', 'profile_after', 'report_before', 'report_after'])
@pytest.mark.parametrize('existing', [False, True])
def test_budget_expiry_during_persistence_never_commits_success(tmp_path, monkeypatch, stage, existing):
    gate = load()
    _gate_harness(tmp_path, monkeypatch, gate, history={}, popen=None)
    ns = gate['main'].__globals__
    clock = [0.0]
    ns['time'] = SimpleNamespace(perf_counter=lambda: clock[0])
    ids = ['tests/test_target.py::test_target']
    source = gate['profile_source_sha256']({'aggregate': 'initial'}, {})
    path = gate['profile_path'](source, ids)
    if existing:
        gate['atomic_json'](path, make_profile(gate, source, ids, seconds=2))
    previous = path.read_bytes() if existing else None
    real = ns['atomic_json']
    if stage == 'history':
        ns['update_duration_history'] = lambda *a: clock.__setitem__(0, 301.0)

    def injected(target, value, **kwargs):
        profile = target == path
        report = target.parent == tmp_path / 'tmp/freeze_gate' and target.suffix == '.json'
        trigger = (profile and stage.startswith('profile')) or (report and stage.startswith('report'))
        if trigger and stage.endswith('before'):
            clock[0] = 301.0
        result = real(target, value, **kwargs)
        if trigger and stage.endswith('after'):
            clock[0] = 301.0
        return result
    ns['atomic_json'] = injected
    assert gate['main']() == 1
    result = last_report(tmp_path)
    assert result['status'] == 'INCOMPLETE_GATE_BUDGET_EXCEEDED'
    assert result['elapsed_seconds'] == 301.0
    assert result['finished_utc']
    assert result['complete_profile_published'] is None
    assert (path.read_bytes() if path.exists() else None) == previous
    assert gate['load_complete_estimate'](source, ids)['status'] == ('KNOWN' if existing else 'UNKNOWN')


def test_same_second_concurrent_runs_isolate_every_execution_artifact(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import datetime
    barrier = Barrier(2)
    gates = [load(), load()]
    class FrozenDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 26, tzinfo=datetime.timezone.utc)
    for gate in gates:
        _gate_harness(tmp_path, monkeypatch, gate, history={}, popen=None)
        ns = gate['main'].__globals__
        ns['dt'] = SimpleNamespace(datetime=FrozenDateTime, timezone=datetime.timezone)
        collect = ns['collect_node_ids']
        def synchronized(*args, collect=collect):
            barrier.wait(timeout=10)
            return collect(*args)
        ns['collect_node_ids'] = synchronized
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda g: g['main'](), gates))
    assert all(code in (0, 1) for code in codes)  # publisher contention may fail closed
    folder = tmp_path / 'tmp/freeze_gate'
    reports = [json.loads(p.read_text()) for p in folder.glob('2026*.json')
               if not p.name.endswith('.observation.json')]
    assert len(reports) == 2
    assert len({r['invocation_id'] for r in reports}) == 2
    assert len({r['artifact_id'] for r in reports}) == 2
    for suffix in ('.log', '.json', '.nodeids', '.observation.json'):
        paths = [folder / (r['artifact_id'] + suffix) for r in reports]
        assert len(set(paths)) == 2 and all(p.is_file() for p in paths)
    for r in reports:
        data = json.loads((tmp_path / r['observation_path']).read_text())
        assert data['invocationId'] == r['invocation_id']
        assert (tmp_path / r['node_manifest_path']).read_text().splitlines() == r['collected_test_node_ids']
        assert '1 passed' in (tmp_path / r['log_path']).read_text()
        other = next(x for x in reports if x is not r)
        with pytest.raises(ValueError, match='INVALID_EXECUTION_OBSERVATION'):
            gates[0]['complete_profile'](r['profile_source_sha256'], r['collected_test_node_ids'], data,
                invocation_id=other['invocation_id'], exit_code=0, timed_out=False, process_seconds=1)


def test_success_timestamps_include_cache_finalization(tmp_path, monkeypatch):
    gate = load()
    _gate_harness(tmp_path, monkeypatch, gate, history={}, popen=None)
    ns = gate['main'].__globals__
    clock = [0.0]
    ns['time'] = SimpleNamespace(perf_counter=lambda: clock[0])
    ns['utc_now'] = lambda: 'clock-' + str(clock[0])
    ns['update_duration_history'] = lambda *a: clock.__setitem__(0, 12.5)
    assert gate['main']() == 0
    result = last_report(tmp_path)
    assert result['status'] == 'PASSED'
    assert result['finished_utc'] == 'clock-12.5'
    assert result['elapsed_seconds'] == 12.5
    assert result['complete_profile_published']


def test_profile_reader_never_observes_unconfirmed_publication(tmp_path, monkeypatch):
    gate = load()
    monkeypatch.setitem(gate['main'].__globals__, 'ROOT', tmp_path)
    ids = ['tests/a.py::a']
    gate['atomic_json'](gate['profile_path']('a' * 64, ids), make_profile(gate, 'a' * 64, ids))
    with gate['duration_cache_lock']():
        estimate = gate['load_complete_estimate']('a' * 64, ids)
        assert estimate == dict(status='UNKNOWN', reason='PROFILE_READ_LOCK_UNAVAILABLE', seconds=None)
    assert gate['load_complete_estimate']('a' * 64, ids)['status'] == 'KNOWN'
