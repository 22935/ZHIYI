"""
对话API路由
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Literal, Optional
import asyncio
import logging
import time
from uuid import uuid4
from app.services.aiservice import AIService
from app.config import settings
from app.ai_engine.model_runtime import (
    apply_reasoning_instruction,
    list_system_runtime_models,
    model_capability_summary,
    resolve_system_runtime_config,
    stream_with_runtime_model,
)
from app.llm.chat_stream import ChatStreamEvent, ChatStreamEventType
from app.tools import get_chat_tool_runtime
from app.tools.permissions import (
    ApprovalDecision,
    ChatApprovalMode,
    ApprovalResolutionError,
    get_chat_permission_service,
)

router = APIRouter()

# 依赖注入AI服务
ai_service = AIService()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    text: str
    role_id: Optional[str] = None
    context_id: Optional[str] = None
    context: Optional[List[Dict[str, str]]] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking_mode: Optional[str] = None
    reasoning_effort: Optional[str] = None
    tool_mode: Literal["auto", "disabled"] = "auto"
    approval_mode: ChatApprovalMode = "ask"

    def resolved_thinking_mode(self) -> str:
        if self.thinking_mode:
            return self.thinking_mode
        effort = (self.reasoning_effort or "").strip().lower()
        if effort in {"", "none", "off", "disabled"}:
            return "disabled"
        # Keep the exact provider value in provider_parameters(); this is only
        # the legacy coarse mode used before capability adaptation.
        return "standard" if effort in {"low", "medium", "minimal"} else "deep"

    def provider_parameters(self) -> Dict[str, str]:
        return {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}

class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str
    context_id: Optional[str] = Field(default=None, alias="contextId")
    confidence: float
    tokens_used: int
    animation: Optional[Dict] = None
    model_info: Optional[str] = None
    metadata: Optional[Dict] = None
    sources: Optional[List[Dict]] = None


class ChatApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    decision: ApprovalDecision
    session_id: str = Field(alias="sessionId", min_length=1)
    invocation_id: Optional[str] = Field(default=None, alias="invocationId")
    capability_id: Optional[str] = Field(default=None, alias="capabilityId")
    relative_path: Optional[str] = Field(default=None, alias="relativePath")


class ChatExecutionCancelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    request_id: str = Field(alias="requestId", min_length=1)


@router.post("/chat/approvals/{approval_id}")
async def resolve_chat_approval(
    approval_id: str,
    request: ChatApprovalDecisionRequest,
):
    """Resolve one pending Chat approval without exposing Host Grant authority."""
    try:
        await get_chat_permission_service().resolve(
            approval_id,
            decision=request.decision,
            session_id=request.session_id,
            invocation_id=request.invocation_id,
            capability_id=request.capability_id,
            relative_path=request.relative_path,
        )
    except ApprovalResolutionError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return {
        "approvalId": approval_id,
        "status": "resolved",
        "decision": request.decision.value,
    }


@router.get("/chat/models")
async def chat_models():
    """Return models available through the server-managed API connection."""
    return await list_system_runtime_models()


@router.get("/chat/model-capabilities")
async def chat_model_capabilities(model: str, base_url: str = ""):
    """Per-model capability metadata (thinking modes / efforts) without secrets.

    base_url 省略时按服务端当前激活供应商解析；自定义连接显式传入 base_url。
    """
    if not base_url.strip():
        _, resolved_base_url, _ = resolve_system_runtime_config(model)
        base_url = resolved_base_url
    return model_capability_summary(model, base_url, "")


@router.get("/chat/capabilities")
async def chat_capabilities():
    """Report server-managed model and Chat tool availability without secrets."""
    models = await list_system_runtime_models()
    return {**models, "toolRuntime": get_chat_tool_runtime().capabilities()}

@router.post("/chat/text", response_model=ChatResponse)
async def chat_text(request: ChatRequest):
    """文本对话"""
    requested_thinking_mode = request.resolved_thinking_mode()
    model = request.model or ""
    base_url = request.base_url or ""
    api_key = request.api_key or ""
    if model and not base_url and not api_key:
        model, base_url, api_key = resolve_system_runtime_config(model)
    runtime = get_chat_tool_runtime() if request.tool_mode == "auto" else get_chat_tool_runtime().scoped([])
    session_id = request.context_id or f"chat_{uuid4().hex}"
    response = await runtime.run(
        request.text,
        history=request.context,
        role_id=request.role_id,
        model=model,
        base_url=base_url,
        api_key=api_key,
        thinking_mode=requested_thinking_mode,
        parameters=request.provider_parameters(),
        session_id=session_id,
        approval_mode=request.approval_mode,
        **({"oscode_context_compaction": True} if settings.OSCODE_CONTEXT_COMPACTION_ENABLED else {}),
    )
    usage = response.usage
    tool_executions = [item.public_dict() for item in response.tool_executions]
    tools_used = list(dict.fromkeys(item.tool_name for item in response.tool_executions))
    execution_summary = [
        {
            "stage": f"tool:{item.tool_name}:{item.call_id}",
            "status": item.status,
            "description": item.output_summary,
            "durationMs": item.duration_ms,
            "terminal": item.terminal,
            "activity": item.activity,
        }
        for item in response.tool_executions
    ]
    execution_summary.append(
        {
            "stage": "answer_generation",
            "status": "completed",
            "description": "模型完成最终回答生成",
        }
    )
    return ChatResponse(
        text=response.text,
        contextId=session_id,
        confidence=0.95,
        tokens_used=int(usage.get("total_tokens") or 0),
        model_info=response.model,
        sources=[source.public_dict() for source in response.sources],
        metadata={
            **response.metadata,
            "inputTokens": usage.get("input_tokens"),
            "outputTokens": usage.get("output_tokens"),
            "totalTokens": usage.get("total_tokens"),
            "thinkingEnabled": response.metadata.get("effectiveThinkingMode", requested_thinking_mode) != "disabled",
            "executionSummary": execution_summary,
            "toolsUsed": tools_used,
            "toolExecutions": tool_executions,
            "fallbackUsed": False,
        },
    )

async def _stream_sse_events(
    chunks,
    http_request: Request,
    heartbeat_interval: float,
    *,
    request_id: str = "anonymous",
    context_id: Optional[str] = None,
):
    """Forward model chunks while emitting comments and promptly cancelling the iterator."""
    iterator = chunks.__aiter__()
    pending_chunk = None
    sequence = 0
    saw_done = False
    try:
        while True:
            if await http_request.is_disconnected():
                logger.info("SSE client disconnected before next model chunk")
                return

            pending_chunk = asyncio.create_task(iterator.__anext__())
            while not pending_chunk.done():
                done, _ = await asyncio.wait({pending_chunk}, timeout=heartbeat_interval)
                if pending_chunk in done:
                    break
                if await http_request.is_disconnected():
                    logger.info("SSE client disconnected while awaiting model chunk")
                    return
                # Keep the comment for legacy clients, and emit a real event
                # because the Java WebClient SSE bridge drops comments.
                sequence += 1
                heartbeat = ChatStreamEvent(
                    event=ChatStreamEventType.HEARTBEAT,
                    request_id=request_id,
                    sequence=sequence,
                    data={"status": "waiting"},
                )
                yield ": heartbeat\n\n"
                yield f"event: {heartbeat.event.value}\ndata: {heartbeat.sse_data()}\n\n"

            try:
                chunk = pending_chunk.result()
            except StopAsyncIteration:
                if not saw_done:
                    sequence += 1
                    done = ChatStreamEvent(
                        event=ChatStreamEventType.DONE,
                        request_id=request_id,
                        sequence=sequence,
                        data={"status": "completed", "contextId": context_id},
                    )
                    yield f"event: {done.event.value}\ndata: {done.sse_data()}\n\n"
                return

            if isinstance(chunk, ChatStreamEvent):
                stream_event = chunk
            else:
                sequence += 1
                stream_event = ChatStreamEvent(
                    event=ChatStreamEventType.CONTENT_DELTA,
                    request_id=request_id,
                    sequence=sequence,
                    data={"delta": str(chunk)},
                )
            sequence = max(sequence, stream_event.sequence)
            if stream_event.event == ChatStreamEventType.DONE:
                saw_done = True
                if context_id:
                    stream_event.data.setdefault("contextId", context_id)
            yield f"event: {stream_event.event.value}\ndata: {stream_event.sse_data()}\n\n"
            pending_chunk = None
    except asyncio.CancelledError:
        logger.info("SSE generation cancelled by downstream")
        raise
    except Exception as error:
        logger.exception("SSE model stream failed. type=%s", type(error).__name__)
        sequence += 1
        stream_event = ChatStreamEvent(
            event=ChatStreamEventType.ERROR,
            request_id=request_id,
            sequence=sequence,
            data={"code": "AI_STREAM_FAILED"},
        )
        yield f"event: error\ndata: {stream_event.sse_data()}\n\n"
    finally:
        if pending_chunk is not None and not pending_chunk.done():
            pending_chunk.cancel()
            await asyncio.gather(pending_chunk, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


@router.post("/chat/text/stream")
async def chat_text_stream(chat_request: ChatRequest, http_request: Request):
    """流式文本对话 (SSE)"""
    async def event_stream():
        request_id = f"chat_{uuid4().hex}"
        session_id = chat_request.context_id or request_id
        if chat_request.model and not chat_request.base_url and not chat_request.api_key:
            chat_request.model, chat_request.base_url, chat_request.api_key = resolve_system_runtime_config(chat_request.model)
        runtime = get_chat_tool_runtime() if chat_request.tool_mode == "auto" else get_chat_tool_runtime().scoped([])
        chunks = runtime.stream(
            chat_request.text,
            history=chat_request.context,
            role_id=chat_request.role_id,
            model=chat_request.model or "",
            base_url=chat_request.base_url or "",
            api_key=chat_request.api_key or "",
            thinking_mode=chat_request.resolved_thinking_mode(),
            parameters=chat_request.provider_parameters(),
            request_id=request_id,
            session_id=session_id,
            approval_mode=chat_request.approval_mode,
            **({"oscode_context_compaction": True} if settings.OSCODE_CONTEXT_COMPACTION_ENABLED else {}),
        )
        async for event in _stream_sse_events(
                chunks,
                http_request,
                max(settings.SSE_HEARTBEAT_INTERVAL, 0.1),
                request_id=request_id,
                context_id=session_id,
        ):
            yield event
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/text/cancel")
async def chat_text_cancel(request: ChatExecutionCancelRequest):
    """Cancel the active Local Runtime process for one Chat stream."""
    cancelled = await get_chat_tool_runtime().cancel(request.request_id)
    return {"requestId": request.request_id, "cancelled": cancelled}


async def _plain_text_stream_events(
    chunks,
    *,
    request_id: str,
    thinking_mode: str,
    model: str,
):
    sequence = 0
    started = time.perf_counter()
    reasoning_started = thinking_mode != "disabled"
    if reasoning_started:
        sequence += 1
        yield ChatStreamEvent(
            event=ChatStreamEventType.REASONING_START,
            request_id=request_id,
            sequence=sequence,
            data={
                "requestedThinkingMode": thinking_mode,
                "effectiveThinkingMode": thinking_mode,
            },
        )
    first_content = True
    async for chunk in chunks:
        if chunk and first_content and reasoning_started:
            sequence += 1
            yield ChatStreamEvent(
                event=ChatStreamEventType.REASONING_END,
                request_id=request_id,
                sequence=sequence,
                data={"reasoningPhaseMs": int((time.perf_counter() - started) * 1000)},
            )
        first_content = False
        if chunk:
            sequence += 1
            yield ChatStreamEvent(
                event=ChatStreamEventType.CONTENT_DELTA,
                request_id=request_id,
                sequence=sequence,
                data={"delta": str(chunk)},
            )
    if first_content and reasoning_started:
        sequence += 1
        yield ChatStreamEvent(
            event=ChatStreamEventType.REASONING_END,
            request_id=request_id,
            sequence=sequence,
            data={"reasoningPhaseMs": int((time.perf_counter() - started) * 1000)},
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    sequence += 1
    yield ChatStreamEvent(
        event=ChatStreamEventType.USAGE,
        request_id=request_id,
        sequence=sequence,
        data={
            "latencyMs": latency_ms,
            "requestedModel": model,
            "effectiveModel": model,
            "requestedThinkingMode": thinking_mode,
            "effectiveThinkingMode": thinking_mode,
        },
    )
    sequence += 1
    yield ChatStreamEvent(
        event=ChatStreamEventType.DONE,
        request_id=request_id,
        sequence=sequence,
        data={"status": "completed", "latencyMs": latency_ms},
    )

@router.post("/chat/voice")
async def chat_voice(
    audio: UploadFile = File(...),
    role_id: Optional[str] = Form(None)
):
    """语音对话"""
    audio_data = await audio.read()
    response = await ai_service.recognize_speech(audio_data)

    # 根据识别的文本生成回复
    chat_response = await ai_service.generate_text(
        text=response["text"],
        role_id=role_id
    )

    return {
        "text": chat_response["text"],
        "confidence": chat_response["confidence"],
        "recognized_text": response["text"]
    }

