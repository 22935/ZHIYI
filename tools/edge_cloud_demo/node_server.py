"""HTTP worker used by terminal_node.py and edge_node.py."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

from common import read_json, signed_json_request, verify_signed_headers, write_json


class NodeState:
    def __init__(self, name: str) -> None:
        self.name = name
        self.credential_id = ""
        self.secret = ""
        self.observation_url = ""
        self.sequence = 0
        self.failed = False
        self.nonces: set[str] = set()
        self.lock = threading.RLock()


def serve(name: str, port: int) -> None:
    state = NodeState(name)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if self.path == "/health":
                write_json(self, 200, {"status": "ok", "node": state.name})
                return
            write_json(self, 404, {"error": "not found"})

        def do_POST(self) -> None:
            try:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/configure":
                    payload = read_json_from_bytes(body)
                    with state.lock:
                        state.credential_id = str(payload["credentialId"])
                        state.secret = str(payload["secret"])
                        state.observation_url = str(payload.get("observationUrl", ""))
                    write_json(self, 200, {"configured": True, "node": state.name})
                    return
                if self.path == "/control/fail":
                    payload = read_json_from_bytes(body)
                    state.failed = bool(payload.get("failed", True))
                    write_json(self, 200, {"failed": state.failed})
                    return
                if self.path == "/emit-observation":
                    with state.lock:
                        state.sequence += 1
                        result = signed_json_request(
                            state.observation_url,
                            credential_id=state.credential_id,
                            secret=state.secret,
                            payload={
                                "availableSlots": 1,
                                "observationSequence": state.sequence,
                                "utilization": 0.0,
                                "latencyMs": 12,
                            },
                        )
                    write_json(self, result[0], result[1])
                    return
                if self.path.rstrip("/") not in {"/execute", "/cloud-execute"}:
                    write_json(self, 404, {"error": "not found"})
                    return
                with state.lock:
                    valid, reason = verify_signed_headers(
                        self,
                        credential_id=state.credential_id,
                        secret=state.secret,
                        body=body,
                        consumed_nonces=state.nonces,
                    )
                    failed = state.failed
                if not valid:
                    write_json(self, 401, {"error": reason})
                    return
                if failed:
                    write_json(self, 503, {"error": f"{state.name} unavailable"})
                    return
                payload = read_json_from_bytes(body)
                write_json(self, 200, {
                    "output": {
                        "node": state.name,
                        "signatureVerified": True,
                        "input": payload.get("input", {}),
                    },
                    "summary": f"executed by {state.name}",
                })
            except Exception as error:
                write_json(self, 400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()


def read_json_from_bytes(body: bytes) -> dict:
    import json

    value = json.loads(body or b"{}")
    if not isinstance(value, dict):
        raise ValueError("request JSON must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    serve(args.name, args.port)


if __name__ == "__main__":
    main()
