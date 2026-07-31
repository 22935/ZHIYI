from __future__ import annotations

import asyncio
from threading import Lock
import time

import pytest

from agentos.adapters.model_adapter import StructuredGenerationError
from app.execution.model_runtime import GatewayStructuredGenerationRuntime


class _Gateway:
    provider_name = "test-provider"
    model = "test-model"

    def __init__(self, *, delay: float = 0.0):
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def generate_json(self, prompt, schema, **kwargs):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            return {
                "data": {"answer": prompt},
                "provider": self.provider_name,
                "model": self.model,
                "latency_ms": int(self.delay * 1000),
            }
        finally:
            with self._lock:
                self.active -= 1


class _InvalidJsonGateway(_Gateway):
    def generate_json(self, prompt, schema, **kwargs):
        raise RuntimeError(
            "Invalid JSON returned by provider: Unterminated string starting at column 7080"
        )


def test_structured_runtime_rejects_unavailable_provider(monkeypatch):
    gateway = _Gateway()
    gateway.provider_name = "unavailable"
    monkeypatch.setattr(
        "app.execution.model_runtime.get_llm_gateway", lambda: gateway
    )

    runtime = GatewayStructuredGenerationRuntime(max_concurrency=1)
    with pytest.raises(StructuredGenerationError) as raised:
        asyncio.run(
            runtime.generate_json(
                prompt="task",
                schema={"type": "object", "required": ["answer"]},
            )
        )

    assert raised.value.code == "MODEL_UNAVAILABLE"


def test_structured_runtime_is_nonblocking_and_bounded(monkeypatch):
    gateway = _Gateway(delay=0.05)
    monkeypatch.setattr(
        "app.execution.model_runtime.get_llm_gateway", lambda: gateway
    )
    runtime = GatewayStructuredGenerationRuntime(max_concurrency=2)

    async def execute():
        ticked = False

        async def tick():
            nonlocal ticked
            await asyncio.sleep(0.01)
            ticked = True

        calls = [
            runtime.generate_json(
                prompt=f"task-{index}",
                schema={"type": "object", "required": ["answer"]},
            )
            for index in range(4)
        ]
        results = await asyncio.gather(tick(), *calls)
        return ticked, results[1:]

    ticked, results = asyncio.run(execute())

    assert ticked is True
    assert gateway.max_active == 2
    assert [item.data["answer"] for item in results] == [
        "task-0",
        "task-1",
        "task-2",
        "task-3",
    ]
    assert all(item.audit_record()["model"] == "test-model" for item in results)


def test_structured_runtime_classifies_truncated_json(monkeypatch):
    gateway = _InvalidJsonGateway()
    monkeypatch.setattr(
        "app.execution.model_runtime.get_llm_gateway", lambda: gateway
    )
    runtime = GatewayStructuredGenerationRuntime(max_concurrency=1)

    with pytest.raises(StructuredGenerationError) as raised:
        asyncio.run(
            runtime.generate_json(
                prompt="task",
                schema={"type": "object", "required": ["answer"]},
            )
        )

    assert raised.value.code == "MODEL_OUTPUT_INVALID_JSON"
