"""统一节点执行 wrapper。

对应设计书任务5《统一节点 Trace wrapper》与执行器“可观测性”关键特性：
每个 Step 执行都产生 STEP_STARTED → AGENT_CALLED/STEP_SUCCEEDED → STEP_FAILED
的统一事件序列，并带 durationMs、输入摘要、输出摘要、error。

这让执行过程从“节点没有统一事件、durationMs 多为 0”升级为节点级白盒可审计。
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Dict, Optional


def summarize(data: Any, *, max_chars: int = 280) -> str:
    """为 trace 生成稳定、有界的输入/输出摘要，避免把全量 payload 灌入日志。"""
    if data is None:
        return ""
    if isinstance(data, str):
        text = data
    else:
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(data)
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"…(+{len(text) - max_chars} chars)"


class StepExecutionTimer:
    """轻量计时器，配合 wrapper 统计节点耗时。"""

    def __init__(self) -> None:
        self._start = perf_counter()

    def elapsed_ms(self) -> int:
        return int((perf_counter() - self._start) * 1000)


def input_summary(payload: Dict[str, Any]) -> str:
    return summarize(payload)


def output_summary(payload: Optional[Dict[str, Any]]) -> str:
    return summarize(payload)


__all__ = ["summarize", "StepExecutionTimer", "input_summary", "output_summary"]
