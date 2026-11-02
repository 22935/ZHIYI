"""Application-owned background scheduling for prepared AgentOS runs."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from time import monotonic
from typing import TYPE_CHECKING, Any

from components.planner import ACGPlanningError, TaskDecompositionError
from support.async_tasks import cancel_and_wait

if TYPE_CHECKING:
    from runtime import ExecutionRuntime


logger = logging.getLogger(__name__)


class RunExecutionCoordinator:
    """Own asyncio tasks without becoming a second workflow state machine."""

    def __init__(self, runtime: "ExecutionRuntime") -> None:
        self.runtime = runtime
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._accepting = True
        self._wake_signal = asyncio.Event()
        self._wake_task: asyncio.Task[None] | None = None

    async def submit(self, run_id: str) -> bool:
        """Submit one new or explicitly retrying Run once in this process."""
        async with self._lock:
            existing = self._tasks.get(run_id)
            if existing is not None and not existing.done():
                return False
            if not self._accepting:
                raise RuntimeError("workflow execution coordinator is shutting down")
            run = self.runtime.workflow_store.get_run(run_id)
            run_status = run.status.value
            is_new_run = run_status == "pending" and run.started_at is None
            is_in_place_retry = run_status == "retrying"
            if not (is_new_run or is_in_place_retry):
                return False
            dispatch_store = getattr(self.runtime, "execution_dispatch_store", None)
            if dispatch_store is not None and "graphActivation" in getattr(run, "execution_state", {}):
                command = dispatch_store.get(run_id)
                return await self._schedule_permitted(command, recover=True) if command else False
            task = asyncio.create_task(self._run_managed(run_id), name=f"workflow-run:{run_id}")
            self._track_task(run_id, task)
            self._ensure_wait_monitor()
        logger.info("run_submitted", extra={"runId": run_id})
        return True

    @contextmanager
    def _dispatch_identity(self, command):
        # Only an accepted server-owned command can restore this context.
        # Current semantic authorization and Permit gates are still rechecked.
        from app.security.internal_auth import TrustedUserContext, _trusted_user_context
        token = _trusted_user_context.set(TrustedUserContext(
            command.actor_id, "dispatch:" + command.dispatch_id, "dispatch_recovery", command.tenant_id))
        try:
            yield
        finally:
            _trusted_user_context.reset(token)

    def _validate_permitted(self, run, command, *, initial=False):
        from runtime.permit_recovery import assert_settled_operations
        from support.stores.execution_dispatch_store import DispatchConflict
        if (run is None or run.run_id != command.run_id or run.mission_id != command.mission_id
                or run.record_state.value != "active" or run.status.value not in {"pending", "planning", "running", "retrying"}
                or run.execution_state.get("executionPermitId") != command.permit_id
                or run.execution_state.get("graphId") != command.graph_id
                or run.execution_state.get("graphVersion") != command.graph_version
                or initial and run.runtime_revision != command.runtime_revision):
            raise DispatchConflict("Dispatch source or lifecycle changed")
        principal = self.runtime.semantic_principal_provider()
        self.runtime.mission_semantic_service.require_write_access(principal, run.mission_id)
        authority = self.runtime.execution_permit_authority
        if authority is None:
            raise DispatchConflict("Permit authority unavailable")
        authority.assert_dispatchable(run)
        assert_settled_operations(self.runtime, run)
        with self.runtime._execution_slot_guard:
            if run.run_id in self.runtime._active_execution_slots:
                raise DispatchConflict("Run already owns an execution slot")

    async def submit_permitted(self, command):
        """Durably accept a command, then own its Task; never manufacture a Permit."""
        from support.run_execution_fence import acquire_run_fence
        store = getattr(self.runtime, "execution_dispatch_store", None)
        if store is None:
            raise ValueError("Dispatch control is not enabled")
        async with self._lock:
            if not self._accepting:
                raise RuntimeError("workflow execution coordinator is shutting down")
            old = store.get(command.run_id)
            if old is not None:
                from support.stores.execution_dispatch_store import DispatchConflict
                if old.operation_key != command.operation_key or old.request_fingerprint != command.request_fingerprint:
                    raise DispatchConflict("Run already has another Dispatch command")
                accepted, replay = old, True
            else:
                with self.runtime.run_lock_manager.lock_for(command.run_id), acquire_run_fence(store.db_path, command.run_id):
                    accepted, replay = store.accept(command, lambda run: self._validate_permitted(run, command, initial=True))
            task = self._tasks.get(command.run_id)
            if task is None or task.done():
                await self._schedule_permitted(accepted, recover=replay)
            return accepted, replay

    def _track_task(self, run_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[run_id] = task
        task.add_done_callback(lambda settled: self._forget_finished_task(run_id, settled))

    def _forget_finished_task(self, run_id: str, task: asyncio.Task[None]) -> None:
        if not task.done():
            return
        failure = None if task.cancelled() else task.exception()
        if failure is not None:
            logger.error("managed task cleanup failed", exc_info=failure, extra={"runId": run_id})
        if self._tasks.get(run_id) is task:
            self._tasks.pop(run_id, None)

    def _create_permitted_task(self, command):
        task = asyncio.create_task(
            self._run_managed(command.run_id, permitted=True), name=f"workflow-dispatch:{command.dispatch_id}")
        self._track_task(command.run_id, task)

    async def _schedule_permitted(self, command, *, recover):
        """Caller owns coordinator lock. Recovery remains the Runtime's decision."""
        from support.run_execution_fence import acquire_run_fence
        task = self._tasks.get(command.run_id)
        if task is not None and not task.done():
            return False
        run = self.runtime.workflow_store.get_run(command.run_id)
        if run.status.value in {"waiting_review", "completed", "failed", "cancelled", "superseded"}:
            return False
        with self._dispatch_identity(command):
            try:
                if recover:
                    self.runtime.reconcile_execution_checkpoint(command.run_id)
                with self.runtime.run_lock_manager.lock_for(command.run_id), acquire_run_fence(
                        self.runtime.workflow_store.db_path, command.run_id):
                    self._validate_permitted(self.runtime.workflow_store.get_run(command.run_id), command)
            except (ValueError, KeyError, RuntimeError, PermissionError, sqlite3.Error) as exc:
                # Existing lifecycle authority records a durable, explicit block;
                # no failed execution receipt or external-effect proof is invented.
                await self.runtime.fail_run_safely(command.run_id, error_code="dispatch_recovery_blocked",
                    error_message="Dispatch recovery could not prove safe execution; operator review required")
                logger.warning("dispatch_recovery_blocked", extra={"runId": command.run_id, "errorType": type(exc).__name__})
                return False
            self._create_permitted_task(command)
            self._ensure_wait_monitor()
            return True

    def is_active(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    async def cancel(self, run_id: str) -> bool:
        """Cancel only the managed workflow task for an explicit Run cancel."""
        async with self._lock:
            task = self._tasks.get(run_id)
        if task is None or task.done() or task is asyncio.current_task():
            return False
        if not task.cancelling():
            task.cancel("operator_cancel")
        return True

    async def startup(self, *, orphan_limit: int = 200) -> list[str]:
        self._accepting = True
        closed = await self.runtime.close_orphaned_runs(limit=orphan_limit)
        # close_orphaned_runs persists terminal Runtime state and its
        # run.finished lifecycle event.  Runtime construction performs the
        # initial identity reconciliation before this startup hook, so flush
        # once more here or the identity projection can remain stale at
        # running while the authoritative Runtime is already failed.  The
        # flush must never take startup down: projection dead letters stay
        # persisted for repair instead of crashing the service loop.
        flush_identity_outbox = getattr(self.runtime, "_flush_identity_outbox", None)
        if callable(flush_identity_outbox):
            try:
                flush_identity_outbox(raise_on_failure=False)
            except Exception:
                logger.exception("identity outbox startup reconciliation crashed")
        store = getattr(self.runtime, "workflow_store", None)
        for run in store.list_non_terminal_runs(limit=orphan_limit) if store is not None else ():
            if "graphActivation" in getattr(run, "execution_state", {}):
                continue  # Permit without an accepted Dispatch is never startup work.
            if run.status.value == "retrying" and (run.execution_state.get("planningLoop") or {}).get("restartPending"):
                await self.submit(run.run_id)
        dispatch_store = getattr(self.runtime, "execution_dispatch_store", None)
        if dispatch_store is not None:
            async with self._lock:
                for command in dispatch_store.commands():
                    await self._schedule_permitted(command, recover=True)
        self._ensure_wait_monitor()
        await self.reconcile_waits()
        return closed

    def notify_state_changed(self) -> None:
        """A state-change hint only; authoritative ledgers decide whether to wake."""
        self._wake_signal.set()

    def _ensure_wait_monitor(self) -> None:
        if not callable(getattr(self.runtime, "prepare_planning_wakeups", None)):
            return
        if self._wake_task is None or self._wake_task.done():
            self._wake_task = asyncio.create_task(self._watch_waits(), name="workflow-planning-waits")

    async def reconcile_waits(self) -> None:
        prepare = getattr(self.runtime, "prepare_planning_wakeups", None)
        if prepare is None or not self._accepting:
            return
        for run_id in await prepare():
            await self.submit(run_id)

    async def _watch_waits(self) -> None:
        while self._accepting:
            self._wake_signal.clear()
            try:
                await self.reconcile_waits()
            except Exception:
                logger.exception("Planner wait reconciliation failed")
            try:
                # Timers and missed notifications use the same durable checks.
                # No model is called while a condition remains unsatisfied.
                await asyncio.wait_for(self._wake_signal.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self) -> None:
        async with self._lock:
            self._accepting = False
            tasks = list(self._tasks.values())
            monitor = self._wake_task
        await cancel_and_wait([*tasks, *([monitor] if monitor is not None else [])], reason="worker_shutdown")
        # A Task cancelled before its coroutine first runs never enters that
        # coroutine's finally block. Prune only settled tasks owned above;
        # _accepting=False prevents a new submission during this shutdown.
        async with self._lock:
            for run_id, task in list(self._tasks.items()):
                if task in tasks and task.done():
                    self._tasks.pop(run_id, None)

    async def _run_managed(self, run_id: str, *, permitted: bool = False) -> None:
        started = monotonic()
        try:
            # Yield once so the async Mission response can be sent before
            # synchronous planning/bootstrap work occupies the event loop.
            await asyncio.sleep(0)
            await self.runtime.execute_prepared_run(run_id)
        except asyncio.CancelledError:
            # An operator cancel already persisted CANCELLED before this task
            # is interrupted. Do not misclassify it as worker shutdown.
            try:
                if self.runtime.workflow_store.get_run(run_id).status.value == "cancelled":
                    return
            except Exception:
                pass
            if permitted:
                # Shutdown is not a user cancellation or proof of invocation
                # failure. Keep WAL/checkpoints for existing recovery to verify.
                raise
            try:
                await self.runtime.fail_run_safely(
                    run_id,
                    error_code="worker_shutdown",
                    error_message="workflow execution interrupted by service shutdown",
                )
            except Exception:
                logger.exception("failed to persist worker shutdown", extra={"runId": run_id})
            raise
        except Exception as exc:
            try:
                await self.runtime.fail_run_safely(
                    run_id,
                    error_code=self._error_code(exc),
                    error_message=self.runtime._safe_error_message(exc),
                    error_metadata=self._error_metadata(exc),
                )
            except Exception:
                logger.exception("failed to persist managed run failure", extra={"runId": run_id})
            logger.exception(
                "managed workflow execution failed",
                extra={
                    "runId": run_id,
                    "elapsedMs": int((monotonic() - started) * 1000),
                    "errorType": type(exc).__name__,
                },
            )
        finally:
            current = asyncio.current_task()
            async with self._lock:
                if self._tasks.get(run_id) is current:
                    self._tasks.pop(run_id, None)

    @staticmethod
    def _error_code(exc: Exception) -> str:
        cause_code = RunExecutionCoordinator._cause_code(exc)
        if cause_code == "MODEL_CONNECTION_INTERRUPTED":
            return "model_connection_interrupted"
        if cause_code == "MODEL_TIMEOUT":
            return "model_timeout"
        if isinstance(exc, TaskDecompositionError):
            return "task_decomposition_failed"
        if isinstance(exc, ACGPlanningError):
            return "acg_planning_failed"
        return "workflow_execution_failed"

    @staticmethod
    def _cause_code(exc: BaseException) -> str | None:
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            code = str(getattr(current, "cause_code", None) or getattr(current, "code", None) or "").upper()
            if code in {"MODEL_CONNECTION_INTERRUPTED", "MODEL_TIMEOUT"}:
                return code
            current = current.__cause__ or current.__context__
        return None

    @staticmethod
    def _error_metadata(exc: BaseException) -> dict[str, Any]:
        current: BaseException | None = exc
        while current is not None:
            metadata = getattr(current, "metadata", None)
            if isinstance(metadata, dict):
                return {key: metadata[key] for key in (
                    "stage", "attemptCount", "retryCount", "streamUsed",
                    "timeoutSeconds", "elapsedMs", "transportErrorClass",
                ) if key in metadata}
            current = current.__cause__ or current.__context__
        return {}


__all__ = ["RunExecutionCoordinator"]
