"""新领域对象的最小状态迁移规则。"""

from __future__ import annotations

from enum import Enum

from domain.models import AttemptStatus, RunStatus, MissionStatus


_TASK_TRANSITIONS = {
    MissionStatus.CREATED: {MissionStatus.PLANNING, MissionStatus.ARCHIVED},
    MissionStatus.PLANNING: {MissionStatus.READY, MissionStatus.ARCHIVED},
    MissionStatus.READY: {MissionStatus.RUNNING, MissionStatus.ARCHIVED},
    MissionStatus.RUNNING: {MissionStatus.COMPLETED, MissionStatus.READY, MissionStatus.ARCHIVED},
    MissionStatus.COMPLETED: {MissionStatus.ARCHIVED},
    MissionStatus.ARCHIVED: set(),
}

_RUN_TRANSITIONS = {
    # A run may fail before its first node starts (for example during graph
    # validation or scheduler preparation), so FAILED is a valid terminal
    # outcome directly from PENDING.
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.SUPERSEDED},
    RunStatus.RUNNING: {RunStatus.FAILED, RunStatus.SUCCEEDED, RunStatus.CANCELLED, RunStatus.SUPERSEDED},
    # An operator may explicitly reopen the same execution Run for a
    # checkpoint retry.  Other terminal states remain immutable.
    RunStatus.FAILED: {RunStatus.PENDING},
    RunStatus.SUCCEEDED: set(),
    RunStatus.CANCELLED: set(),
    RunStatus.SUPERSEDED: set(),
}

_ATTEMPT_TRANSITIONS = {
    AttemptStatus.PENDING: {AttemptStatus.RUNNING, AttemptStatus.CANCELLED},
    AttemptStatus.RUNNING: {
        AttemptStatus.FAILED,
        AttemptStatus.SUCCEEDED,
        AttemptStatus.CANCELLED,
    },
    AttemptStatus.FAILED: set(),
    AttemptStatus.SUCCEEDED: set(),
    AttemptStatus.CANCELLED: set(),
}


def require_transition(current: Enum, target: Enum) -> None:
    tables = {
        MissionStatus: _TASK_TRANSITIONS,
        RunStatus: _RUN_TRANSITIONS,
        AttemptStatus: _ATTEMPT_TRANSITIONS,
    }
    table = tables.get(type(current))
    if table is None or type(current) is not type(target) or target not in table[current]:
        raise ValueError(f"invalid lifecycle transition: {current.value} -> {target.value}")


__all__ = ["require_transition"]
