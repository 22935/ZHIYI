"""
本地语音识别服务：sherpa-onnx + paraformer 中文小模型（CPU 离线推理）。

设计边界：
- 不依赖任何云密钥——Electron 里的浏览器在线识别服务不可用，
  这是桌面 Companion 语音输入的唯一可靠兜底；
- 模型懒加载：首次请求才加载（int8 模型约 80MB，冷启动约 7s），
  进程内单例复用；缺模型 / 缺依赖时明确报错，不假装识别；
- 解码在线程池执行（实测 RTF≈0.08，2 线程足够），不阻塞事件循环。
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_AGENT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = _AGENT_ROOT / "data" / "models" / "paraformer-zh-small"
TARGET_SAMPLE_RATE = 16000


def _resample_to_16k(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """任意采样率 → 16kHz 的线性插值重采样（浏览器端通常已重采样，这里只是兜底）。"""
    if sample_rate == TARGET_SAMPLE_RATE or samples.size == 0:
        return samples
    duration = samples.size / float(sample_rate)
    target_size = max(1, int(round(duration * TARGET_SAMPLE_RATE)))
    source_index = np.arange(target_size, dtype=np.float64) * sample_rate / TARGET_SAMPLE_RATE
    return np.interp(source_index, np.arange(samples.size, dtype=np.float64), samples).astype(np.float32)


class LocalASRService:
    """进程内单例。加载结果（含失败原因）缓存，避免每次请求重复探测。"""

    def __init__(self) -> None:
        self._recognizer = None
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()

    def model_dir(self) -> Path:
        configured = (getattr(settings, "LOCAL_ASR_MODEL_DIR", "") or "").strip()
        return Path(configured) if configured else DEFAULT_MODEL_DIR

    def _load_locked(self) -> None:
        if self._recognizer is not None or self._load_error is not None:
            return
        model_dir = self.model_dir()
        model_path = model_dir / "model.int8.onnx"
        tokens_path = model_dir / "tokens.txt"
        if not model_path.is_file() or not tokens_path.is_file():
            self._load_error = (
                f"本地识别模型缺失（{model_dir}）。"
                "需要 model.int8.onnx 与 tokens.txt；可通过 LOCAL_ASR_MODEL_DIR 指定目录。"
            )
            logger.warning(self._load_error)
            return
        try:
            import sherpa_onnx
        except ImportError as exc:  # pragma: no cover - 环境相关
            self._load_error = f"sherpa-onnx 未安装：{exc}"
            logger.warning(self._load_error)
            return
        try:
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=str(model_path),
                tokens=str(tokens_path),
                num_threads=int(getattr(settings, "LOCAL_ASR_NUM_THREADS", 2) or 2),
                debug=False,
            )
            logger.info("本地 ASR 模型已加载: %s", model_dir)
        except Exception as exc:  # noqa: BLE001 - 模型损坏/版本不兼容都要给出人话
            self._load_error = f"本地识别模型加载失败：{exc}"
            logger.warning(self._load_error)

    def availability(self) -> Tuple[bool, Optional[str]]:
        """(可用, 不可用原因)。首次调用触发加载。"""
        with self._lock:
            self._load_locked()
            if self._recognizer is not None:
                return True, None
            return False, self._load_error or "本地识别不可用"

    def reset_for_tests(self) -> None:
        """测试专用：清掉单例状态，允许换目录重载。"""
        with self._lock:
            self._recognizer = None
            self._load_error = None

    async def transcribe(self, pcm: bytes, sample_rate: int = TARGET_SAMPLE_RATE) -> Tuple[Optional[str], Optional[str]]:
        """PCM16LE 单声道 → 文本。返回 (text, error)，二者互斥（空文本不算错误）。"""
        with self._lock:
            self._load_locked()
            recognizer = self._recognizer
            error = self._load_error
        if recognizer is None:
            return None, error or "本地识别不可用"
        if not pcm or len(pcm) < 2:
            return None, "音频数据为空"

        def decode() -> str:
            samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
            samples = _resample_to_16k(samples, sample_rate)
            stream = recognizer.create_stream()
            stream.accept_waveform(TARGET_SAMPLE_RATE, samples)
            recognizer.decode_stream(stream)
            return stream.result.text.strip()

        try:
            text = await asyncio.get_running_loop().run_in_executor(None, decode)
        except Exception as exc:  # noqa: BLE001
            return None, f"识别失败：{exc}"
        return (text or None), None


local_asr_service = LocalASRService()
