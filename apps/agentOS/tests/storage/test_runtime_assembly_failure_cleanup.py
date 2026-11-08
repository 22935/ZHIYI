"""Failed production assembly must release the instance lock and resources.

Every case drives the real composition root (build_default_runtime) on
temporary databases. No implicit C2 schema DDL, no fake lock release, and
the original assembly error always survives the cleanup.
"""
from contextlib import closing
import asyncio
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from support.stores import c2_schema_upgrade as ops


ROOT = Path(__file__).resolve().parents[4]

ENV_KEYS = ("AGENTOS_WORKFLOW_DB_PATH", "AGENTOS_LANGGRAPH_CHECKPOINT_DB", "AGENTOS_EXECUTION_VALUE_DB",
            "AGENTOS_CONTENT_MANIFEST_DB", "AGENTOS_EXECUTION_MEMORY_DB", "AGENTOS_PROVENANCE_DB",
            "AGENTOS_AUDIT_DB", "AGENTOS_RESOURCE_DB", "AGENTOS_NODE_DB", "AGENTOS_AGENT_DB",
            "AGENTOS_RESOURCE_HEALTH_DB", "AGENTOS_EVOLUTION_DB", "AGENTOS_IDENTITY_DB")

AUTHORITY_ENABLE_STEPS = (
    "enable_planning_commit",
    "enable_graph_materialization",
    "enable_graph_activation",
    "enable_graph_handoff",
    "enable_execution_permit",
)


class ScopedTools:
    def scoped(self, allowed_tools):
        return self


@pytest.fixture(autouse=True)
def _app_composition_on_path(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / "apps" / "agent"))
    monkeypatch.setenv("AGENTOS_COMMUNICATION_DB", str(tmp_path / "communication.sqlite"))
    from app.execution import instance_lock
    yield
    if instance_lock._LOCK_HANDLE is not None:
        instance_lock.release_workflow_instance_lock()


def role_paths(folder):
    return {
        "workflow": folder / "workflow.sqlite",
        "checkpoint": folder / "checkpoint.sqlite",
        "identity": folder / "identity.sqlite",
    }


def initialize_trio(folder):
    trio = role_paths(folder)
    for role, path in trio.items():
        ops._initialize(role, path)
    return trio


def assembly_env(folder, *, semantic, c2, trio=None):
    env = {key: str(folder / f"{key}.sqlite") for key in ENV_KEYS}
    if trio is not None:
        env["AGENTOS_WORKFLOW_DB_PATH"] = str(trio["workflow"])
        env["AGENTOS_LANGGRAPH_CHECKPOINT_DB"] = str(trio["checkpoint"])
        env["AGENTOS_IDENTITY_DB"] = str(trio["identity"])
    env["AGENTOS_MISSION_SEMANTIC_CONVERGENCE"] = "true" if semantic else "false"
    env["AGENTOS_C2_EXECUTION_AUTHORITIES"] = "true" if c2 else "false"
    return env


def build(env):
    from app.execution.wiring import build_default_runtime
    return build_default_runtime(environment=env, tool_runtime=ScopedTools(),
                                 model_runtime=object(), intent_llm=object())


def lock_held():
    from app.execution import instance_lock
    return instance_lock._LOCK_HANDLE is not None


def spy_identity_close(monkeypatch):
    from runtime.runner import AcgIdentityLifecycleService
    calls = []
    original = AcgIdentityLifecycleService.close

    def recording_close(self):
        calls.append(self)
        original(self)

    monkeypatch.setattr(AcgIdentityLifecycleService, "close", recording_close)
    return calls


def sql(path, statement, parameters=()):
    with closing(sqlite3.connect(path)) as conn, conn:
        return conn.execute(statement, parameters).fetchall()


