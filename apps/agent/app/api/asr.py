"""
本地语音识别 API：POST /ai/voice/asr。

输入：raw PCM16LE 单声道（请求体二进制），默认 16kHz，可用 query 参数覆盖；
输出：{"text": "...", "duration_ms": ..., "decode_ms": ...}。

模型 / 依赖缺失返回 503，前端据此如实降级，绝不返回假识别结果。
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from app.services.localasrservice import TARGET_SAMPLE_RATE, local_asr_service

router = APIRouter()

# 60s @ 16kHz 单声道 PCM16；再长就该走流式方案而不是整段上传。
MAX_AUDIO_BYTES = TARGET_SAMPLE_RATE * 2 * 60
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 96000


@router.post("/voice/asr")
async def recognize_speech(request: Request, sample_rate: int = TARGET_SAMPLE_RATE) -> dict:
    available, reason = local_asr_service.availability()
    if not available:
        raise HTTPException(status_code=503, detail=reason)

    if not MIN_SAMPLE_RATE <= sample_rate <= MAX_SAMPLE_RATE:
        raise HTTPException(status_code=400, detail=f"sample_rate 需在 {MIN_SAMPLE_RATE}~{MAX_SAMPLE_RATE} 之间")

    pcm = await request.body()
    if not pcm:
        raise HTTPException(status_code=400, detail="请求体为空：需要 PCM16LE 单声道音频")
    if len(pcm) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="音频过长（上限 60 秒）")

    started = time.perf_counter()
    text, error = await local_asr_service.transcribe(pcm, sample_rate)
    if error:
        status = 400 if "为空" in error else 500
        raise HTTPException(status_code=status, detail=error)

    return {
        "text": text or "",
        "duration_ms": round(len(pcm) / 2 / sample_rate * 1000),
        "decode_ms": round((time.perf_counter() - started) * 1000),
    }
