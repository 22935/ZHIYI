"""Application model adapter registration for AgentOS."""

from __future__ import annotations

from agentos.adapters.model_adapter import register_model_service_factory
from app.services.aiservice import AIService as AppAIService


def build_app_ai_service() -> AppAIService:
    return AppAIService()


def configure_model_adapter() -> None:
    register_model_service_factory(build_app_ai_service)


__all__ = ["build_app_ai_service", "configure_model_adapter"]