def dump(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        return tuple(conn.iterdump())


def test_invalid_switch_combination_fails_before_lock_and_resources(tmp_path, monkeypatch):
    """C2 without semantic convergence refuses before the lock or any file."""
    from app.execution import wiring

    def forbidden(*args, **kwargs):
        pytest.fail("invalid switch combination must fail before acquiring the lock")

    monkeypatch.setattr(wiring, "acquire_workflow_instance_lock", forbidden)
    with pytest.raises(RuntimeError, match="AGENTOS_MISSION_SEMANTIC_CONVERGENCE"):
        build(assembly_env(tmp_path, semantic=False, c2=True))
    assert not lock_held()
    assert list(tmp_path.iterdir()) == []


def test_pre_runtime_failure_releases_lock_and_closes_owned_resources(tmp_path, monkeypatch):
    """A verify failure before the Runtime exists still cleans lock and stores."""
    calls = spy_identity_close(monkeypatch)
    # semantic=True on a database without even the S00-01 tables: the
    # workflow store refuses during composition, before ExecutionRuntime.
    with pytest.raises(RuntimeError, match="upgraded explicitly"):
        build(assembly_env(tmp_path, semantic=True, c2=False))
    assert not lock_held()
    assert len(calls) == 1, "the pre-Runtime identity connection must be closed"
    # The lock is truly free again: a fresh acquisition for the same database
    # succeeds and observes its own pid.
    from app.execution.instance_lock import acquire_workflow_instance_lock, release_workflow_instance_lock
    handle = acquire_workflow_instance_lock(str(tmp_path / "workflow.sqlite"))
    try:
        handle.seek(0)
        assert handle.read().strip() == f"pid={os.getpid()}"
    finally:
        release_workflow_instance_lock()


def test_missing_c2_schema_failure_cleans_lock_and_runtime_resources(tmp_path, monkeypatch):
    """Verify-only refusal must clean the already-constructed Runtime."""
    calls = spy_identity_close(monkeypatch)
    trio = initialize_trio(tmp_path)  # S00-01 only; C2 ledgers deliberately absent.
    with pytest.raises((sqlite3.OperationalError, RuntimeError), match="no such table|explicit upgrade"):
        build(assembly_env(tmp_path, semantic=True, c2=True, trio=trio))
    assert not lock_held()
    assert len(calls) == 1, "the Runtime-owned identity connection must be closed"


@pytest.mark.parametrize("step", AUTHORITY_ENABLE_STEPS)
def test_partial_authority_assembly_failure_cleans_up(tmp_path, monkeypatch, step):
    """Any authority assembly step failing leaves neither lock nor resources."""
    calls = spy_identity_close(monkeypatch)
    trio = initialize_trio(tmp_path)
    assert ops.upgrade_databases(**trio)["status"] == "READY"
    from runtime.workflow_runtime import ExecutionRuntime

    captured = {}

    def bomb(self, *args, **kwargs):
        captured["runtime"] = self
        raise RuntimeError(f"injected assembly fault: {step}")

    monkeypatch.setattr(ExecutionRuntime, step, bomb)
    with pytest.raises(RuntimeError, match=f"injected assembly fault: {step}"):
        build(assembly_env(tmp_path, semantic=True, c2=True, trio=trio))
    assert not lock_held()
    assert len(calls) == 1, "failed assembly must close the Runtime's resources"
    assert captured["runtime"].identity_lifecycle is not None


def test_cleanup_failure_does_not_mask_original_assembly_error(tmp_path, monkeypatch):
    """A close() that itself fails can never replace the assembly error."""
    services = spy_identity_close(monkeypatch)
    trio = initialize_trio(tmp_path)
    assert ops.upgrade_databases(**trio)["status"] == "READY"
    from storage.v2.sqlite import SQLiteV2Storage

    def boom(self):
        raise RuntimeError("cleanup close exploded")

    monkeypatch.setattr(SQLiteV2Storage, "close", boom)
    from runtime.workflow_runtime import ExecutionRuntime

    def bomb(self, *args, **kwargs):
        raise RuntimeError("original assembly fault")

    monkeypatch.setattr(ExecutionRuntime, "enable_graph_activation", bomb)
    with pytest.raises(RuntimeError, match="original assembly fault"):
        build(assembly_env(tmp_path, semantic=True, c2=True, trio=trio))
    assert not lock_held()
    # Restore the real close and release the deliberately leaked identity
    # connection so later tests and tmp_path cleanup stay clean.
    monkeypatch.undo()
    for service in services:
        service.close()


def test_retry_in_same_process_reacquires_the_target_database_lock(tmp_path):
    """After a failed build the next build guards its own database."""
    folder_fail = tmp_path / "fail"
    folder_other = tmp_path / "other"
    # Fail once on a missing C2 schema.
    trio = initialize_trio(folder_fail)
    with pytest.raises((sqlite3.OperationalError, RuntimeError)):
        build(assembly_env(folder_fail, semantic=True, c2=True, trio=trio))
    assert not lock_held()

    # A different database builds legally and is guarded by ITS OWN lock file.
    from app.execution import instance_lock
    from app.execution.wiring import close_runtime
    runtime = build(assembly_env(folder_other, semantic=False, c2=False))
    try:
        assert Path(instance_lock._LOCK_HANDLE.name).resolve() == (
            folder_other.resolve() / "runtime.instance.lock"
        )
    finally:
        close_runtime(runtime)
    assert not lock_held()

    # Retrying the original folder (schema now installed) reacquires its lock.
    assert ops.upgrade_databases(**trio)["status"] == "READY"
    runtime = build(assembly_env(folder_fail, semantic=True, c2=True, trio=trio))
    try:
        assert Path(instance_lock._LOCK_HANDLE.name).resolve() == (
            folder_fail.resolve() / "runtime.instance.lock"
        )
        for attribute in ("planning_commit_authority", "graph_materialization_authority",
                          "graph_activation_authority", "graph_handoff_authority",
                          "execution_permit_authority"):
            assert getattr(runtime, attribute) is not None
    finally:
        close_runtime(runtime)
    assert not lock_held()


def test_legal_configuration_assembles_closes_and_rebuilds(tmp_path):
    """The success path is unchanged and shutdown is repeatable."""
    trio = initialize_trio(tmp_path)
    assert ops.upgrade_databases(**trio)["status"] == "READY"
    from app.execution.wiring import close_runtime

    runtime = build(assembly_env(tmp_path, semantic=True, c2=True, trio=trio))
    try:
        assert runtime.mission_semantic_service is not None
        assert runtime.execution_permit_authority is not None
        assert runtime.graph_handoff_authority.staged_store is not None
    finally:
        close_runtime(runtime)
        close_runtime(runtime)  # repeated shutdown stays idempotent
    assert not lock_held()

    runtime = build(assembly_env(tmp_path, semantic=True, c2=True, trio=trio))
    close_runtime(runtime)
    assert not lock_held()


@pytest.mark.parametrize("fault", ["missing_schema", "injected_step"])
def test_failure_paths_write_no_c2_ddl(tmp_path, monkeypatch, fault):
    """Refused assembly never upgrades the databases implicitly."""
    trio = initialize_trio(tmp_path)
    if fault == "injected_step":
        assert ops.upgrade_databases(**trio)["status"] == "READY"
        from runtime.workflow_runtime import ExecutionRuntime

        def bomb(self, *args, **kwargs):
            raise RuntimeError("injected assembly fault")

        monkeypatch.setattr(ExecutionRuntime, "enable_execution_permit", bomb)
        workflow_before = dump(trio["workflow"])
        checkpoint_before = dump(trio["checkpoint"])
    with pytest.raises((sqlite3.OperationalError, RuntimeError), match="no such table|injected"):
        build(assembly_env(tmp_path, semantic=True, c2=True, trio=trio))
    if fault == "missing_schema":
        # Nothing was ever upgraded: assembly must leave the databases bare.
        assert not set(name for name, in sql(trio["workflow"], "SELECT name FROM sqlite_master")) & ops.C2_TABLES
        assert sql(trio["checkpoint"], "SELECT name FROM sqlite_master WHERE name='staged_graph_checkpoints'") == []
    else:
        # Full DDL upgrade had happened beforehand; a failed assembly must not
        # alter any row of it.
        assert dump(trio["workflow"]) == workflow_before
        assert dump(trio["checkpoint"]) == checkpoint_before


def take_os_lock(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize("unlock_fails", [False, True])
def test_adversarial_close_failure_never_allows_runtime_bypass(tmp_path, monkeypatch, unlock_fails):
    from app.execution import instance_lock as locks
    real = locks.acquire_workflow_instance_lock(str(tmp_path / "workflow.sqlite"))

    class BadClose:
        def __getattr__(self, name):
            return getattr(real, name)
        def close(self):
            raise OSError("injected close failure")

    locks._LOCK_HANDLE = BadClose()
    original_unlock = locks._unlock
    if unlock_fails:
        monkeypatch.setattr(locks, "_unlock", lambda h: (_ for _ in ()).throw(OSError("unlock failure")))
    try:
        with pytest.raises(OSError):
            locks.release_workflow_instance_lock()
        with open(real.name, "r+") as contender:
            if unlock_fails:
                with pytest.raises(OSError):
                    take_os_lock(contender)
            else:
                take_os_lock(contender)  # Explicit unlock really freed the OS lock.
            with pytest.raises(RuntimeError, match="uncertain|invalid"):
                build(assembly_env(tmp_path, semantic=False, c2=False))
    finally:
        monkeypatch.setattr(locks, "_unlock", original_unlock)
        locks._LOCK_HANDLE = real
        locks.release_workflow_instance_lock()


def test_adversarial_same_directory_different_database_is_rejected(tmp_path):
    from app.execution import instance_lock as locks
    locks.acquire_workflow_instance_lock(str(tmp_path / "one.sqlite"))
    with pytest.raises(RuntimeError, match="different workflow database"):
        locks.acquire_workflow_instance_lock(str(tmp_path / "two.sqlite"))


@pytest.mark.parametrize("stage", ["SQLiteNodeStore", "ResourcePlane", "SQLiteMemoryStore", "ExecutionRuntime"])
def test_adversarial_partial_construction_closes_actual_connections(tmp_path, monkeypatch, stage):
    from app.execution import wiring
    captured = []
    for name in ("SQLiteResourceStore", "SQLiteNodeStore", "SQLiteResourceHealthStore",
                 "SQLiteContentManifestStore", "ACGCheckpointStore", "SQLiteExecutionValueStore",
                 "SQLiteEvolutionStore", "SQLiteProvenanceStore", "SQLiteDecisionStore"):
        constructor = getattr(wiring, name)
        def record(*args, _constructor=constructor, **kwargs):
            value = _constructor(*args, **kwargs)
            captured.append(value)
            return value
        monkeypatch.setattr(wiring, name, record)
    original = getattr(wiring, stage)
    if stage == "ExecutionRuntime":
        import runtime.workflow_runtime as runtime_module
        def fail_inside_constructor(*args, **kwargs):
            raise RuntimeError("injected middle of ExecutionRuntime constructor")
        monkeypatch.setattr(runtime_module, "RuntimeBindingService", fail_inside_constructor)
    def bomb(*args, **kwargs):
        if stage == "ExecutionRuntime":
            # Real constructor has created ports and installed store references.
            return original(*args, **kwargs)
        raise RuntimeError("injected constructor fault")
    monkeypatch.setattr(wiring, stage, bomb)
    with pytest.raises((ValueError, RuntimeError)):
        build(assembly_env(tmp_path, semantic=False, c2=False))
    try:
        assert not lock_held()
        assert captured
        for resource in captured:
            connection = getattr(resource, "_connection", None)
            if connection is not None:
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    connection.execute("SELECT 1")
    finally:
        for resource in captured:
            resource.close()
    monkeypatch.undo()
    from app.execution.wiring import close_runtime
    runtime = build(assembly_env(tmp_path, semantic=False, c2=False))
    close_runtime(runtime)


@pytest.mark.parametrize("failure", [False, True])
def test_adversarial_local_transport_client_closed_on_shutdown_and_failure(tmp_path, monkeypatch, failure):
    from app.execution import wiring
    transports = []
    original = wiring.HttpLocalRuntimeTransport
    def record(**kwargs):
        transport = original(**kwargs)
        transports.append(transport)
        return transport
    monkeypatch.setattr(wiring, "HttpLocalRuntimeTransport", record)
    env = assembly_env(tmp_path, semantic=False, c2=False)
    env["AGENTOS_LOCAL_RUNTIME_ENDPOINT"] = "http://127.0.0.1:12345/v1/executions"
    if failure:
        def bomb(**kwargs):
            raise RuntimeError("late assembly failure")
        monkeypatch.setattr(wiring, "register_native_runtime", bomb)
        with pytest.raises(RuntimeError, match="late assembly failure"):
            build(env)
    else:
        runtime = build(env)
        wiring.close_runtime(runtime)
    try:
        assert len(transports) == 1
        assert transports[0]._client.is_closed
        assert not lock_held()
    finally:
        wiring._run_coroutine_sync(transports[0].aclose)


def test_adversarial_cleanup_continues_after_one_close_fails(tmp_path, monkeypatch):
    from app.execution import wiring
    runtime = build(assembly_env(tmp_path, semantic=False, c2=False))
    original = runtime.decision_store.close
    def bad_close():
        raise RuntimeError("one close failed")
    monkeypatch.setattr(runtime.decision_store, "close", bad_close)
    try:
        with pytest.raises(RuntimeError, match="one close failed"):
            wiring.close_runtime(runtime)
        assert not lock_held()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            runtime.checkpoint_store._connection.execute("SELECT 1")
    finally:
        original()


def test_adversarial_async_shutdown_closes_transport_in_owning_loop(tmp_path):
    import asyncio
    import httpx
    from app.execution import wiring
    runtime = build(assembly_env(tmp_path, semantic=False, c2=False))
    async def exercise():
        loop = asyncio.get_running_loop()
        transport = wiring.HttpLocalRuntimeTransport(resource_id="test", address="http://localhost:12345",
                                                     credential_provider=runtime.resource_plane)
        original = transport.aclose
        closed = []
        async def checked_close():
            assert asyncio.get_running_loop() is loop
            await original()
            closed.append(True)
        transport.aclose = checked_close
        runtime.local_runtime_transport = transport
        await wiring.aclose_runtime(runtime)
        assert closed == [True]
        assert transport._client.is_closed
        # Injected clients belong to their caller, not the transport.
        async with httpx.AsyncClient() as borrowed:
            transport = wiring.HttpLocalRuntimeTransport(resource_id="test", address="http://localhost:12345",
                                                         credential_provider=runtime.resource_plane, client=borrowed)
            await transport.aclose()
            assert not borrowed.is_closed
    asyncio.run(exercise())
    assert not lock_held()


def test_application_lifespan_awaits_runtime_shutdown_without_importing_application():
    """Inspect lifecycle wiring without importing main (which opens business DBs)."""
    import ast
    main_tree = ast.parse((ROOT / "apps/agent/app/main.py").read_text(encoding="utf8"))
    wiring_calls = [node for node in ast.walk(main_tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "build_lifespan"]
    assert len(wiring_calls) == 1
    injected = {kw.arg for kw in wiring_calls[0].keywords}
    assert {"runtime", "model_setup", "coordinator", "settings"} <= injected
    assert not any(isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan"
                   for node in ast.walk(main_tree)), "the cleanup contract lives in app.lifespan"

    source = (ROOT / "apps/agent/app/lifespan.py").read_text(encoding="utf8")
    tree = ast.parse(source)
    # The default seam awaits the real asynchronous runtime closer.
    assert "await aclose_runtime(target)" in source
    # Both the failure paths and the shutdown path schedule the runtime close,
    # exactly twice as before the extraction.
    assert source.count("lambda: runtime_close(runtime)") == 2
    # run_cleanups awaits every scheduled step even after earlier failures.
    cleanups = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "run_cleanups")
    assert any(isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name) and node.value.func.id == "step"
               for node in ast.walk(cleanups))


def c2_runtime_with_transport(folder, *, credential_key=None):
    trio = initialize_trio(folder)
    assert ops.upgrade_databases(**trio)["status"] == "READY"
    env = assembly_env(folder, semantic=True, c2=True, trio=trio)
    env["AGENTOS_LOCAL_RUNTIME_ENDPOINT"] = "http://127.0.0.1:12345/v1/executions"
    if credential_key is not None:
        env["AGENTOS_RESOURCE_CREDENTIAL_KEY"] = credential_key
    return build(env)


@pytest.mark.freeze_gate
@pytest.mark.parametrize("startup_failure", [False, True])
def test_real_lifespan_cancelled_runtime_close_releases_resources(tmp_path, startup_failure, caplog):
    """P1-01: actual Task.cancel at the default closer's transport await."""
    from app.execution import wiring, instance_lock
    from app.lifespan import build_lifespan

    async def exercise():
        runtime = c2_runtime_with_transport(tmp_path)
        transport = runtime.local_runtime_transport
        original_close = transport.aclose
        old_handle = instance_lock._LOCK_HANDLE
        entered = asyncio.Event()
        original_error = RuntimeError("original startup failure")

        async def blocked_close():
            entered.set()
            await asyncio.Event().wait()

        async def start():
            if startup_failure:
                raise original_error

        async def noop(*args):
            pass

        transport.aclose = blocked_close
        lifespan = build_lifespan(runtime=runtime,
            model_setup=SimpleNamespace(start=start, close=noop),
            coordinator=SimpleNamespace(startup=noop, shutdown=noop),
            settings=SimpleNamespace(ENVIRONMENT="development"),
            tool_warmup=None, bind_planner=None, provider_store_close=noop)

        async def drive():
            async with lifespan(None):
                pass

        task = asyncio.create_task(drive())
        try:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            with pytest.raises(RuntimeError if startup_failure else asyncio.CancelledError) as caught:
                await asyncio.wait_for(task, 5)
            if startup_failure:
                assert caught.value is original_error
            assert not lock_held() and not instance_lock._LOCK_VALID
            assert old_handle.closed
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                runtime.checkpoint_store._connection.execute("SELECT 1")
            # Interrupted clients remain incomplete: no silent retry or false success.
            assert not transport._client.is_closed
            assert "resource may remain open" in caplog.text
            fresh = instance_lock.acquire_workflow_instance_lock(str(role_paths(tmp_path)["workflow"]))
            assert fresh is not old_handle
            instance_lock.release_workflow_instance_lock()
        finally:
            transport.aclose = original_close
            await wiring.aclose_runtime(runtime)  # Explicit retry closes the interrupted client.
        assert transport._client.is_closed
    asyncio.run(exercise())


@pytest.mark.freeze_gate
@pytest.mark.parametrize("release_failure", [False, True])
def test_repeated_runtime_close_cancellation_with_errors_is_fail_closed(tmp_path, monkeypatch, release_failure, caplog):
    from app.execution import wiring, instance_lock

    async def exercise():
        runtime = c2_runtime_with_transport(tmp_path)
        transport = runtime.local_runtime_transport
        entered = [asyncio.Event(), asyncio.Event()]
        failures = []
        with monkeypatch.context() as patch:
            async def first_close():
                entered[0].set()
                await asyncio.Event().wait()

            async def second_close():
                entered[1].set()
                await asyncio.Event().wait()

            def failed_close(name):
                def close():
                    failures.append(name)
                    raise RuntimeError(name)
                return close

            patch.setattr(transport, "aclose", first_close)
            patch.setattr(runtime.memory_store, "aclose", second_close, raising=False)
            patch.setattr(runtime.decision_store, "close", failed_close("decision close failed"))
            patch.setattr(runtime.provenance_store, "close", failed_close("provenance close failed"))
            if release_failure:
                def bad_drop(handle):
                    raise OSError("lock close failed")
                patch.setattr(instance_lock, "_drop_handle", bad_drop)
            task = asyncio.create_task(wiring.aclose_runtime(runtime))
            try:
                for event in entered:
                    await asyncio.wait_for(event.wait(), 5)
                    task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 5)
                assert task.cancelled() and task.cancelling() == 2
                assert set(failures) == {"decision close failed", "provenance close failed"}
                assert "decision close failed" in caplog.text and "provenance close failed" in caplog.text
                assert not instance_lock._LOCK_VALID
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    runtime.checkpoint_store._connection.execute("SELECT 1")
                assert not transport._client.is_closed
                if release_failure:
                    assert lock_held()
                    assert "lock close failed" in caplog.text
                    with pytest.raises(RuntimeError, match="uncertain|invalid"):
                        build(assembly_env(tmp_path, semantic=True, c2=True, trio=role_paths(tmp_path)))
                else:
                    assert not lock_held()
            finally:
                # Restore failing closers before the explicit cleanup retry.
                patch.undo()
                await wiring.aclose_runtime(runtime)
        assert not lock_held() and transport._client.is_closed
    asyncio.run(exercise())


