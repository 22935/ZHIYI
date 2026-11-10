"""本地 ASR：路由行为 + 服务层纯逻辑。真模型集成见文件末尾的可选用例。"""
from __future__ import annotations

import struct

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.asr as asr_api
from app.services import localasrservice
from app.services.localasrservice import LocalASRService, _resample_to_16k


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(asr_api.router, prefix="/ai")
    return TestClient(app)


def _silence_pcm(seconds: float, sample_rate: int = 16000) -> bytes:
    samples = np.zeros(int(seconds * sample_rate), dtype=np.int16)
    return samples.tobytes()


class _FakeRecognizer:
    def __init__(self, text: str = "你好知宝"):
        self.text = text
        self.calls: list[np.ndarray] = []

    def create_stream(self):
        return self

    def accept_waveform(self, sample_rate, samples):
        self.calls.append(np.asarray(samples))

    def decode_stream(self, stream):
        pass

    @property
    def result(self):
        class _Result:
            text = self.text
        return _Result()


def test_resample_is_identity_at_16k_and_scales_other_rates():
    samples = np.ones(16000, dtype=np.float32)
    assert _resample_to_16k(samples, 16000) is samples
    doubled = _resample_to_16k(np.ones(48000, dtype=np.float32), 48000)
    assert doubled.size == 16000


def test_availability_reports_missing_model_without_raising(monkeypatch, tmp_path):
    service = LocalASRService()
    monkeypatch.setattr(service, "model_dir", lambda: tmp_path / "nope")
    ok, reason = service.availability()
    assert ok is False
    assert "缺失" in reason


def test_transcribe_returns_text_from_engine(monkeypatch, tmp_path):
    service = LocalASRService()
    engine = _FakeRecognizer("今天天气不错")
    monkeypatch.setattr(service, "model_dir", lambda: tmp_path)
    monkeypatch.setattr(localasrservice, "DEFAULT_MODEL_DIR", tmp_path)
    # 跳过真实加载：直接注入引擎并标记已加载成功。
    service._recognizer = engine
    text, error = _run(service.transcribe(_silence_pcm(0.5)))
    assert error is None
    assert text == "今天天气不错"
    # PCM16 归一化后幅值在 [-1, 1]，静音即全 0。
    assert float(np.max(np.abs(engine.calls[0]))) == 0.0


def test_transcribe_resamples_non_16k_input(monkeypatch):
    service = LocalASRService()
    engine = _FakeRecognizer("重采样")
    service._recognizer = engine
    text, error = _run(service.transcribe(_silence_pcm(1.0, sample_rate=48000), sample_rate=48000))
    assert error is None and text == "重采样"
    # 1s @ 48k 重采样后应接近 16000 个采样点。
    assert 15900 <= engine.calls[0].size <= 16100


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_endpoint_rejects_bad_input(client, monkeypatch):
    # 引擎可用，但请求体为空。
    asr_api.local_asr_service._recognizer = _FakeRecognizer()
    assert client.post("/ai/voice/asr", content=b"").status_code == 400
    assert client.post("/ai/voice/asr?sample_rate=123", content=b"\x00\x00").status_code == 400
    # 引擎不可用 → 503 + 人话原因。
    class _Unavailable:
        def availability(self):
            return False, "本地识别模型缺失（x）"

        def transcribe(self, *args, **kwargs):
            raise AssertionError("should not be called")

    monkeypatch.setattr(asr_api, "local_asr_service", _Unavailable())
    response = client.post("/ai/voice/asr", content=b"\x00\x00")
    assert response.status_code == 503
    assert "缺失" in response.json()["detail"]


def test_endpoint_returns_text_and_metrics(client):
    class _Ok:
        def availability(self):
            return True, None

        async def transcribe(self, pcm, sample_rate=16000):
            return "知宝你好", None

    original = asr_api.local_asr_service
    asr_api.local_asr_service = _Ok()
    try:
        response = client.post("/ai/voice/asr", content=_silence_pcm(0.25))
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "知宝你好"
        assert body["duration_ms"] == 250
        assert body["decode_ms"] >= 0
    finally:
        asr_api.local_asr_service = original


def test_endpoint_rejects_oversized_audio(client):
    asr_api.local_asr_service._recognizer = _FakeRecognizer()
    huge = b"\x00\x00" * (asr_api.MAX_AUDIO_BYTES // 2 + 1)
    assert client.post("/ai/voice/asr", content=huge).status_code == 413


@pytest.mark.skipif(
    not (localasrservice.DEFAULT_MODEL_DIR / "model.int8.onnx").is_file(),
    reason="本地 paraformer 模型未下载",
)
def test_real_model_transcribes_known_audio():
    """真模型冒烟：模型目录下的 test.wav 是官方样例，识别文本非空即通过。"""
    import wave

    service = LocalASRService()
    with wave.open(str(localasrservice.DEFAULT_MODEL_DIR / "test.wav")) as handle:
        assert handle.getframerate() == 16000
        pcm = handle.readframes(handle.getnframes())
    text, error = _run(service.transcribe(pcm))
    assert error is None
    assert text and len(text) > 4
