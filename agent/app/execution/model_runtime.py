"""Application adapter for bounded, asynchronous ACG structured generation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Any, Dict

from agentos.adapters.model_adapter import (
    StructuredGenerationError,
    StructuredGenerationResult,
)

from app.llm.gateway import get_llm_gateway


def _positive_int(name: str, default: int) -> int:
    try:
        return max(1, int((os.getenv(name) or str(default)).strip()))
    except ValueError:
        return default


class GatewayStructuredGenerationRuntime:
    """Run synchronous gateway calls outside the event loop with bounded concurrency."""

    def __init__(self, *, max_concurrency: int | None = None) -> None:
        workers = max_concurrency or _positive_int("AGENTOS_ACG_MODEL_MAX_CONCURRENCY", 2)
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="agentos-acg-model",
        )

    def is_available(self) -> bool:
        return get_llm_gateway().provider_name not in {"", "mock", "unavailable"}

    async def generate_json(
        self,
        *,
        prompt: str,
        schema: Dict[str, Any],
        thinking_mode: str = "disabled",
        timeout_seconds: float = 120.0,
        max_output_tokens: int = 4096,
        prompt_version: str = "native-capability.v1",
    ) -> StructuredGenerationResult:
        gateway = get_llm_gateway()
        if gateway.provider_name in {"", "mock", "unavailable"}:
            raise StructuredGenerationError(
                "MODEL_UNAVAILABLE",
                "No production model is configured for native ACG execution.",
            )

        loop = asyncio.get_running_loop()

        def invoke() -> Dict[str, Any]:
            return gateway.generate_json(
                prompt,
                schema,
                thinking_mode=thinking_mode,
                max_tokens=max_output_tokens,
            )

        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(self._executor, invoke),
                timeout=max(1.0, timeout_seconds),
            )
        except asyncio.TimeoutError as exc:
            raise StructuredGenerationError(
                "MODEL_TIMEOUT",
                f"Structured model generation exceeded {timeout_seconds:g} seconds.",
            ) from exc
        except StructuredGenerationError:
            raise
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if (
                "invalid json returned" in lowered
                or "json response must be an object" in lowered
                or "unterminated string" in lowered
            ):
                code = "MODEL_OUTPUT_INVALID_JSON"
            elif "empty json content" in lowered or "empty content" in lowered:
                code = "MODEL_EMPTY_RESPONSE"
            elif "rate limit" in lowered or "429" in lowered:
                code = "MODEL_RATE_LIMITED"
            elif "timeout" in lowered or "timed out" in lowered:
                code = "MODEL_TIMEOUT"
            else:
                code = "MODEL_TRANSPORT_ERROR"
            raise StructuredGenerationError(code, message or code) from exc

        data = raw.get("data")
        if not isinstance(data, dict) or not data:
            raise StructuredGenerationError(
                "MODEL_EMPTY_RESPONSE",
                "Structured model generation returned no JSON object.",
            )
        return StructuredGenerationResult(
            data=data,
            provider=str(raw.get("provider") or gateway.provider_name),
            model=str(raw.get("model") or gateway.model),
            latencyMs=int(raw.get("latency_ms") or 0),
            promptVersion=prompt_version,
            usage=dict(raw.get("usage") or {}),
        )


__all__ = ["GatewayStructuredGenerationRuntime"]
