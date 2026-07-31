import asyncio

import pytest

from agentos.adapters.model_adapter import (
    AIService,
    clear_model_service_factory,
    register_model_service_factory,
)


class FakeModelService:
    async def generate_text(self, text, role_id=None, context=None):
        return {
            "text": f"echo:{text}",
            "role_id": role_id,
            "context": context or [],
        }


def teardown_function():
    clear_model_service_factory()


def test_ai_service_requires_application_registered_factory():
    async def _run():
        with pytest.raises(RuntimeError, match="No AgentOS model service factory registered"):
            await AIService().generate_text("hello")

    asyncio.run(_run())


def test_ai_service_uses_registered_application_factory():
    async def _run():
        register_model_service_factory(lambda: FakeModelService())
        result = await AIService().generate_text(
            "hello",
            role_id="writer",
            context=[{"role": "user", "content": "draft"}],
        )
        assert result["text"] == "echo:hello"
        assert result["role_id"] == "writer"
        assert result["context"][0]["content"] == "draft"

    asyncio.run(_run())
