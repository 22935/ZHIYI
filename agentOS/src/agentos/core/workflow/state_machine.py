"""AgentOS Core 的 state_machine 模块，提供运行时控制、状态、Trace、审核或治理能力。"""


from enum import Enum
from typing import TypeVar

from agentos.core.models.types import StepStatus, WorkflowStatus

StatusT = TypeVar("StatusT", WorkflowStatus, StepStatus)


class InvalidStateTransition(ValueError):
    """工作流或步骤尝试非法状态流转时抛出。"""


class StateMachine:
    """工作流运行和步骤共享的状态机。"""

    _transitions = {
        "pending": {"planning", "running", "failed", "cancelled", "skipped_by_condition"},
        "planning": {"running", "failed", "cancelled"},
        "running": {"waiting_review", "retrying", "failed", "completed", "cancelled"},
        "waiting_review": {"running", "retrying", "failed", "completed", "cancelled"},
        "retrying": {"running", "failed", "cancelled"},
        "failed": {"retrying", "cancelled"},
        "completed": set(),
        "cancelled": set(),
        "skipped_by_condition": set(),
    }

    def can_transition(self, current: Enum, target: Enum) -> bool:
        if current == target:
            return True
        return target.value in self._transitions.get(current.value, set())

    def transition(self, current: StatusT, target: StatusT) -> StatusT:
        if not self.can_transition(current, target):
            raise InvalidStateTransition(f"illegal transition: {current.value} -> {target.value}")
        return target
