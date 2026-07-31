"""Managed in-process execution for prepared workflow runs."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentos.core.runtime import WorkflowRuntime


logger = logging.getLogger(__name__)


class RunExecutionCoordinator:
    """Own background tasks without treating the task registry as business state."""

    def __init__(self, runtime: "WorkflowRuntime") -> None:
        self.runtime = runtime
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._accepting = True

    async def submit(self, run_id: str) -> bool:
        """Submit once per process; return False when the run is already active."""

        async with self._lock:
            existing = self._tasks.get(run_id)
            if existing is not None and not existing.done():
                return False
            if not self._accepting:
                raise RuntimeError("workflow execution coordinator is shutting down")
            run = self.runtime.workflow_store.get_run(run_id)
            if run.status.value != "pending" or run.started_at is not None:
                return False
            task = asyncio.create_task(
                self._run_managed(run_id),
                name=f"workflow-run:{run_id}",
            )
            self._tasks[run_id] = task
        run = self.runtime.workflow_store.get_run(run_id)
        logger.info(
            "run_submitted",
            extra={
                "taskId": run.task_id,
                "runId": run.run_id,
                "workflowId": run.workflow_id,
                "phase": run.lifecycle_phase.value if run.lifecycle_phase else None,
            },
        )
        return True

    def is_active(self, run_id: str) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    async def startup(self, *, orphan_limit: int = 200) -> list[str]:
        return await self.runtime.close_orphaned_runs(limit=orphan_limit)

    async def shutdown(self) -> None:
        async with self._lock:
            self._accepting = False
            tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_managed(self, run_id: str) -> None:
        started = monotonic()
        try:
            await self.runtime.execute_prepared_run(run_id)
        except asyncio.CancelledError:
            try:
                await self.runtime.fail_run_safely(
                    run_id,
                    error_code="worker_shutdown",
                    error_message="工作流执行因服务进程关闭而中断",
                )
            except Exception:
                logger.exception("Failed to persist worker shutdown state", extra={"runId": run_id})
            raise
        except Exception as exc:
            try:
                await self.runtime.fail_run_safely(
                    run_id,
                    error_code="workflow_execution_failed",
                    error_message=self.runtime._safe_error_message(exc),
                )
            except Exception:
                logger.exception("Failed to persist managed run failure", extra={"runId": run_id})
            logger.exception(
                "Managed workflow execution failed",
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


__all__ = ["RunExecutionCoordinator"]
