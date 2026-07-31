"""Model adapter contracts for AgentOS.

This module deliberately does not load application services. Concrete model
providers are registered by the application layer.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field


class StructuredGenerationError(RuntimeError):
    """Stable execution error raised by a structured model runtime."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class StructuredGenerationResult(BaseModel):
    """Safe structured result returned to Core without raw prompts or responses."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    data: Dict[str, Any]
    provider: str
    model: str
    latency_ms: int = Field(default=0, alias="latencyMs", ge=0)
    prompt_version: str = Field(default="native-capability.v1", alias="promptVersion")
    usage: Dict[str, Any] = Field(default_factory=dict)

    def audit_record(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "latencyMs": self.latency_ms,
            "promptVersion": self.prompt_version,
            "usage": dict(self.usage),
        }


class StructuredGenerationRuntime(Protocol):
    """Application-injected, bounded JSON generation service used by ACG agents."""

    def is_available(self) -> bool:
        ...

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
        ...


class ModelService(Protocol):
    async def generate_text(
        self,
        text: str,
        role_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        ...


ModelServiceFactory = Callable[[], ModelService]

_model_service_factory: Optional[ModelServiceFactory] = None


def register_model_service_factory(factory: ModelServiceFactory) -> None:
    global _model_service_factory
    _model_service_factory = factory


def clear_model_service_factory() -> None:
    global _model_service_factory
    _model_service_factory = None


class AIService:
    """Compatibility proxy for Pack skills that expect an AIService instance."""

    def __init__(self, delegate: Optional[ModelService] = None):
        self._delegate = delegate

    def _resolve_delegate(self) -> ModelService:
        if self._delegate is not None:
            return self._delegate
        if _model_service_factory is None:
            raise RuntimeError(
                "No AgentOS model service factory registered. "
                "Register one from the application layer before using AIService."
            )
        self._delegate = _model_service_factory()
        return self._delegate

    async def generate_text(
        self,
        text: str,
        role_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        return await self._resolve_delegate().generate_text(
            text=text,
            role_id=role_id,
            context=context,
        )


class ModelAdapter:
    """Thin model adapter wrapper used by AgentOS packs."""

    def __init__(self, ai_service: Optional[ModelService] = None):
        self.ai_service = ai_service or AIService()

    async def generate_text(
        self,
        text: str,
        role_id: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        return await self.ai_service.generate_text(text=text, role_id=role_id, context=context)


__all__ = [
    "AIService",
    "ModelAdapter",
    "ModelService",
    "ModelServiceFactory",
    "StructuredGenerationError",
    "StructuredGenerationResult",
    "StructuredGenerationRuntime",
    "clear_model_service_factory",
    "register_model_service_factory",
]
