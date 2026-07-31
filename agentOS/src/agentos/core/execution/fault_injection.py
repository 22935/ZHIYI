"""故障注入与恢复策略（设计书 §2.6/§7.2）。

为“自愈闭环”演示提供可控故障源：在指定 Step 注入模型超时、Agent 崩溃、
证据为空等异常，验证检查点恢复与局部重规划能否让任务在无人工干预下
自主纠错并续跑。

故障注入通过任务输入声明，不污染生产执行逻辑：
  task.input["faultInjection"] = {
      "step_id": "risk_detect",      # 在哪个节点注入
      "fault_type": "timeout",        # timeout | crash | empty_evidence
      "max_triggers": 1,               # 触发几次后自愈（默认 1，模拟瞬时故障）
  }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class FaultType(str, Enum):
    TIMEOUT = "timeout"          # 模型/调用超时
    CRASH = "crash"              # Agent 崩溃
    EMPTY_EVIDENCE = "empty_evidence"  # 证据检索为空
    NONE = "none"


class InjectedFault(RuntimeError):
    """注入的可恢复故障。携带类型供恢复策略分类处理。"""

    def __init__(self, fault_type: FaultType, step_id: str, message: str = ""):
        self.fault_type = fault_type
        self.step_id = step_id
        super().__init__(message or f"injected {fault_type.value} fault at {step_id}")


@dataclass
class FaultInjector:
    """按配置在指定节点注入有限次故障，之后自动“痊愈”（模拟瞬时异常）。"""

    step_id: Optional[str] = None
    fault_type: FaultType = FaultType.NONE
    max_triggers: int = 1
    _triggered: int = field(default=0, init=False)

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]]) -> "FaultInjector":
        if not isinstance(config, dict) or not config.get("step_id"):
            return cls()
        try:
            fault_type = FaultType(str(config.get("fault_type", "timeout")))
        except ValueError:
            fault_type = FaultType.TIMEOUT
        return cls(
            step_id=str(config["step_id"]),
            fault_type=fault_type,
            max_triggers=int(config.get("max_triggers", 1)),
        )

    @property
    def active(self) -> bool:
        return self.step_id is not None and self.fault_type != FaultType.NONE

    def should_fire(self, step_id: str) -> bool:
        return (
            self.active
            and step_id == self.step_id
            and self._triggered < self.max_triggers
        )

    def fire(self, step_id: str) -> None:
        """触发故障（若适用）。计数 +1，达到上限后自愈。"""
        if self.should_fire(step_id):
            self._triggered += 1
            raise InjectedFault(self.fault_type, step_id)

    @property
    def triggered_count(self) -> int:
        return self._triggered

    def restore_triggered_count(self, value: int) -> None:
        self._triggered = max(0, int(value))


__all__ = ["FaultType", "InjectedFault", "FaultInjector"]
