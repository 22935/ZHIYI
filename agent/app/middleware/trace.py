from app.observability.context import accepted_or_new_trace_id, reset_trace_id, set_trace_id


class TraceIdMiddleware:
    """Pure ASGI middleware keeps ContextVar state alive for the complete SSE stream."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        values = [value.decode("latin-1") for name, value in scope.get("headers", [])
                  if name.lower() == b"x-trace-id"]
        trace_id = accepted_or_new_trace_id(values[0] if len(values) == 1 else None)
        token = set_trace_id(trace_id)

        async def send_with_trace(message):
            if message["type"] == "http.response.start":
                headers = [(name, value) for name, value in message.get("headers", [])
                           if name.lower() != b"x-trace-id"]
                headers.append((b"x-trace-id", trace_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            reset_trace_id(token)