def test_async_close_errors_continue_and_normal_close_rebuilds(tmp_path, monkeypatch):
    from app.execution import wiring
    from cryptography.fernet import Fernet

    async def exercise():
        # A persisted local-runtime credential must use the same key on reopen.
        credential_key = Fernet.generate_key().decode("ascii")
        runtime = c2_runtime_with_transport(tmp_path, credential_key=credential_key)
        closed = []
        with monkeypatch.context() as patch:
            async def fail_transport():
                raise RuntimeError("async close failed")

            original = runtime.decision_store.close
            def close_then_fail():
                original()
                closed.append(True)
                raise RuntimeError("sync close failed")

            patch.setattr(runtime.local_runtime_transport, "aclose", fail_transport)
            patch.setattr(runtime.decision_store, "close", close_then_fail)
            try:
                with pytest.raises(RuntimeError, match="async close failed"):
                    await wiring.aclose_runtime(runtime)
                assert closed == [True] and not lock_held()
                with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                    runtime.checkpoint_store._connection.execute("SELECT 1")
            finally:
                patch.undo()
                await wiring.aclose_runtime(runtime)
        await wiring.aclose_runtime(runtime)  # Repeat normal async shutdown.
        rebuilt = c2_runtime_with_transport(tmp_path, credential_key=credential_key)
        await wiring.aclose_runtime(rebuilt)
        assert rebuilt.local_runtime_transport._client.is_closed and not lock_held()
    asyncio.run(exercise())
