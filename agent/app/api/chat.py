"""
对话API路由
"""
from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Literal, Optional
import asyncio
import logging
import time
from uuid import uuid4
from app.services.aiservice import AIService
from app.config import settings
from app.ai_engine.kylin_sdk.client import KylinAIClient
from app.ai_engine.model_runtime import (
    apply_reasoning_instruction,
    list_system_runtime_models,
    resolve_system_runtime_config,
    stream_with_runtime_model,
)
from app.llm.chat_stream import ChatStreamEvent, ChatStreamEventType
from app.tools import get_tool_runtime

router = APIRouter()

# 依赖注入AI服务
ai_service = AIService()
stream_client = KylinAIClient()
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

    def resolved_thinking_mode(self) -> str:
        return self.thinking_mode or self.reasoning_effort or "disabled"

class ChatResponse(BaseModel):
    text: str
    confidence: float
    tokens_used: int
    animation: Optional[Dict] = None
    model_info: Optional[str] = None
    metadata: Optional[Dict] = None
    sources: Optional[List[Dict]] = None


@router.get("/chat/models")
async def chat_models():
    """Return models available through the server-managed API connection."""
    return await list_system_runtime_models()


@router.get("/chat/capabilities")
async def chat_capabilities():
    """Report server-managed model and read-only tool availability without secrets."""
    models = await list_system_runtime_models()
    return {**models, "toolRuntime": get_tool_runtime().capabilities()}

@router.post("/chat/text", response_model=ChatResponse)
async def chat_text(request: ChatRequest):
    """文本对话"""
    requested_thinking_mode = request.resolved_thinking_mode()
    model = request.model or ""
    base_url = request.base_url or ""
    api_key = request.api_key or ""
    if model and not base_url and not api_key:
        model, base_url, api_key = resolve_system_runtime_config(model)
    runtime = get_tool_runtime() if request.tool_mode == "auto" else get_tool_runtime().scoped([])
    response = await runtime.run(
        request.text,
        history=request.context,
        role_id=request.role_id,
        model=model,
        base_url=base_url,
        api_key=api_key,
        thinking_mode=requested_thinking_mode,
    )
    usage = response.usage
    tool_executions = [item.public_dict() for item in response.tool_executions]
    tools_used = list(dict.fromkeys(item.tool_name for item in response.tool_executions))
    execution_summary = [
        {
            "stage": f"tool:{item.tool_name}",
            "status": item.status,
            "description": item.output_summary,
            "durationMs": item.duration_ms,
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
                yield ": heartbeat\n\n"

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
        if chat_request.model and not chat_request.base_url and not chat_request.api_key:
            chat_request.model, chat_request.base_url, chat_request.api_key = resolve_system_runtime_config(chat_request.model)
        runtime = get_tool_runtime() if chat_request.tool_mode == "auto" else get_tool_runtime().scoped([])
        chunks = runtime.stream(
            chat_request.text,
            history=chat_request.context,
            role_id=chat_request.role_id,
            model=chat_request.model or "",
            base_url=chat_request.base_url or "",
            api_key=chat_request.api_key or "",
            thinking_mode=chat_request.resolved_thinking_mode(),
            request_id=request_id,
        )
        async for event in _stream_sse_events(
                chunks,
                http_request,
                max(settings.SSE_HEARTBEAT_INTERVAL, 0.1),
                request_id=request_id,
                context_id=chat_request.context_id,
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

