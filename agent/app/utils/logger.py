"""Central logging configuration with production JSON and mandatory redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

from app.observability.context import current_task_id, current_trace_id, current_workflow_id

_configured_mode: str | None = None
_REDACTIONS = (
    re.compile(r"(?i)(authorization|cookie|x-internal-service-token|api[-_ ]?key|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
)


def redact(value: str) -> str:
    result = value
    for pattern in _REDACTIONS:
        result = pattern.sub("[REDACTED]", result)
    return result


class RedactingTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.trace_id = current_trace_id() or "no-trace"
        record.workflow_id = current_workflow_id() or "-"
        record.task_id = current_task_id() or "-"
        return redact(super().format(record))


class KinlinJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        exception = self.formatException(record.exc_info) if record.exc_info else ""
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": "kinlin-ai-service",
            "trace_id": current_trace_id(),
            "workflow_id": current_workflow_id(),
            "task_id": current_task_id(),
            "message": redact(record.getMessage()),
            "exception": redact(exception),
            "logger": record.name,
        }
        for field in ("http_method", "path", "status", "duration_ms", "user_id", "upstream_status"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(*, json_format: bool, level: int = logging.INFO) -> None:
    global _configured_mode
    mode = "json" if json_format else "text"
    if _configured_mode == mode:
        return
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if json_format:
        handler.setFormatter(KinlinJsonFormatter())
    else:
        handler.setFormatter(RedactingTextFormatter(
            "%(asctime)s - %(levelname)s - [%(trace_id)s] [%(workflow_id)s/%(task_id)s] [%(name)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root.addHandler(handler)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    _configured_mode = mode


def setup_logger(name: str = "federal_hub", log_file: str = "", level: int = logging.INFO):
    if _configured_mode is None:
        configure_logging(json_format=False, level=level)
    return logging.getLogger(name)


def get_logger(name: str | None = None):
    return logging.getLogger(f"federal_hub.{name}" if name else "federal_hub")
