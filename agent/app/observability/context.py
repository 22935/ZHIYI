from contextlib import contextmanager
from contextvars import ContextVar
import re
import uuid

TRACE_ID_HEADER = "x-trace-id"
TRACE_ID_PATTERN = re.compile(
    r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})"
)

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_workflow_id: ContextVar[str] = ContextVar("workflow_id", default="")
_task_id: ContextVar[str] = ContextVar("task_id", default="")


def valid_trace_id(value: str | None) -> bool:
    return bool(value and len(value) <= 36 and TRACE_ID_PATTERN.fullmatch(value))


def accepted_or_new_trace_id(value: str | None) -> str:
    return value if valid_trace_id(value) else str(uuid.uuid4())


def current_trace_id() -> str:
    return _trace_id.get()


def current_workflow_id() -> str:
    return _workflow_id.get()


def current_task_id() -> str:
    return _task_id.get()


def set_trace_id(value: str):
    return _trace_id.set(value)


def reset_trace_id(token) -> None:
    _trace_id.reset(token)


@contextmanager
def execution_context(*, workflow_id: str = "", task_id: str = ""):
    workflow_token = _workflow_id.set(str(workflow_id or ""))
    task_token = _task_id.set(str(task_id or ""))
    try:
        yield
    finally:
        _task_id.reset(task_token)
        _workflow_id.reset(workflow_token)
