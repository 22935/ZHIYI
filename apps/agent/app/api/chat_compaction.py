"""Explicit OScode projection. Original conversation records are never rewritten."""
from typing import Literal

from agents.run import ModelInputData
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.ai_engine.model_runtime import resolve_system_runtime_config
from app.config import settings
from app.context_compaction.runtime import CompactionBridgeError, build_input_filter
from app.tools import get_chat_tool_runtime
from app.tools.runtime import _provider_for_model

router = APIRouter()


class CompactMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CompactRequest(BaseModel):
    context_id: str = Field(min_length=1)
    context: list[CompactMessage] = Field(min_length=1)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    role_id: str | None = None


@router.post("/chat/compact")
async def compact_chat(request: CompactRequest):
    if not settings.OSCODE_CONTEXT_COMPACTION_MANUAL_ENABLED:
        raise HTTPException(503, detail={"code": "COMPACTION_DISABLED", "message": "手动上下文压缩已关闭"})
    model, base_url, api_key = request.model or "", request.base_url or "", request.api_key or ""
    client = projection = None
    try:
        if not base_url and not api_key:
            model, base_url, api_key = resolve_system_runtime_config(model)
        runtime = get_chat_tool_runtime()
        context = runtime._context(request.role_id, provider=_provider_for_model(model, base_url), session_id=request.context_id)
        agent, client, metadata = runtime._build_agent(
            context, model=model, base_url=base_url, api_key=api_key,
            require_evidence=False, thinking_mode="disabled")
        projection = build_input_filter(
            agent=agent, context_id=request.context_id,
            model=str(metadata.get("effectiveModel") or model), base_url=base_url, api_key=api_key,
            model_policies=settings.OSCODE_CONTEXT_COMPACTION_MODELS)
        # Match the normal Runtime's history normalization, without appending a command turn.
        history = [{"role": item.role, "content": item.content.strip()}
                   for item in request.context if item.content.strip()]
        result = await projection.project(ModelInputData(input=history, instructions=agent.instructions), force=True)
        metrics = projection.last_metrics or {}
        return {"contextId": request.context_id, "status": metrics.get("status", "unchanged"),
                "messages": result.input, "metrics": metrics, "model": str(metadata.get("effectiveModel") or model),
                "contextWindowTokens": projection.budget["contextWindow"]}
    except (CompactionBridgeError, ValueError) as error:
        raise HTTPException(422, detail={"code": "COMPACTION_CONFIG_REQUIRED",
                            "message": "压缩不可用，请检查模型窗口配置及 Node 运行环境"}) from error
    except Exception as error:
        raise HTTPException(503, detail={"code": "COMPACTION_FAILED",
                            "message": "上下文压缩失败，原始对话已保留，请稍后重试"}) from error
    finally:
        if projection is not None:
            await projection.close()
        if client is not None:
            await client.close()
