"""应用层 OpenAI 兼容端点的标准库 JSON HTTP 传输。"""

from __future__ import annotations

import asyncio
from support.async_tasks import await_owned, await_settled, run_blocking
import json
from collections.abc import AsyncIterator, Callable
from threading import RLock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class HttpTransportError(RuntimeError):
    """表示不暴露请求或响应正文的 HTTP 传输稳定错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RotatingKeyProvider:
    """保存应用层当前密钥并支持原子轮换，不向调用方返回密钥正文。"""

    def __init__(self, initial_key: str | None = None) -> None:
        self._key = initial_key.strip() if initial_key else None
        self._revision = 0
        self._lock = RLock()

    def current_key(self) -> str | None:
        """返回仅供传输层立即写入请求头的当前密钥。"""
        with self._lock:
            return self._key

    def rotate(self, key: str | None) -> int:
        """原子替换当前密钥并返回无敏感信息的修订号。"""
        with self._lock:
            self._key = key.strip() if key else None
            self._revision += 1
            return self._revision


class HttpJsonTransport:
    """以显式基地址、密钥和超时调用 JSON API 的应用层传输。

    密钥仅保存在传输对象内，并写入 ``Authorization`` Header；`idempotency_key`
    仅写入 HTTP Header。二者均不进入 ``CapabilityManifest``、模型消息、运行 State、
    checkpoint、Trace 或响应错误文字。核心 Runtime 只依赖 ``JsonTransport`` 协议，
    不会自行构造该对象或读取环境变量。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        key_provider: RotatingKeyProvider | None = None,
        request_timeout: float = 120.0,
        allow_insecure: bool = False,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        """保存应用层连接配置；默认拒绝明文 HTTP，便于防止密钥误传。"""
        normalized_url = base_url.strip().rstrip("/")
        parsed = urlsplit(normalized_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("HTTP_BASE_URL_INVALID: base_url must be an absolute URL")
        if parsed.scheme != "https" and not allow_insecure:
            raise ValueError("HTTP_BASE_URL_INSECURE: HTTPS is required unless allow_insecure is true")
        if parsed.scheme not in {"https", "http"}:
            raise ValueError("HTTP_BASE_URL_INVALID: only HTTP(S) URLs are supported")
        if request_timeout <= 0:
            raise ValueError("HTTP_TIMEOUT_INVALID: request_timeout must be greater than zero")
        self._base_url = normalized_url
        if api_key is not None and key_provider is not None:
            raise ValueError("HTTP_KEY_CONFIGURATION_INVALID: use api_key or key_provider, not both")
        self._api_key = api_key.strip() if api_key else None
        self._key_provider = key_provider
        self._request_timeout = request_timeout
        self._opener = opener

    async def post_json(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """异步提交 JSON；底层标准库阻塞请求在工作线程执行。"""
        return await run_blocking(
            self._post_json_sync,
            path=path,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    async def stream_json(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """读取 OpenAI 兼容 SSE，并在停止消费时关闭底层响应。"""
        opening = asyncio.create_task(asyncio.to_thread(
            self._open_stream_sync,
            path=path,
            payload=payload,
            idempotency_key=idempotency_key,
        ), name="model-stream-open")
        try:
            response = await await_owned(opening)
        except asyncio.CancelledError:
            results = await await_settled(asyncio.gather(opening, return_exceptions=True), propagate_cancel=False)
            if not isinstance(results[0], BaseException):
                await await_settled(asyncio.create_task(run_blocking(results[0].close)))
            raise
        data_lines: list[str] = []
        try:
            while True:
                raw_line = await run_blocking(response.readline)
                if not raw_line:
                    if data_lines:
                        event = self._parse_sse_data(data_lines)
                        if event is not None:
                            yield event
                    return
                try:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError as exc:
                    raise HttpTransportError(
                        "MODEL_RESPONSE_INVALID",
                        "HTTP provider stream is not UTF-8",
                    ) from exc
                if not line:
                    if not data_lines:
                        continue
                    event = self._parse_sse_data(data_lines)
                    data_lines = []
                    if event is None:
                        return
                    yield event
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                await await_settled(asyncio.create_task(run_blocking(close), name="model-stream-close"))

    def _post_json_sync(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        """构造受限请求并映射网络、状态码和 JSON 解析错误。"""
        request = self._request_for(
            path=path,
            payload=payload,
            idempotency_key=idempotency_key,
            accept="application/json",
        )
        try:
            with self._opener(request, timeout=self._request_timeout) as response:
                status_value = getattr(response, "status", None)
                status = int(
                    status_value if status_value is not None else response.getcode()
                )
                raw_response = response.read()
        except HTTPError as exc:
            raise HttpTransportError(
                self._code_for_status(exc.code),
                "HTTP provider returned an error response",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise HttpTransportError(
                "MODEL_TEMPORARY_UNAVAILABLE",
                "HTTP provider connection failed",
            ) from exc
        if status < 200 or status >= 300:
            raise HttpTransportError(
                self._code_for_status(status),
                "HTTP provider returned an error response",
            )
        try:
            parsed = json.loads(raw_response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpTransportError(
                "MODEL_RESPONSE_INVALID",
                "HTTP provider response is not valid JSON",
            ) from exc
        if not isinstance(parsed, dict):
            raise HttpTransportError(
                "MODEL_RESPONSE_INVALID",
                "HTTP provider response must be a JSON object",
            )
        return parsed

    def _open_stream_sync(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
    ) -> Any:
        """建立 SSE 请求，并在交给异步读取器前完成状态码校验。"""
        request = self._request_for(
            path=path,
            payload=payload,
            idempotency_key=idempotency_key,
            accept="text/event-stream",
        )
        try:
            response = self._opener(request, timeout=self._request_timeout)
            status_value = getattr(response, "status", None)
            status = int(status_value if status_value is not None else response.getcode())
        except HTTPError as exc:
            raise HttpTransportError(
                self._code_for_status(exc.code),
                "HTTP provider returned an error response",
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise HttpTransportError(
                "MODEL_TEMPORARY_UNAVAILABLE",
                "HTTP provider connection failed",
            ) from exc
        if status < 200 or status >= 300:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise HttpTransportError(
                self._code_for_status(status),
                "HTTP provider returned an error response",
            )
        return response

    @staticmethod
    def _parse_sse_data(data_lines: list[str]) -> dict[str, Any] | None:
        """解析一个 SSE data 事件；``[DONE]`` 只表示结束，不作为正文返回。"""
        data = "\n".join(data_lines)
        if data == "[DONE]":
            return None
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise HttpTransportError(
                "MODEL_RESPONSE_INVALID",
                "HTTP provider stream event is not valid JSON",
            ) from exc
        if not isinstance(parsed, dict):
            raise HttpTransportError(
                "MODEL_RESPONSE_INVALID",
                "HTTP provider stream event must be a JSON object",
            )
        return parsed

    def _request_for(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
        accept: str,
    ) -> Request:
        """构造请求，并把认证与幂等标识限制在 Header。"""
        url = self._url_for(path)
        try:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise HttpTransportError(
                "HTTP_PAYLOAD_INVALID",
                "HTTP payload is not JSON serializable",
            ) from exc
        headers = {"Accept": accept, "Content-Type": "application/json"}
        api_key = self._key_provider.current_key() if self._key_provider is not None else self._api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if idempotency_key and idempotency_key.strip():
            headers["Idempotency-Key"] = idempotency_key.strip()
        return Request(url=url, data=body, headers=headers, method="POST")

    def _url_for(self, path: str) -> str:
        """仅允许相对路径，避免适配器被请求参数诱导访问其他主机。"""
        normalized_path = path.strip()
        parsed = urlsplit(normalized_path)
        if not normalized_path or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise HttpTransportError(
                "HTTP_PATH_INVALID",
                "HTTP path must be a relative path without query or fragment",
            )
        return f"{self._base_url}/{normalized_path.lstrip('/')}"

    @staticmethod
    def _code_for_status(status: int) -> str:
        """将常见供应商 HTTP 状态映射为模型保护层可识别的稳定错误码。"""
        if status == 429:
            return "MODEL_RATE_LIMITED"
        if status in {408, 504}:
            return "MODEL_TIMEOUT"
        if status >= 500:
            return "MODEL_TEMPORARY_UNAVAILABLE"
        return "MODEL_PROVIDER_FAILED"


__all__ = ["HttpJsonTransport", "HttpTransportError", "RotatingKeyProvider"]
