import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.middleware.trace import TraceIdMiddleware
from app.observability.context import current_trace_id, execution_context
from app.utils.logger import KinlinJsonFormatter


def build_app():
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/trace")
    async def trace():
        return {"trace_id": current_trace_id()}

    @app.get("/stream")
    async def stream():
        async def events():
            yield f"data: {current_trace_id()}\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")

    return app


def test_trace_generation_preservation_replacement_and_sse():
    client = TestClient(build_app())
    generated = client.get("/trace")
    valid = str(uuid.uuid4())
    preserved = client.get("/trace", headers={"X-Trace-Id": valid})
    invalid = client.get("/trace", headers={"X-Trace-Id": "bad-value"})
    too_long = client.get("/trace", headers={"X-Trace-Id": "a" * 200})
    stream = client.get("/stream", headers={"X-Trace-Id": valid})

    assert generated.headers["X-Trace-Id"] == generated.json()["trace_id"]
    assert preserved.headers["X-Trace-Id"] == valid == preserved.json()["trace_id"]
    assert invalid.headers["X-Trace-Id"] != "bad-value"
    assert too_long.headers["X-Trace-Id"] != "a" * 200
    assert valid in stream.text and stream.headers["X-Trace-Id"] == valid


def test_concurrent_requests_do_not_mix_trace_contexts():
    values = [str(uuid.uuid4()) for _ in range(16)]

    def request(value):
        with TestClient(build_app()) as client:
            response = client.get("/trace", headers={"X-Trace-Id": value})
            return response.json()["trace_id"], response.headers["X-Trace-Id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(request, values))

    assert results == [(value, value) for value in values]


def test_json_formatter_has_fixed_fields_and_redacts_credentials():
    formatter = KinlinJsonFormatter()
    secret_message = "Authorization=Bearer " + "eyJ" + "abc.def.ghi" + " api_key=sk" + "-privatevalue"
    record = logging.LogRecord("test", logging.ERROR, __file__, 1, secret_message, (), None)
    with execution_context(workflow_id="workflow-1", task_id="task-1"):
        payload = json.loads(formatter.format(record))

    assert {"timestamp", "level", "service", "trace_id", "workflow_id", "task_id", "message", "exception"} <= payload.keys()
    assert payload["workflow_id"] == "workflow-1"
    assert payload["task_id"] == "task-1"
    assert "privatevalue" not in payload["message"]
    assert "abc.def.ghi" not in payload["message"]
