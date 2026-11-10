"""loopback 工具服务：固定路由、HMAC 验证、时间窗与 nonce 防重放。"""
import hmac
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, BoundedSemaphore
from .signing import build_resource_signature


def serve():
    runtime_id = os.environ.pop("AGENTOS_TOOL_RUNTIME_ID")
    credential_id = os.environ.pop("AGENTOS_TOOL_CREDENTIAL_ID")
    secret = os.environ.pop("AGENTOS_TOOL_SECRET")
    capability = os.environ.pop("AGENTOS_TOOL_CAPABILITY")
    workspace = Path("workspace").resolve()
    workspace.mkdir(exist_ok=True)
    nonces = {}
    auth_lock = Lock()
    execution_slot = BoundedSemaphore(1)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # 不将签名、正文和源文档写入 HTTP 访问日志。

        def reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"runtimeId": runtime_id, "status": "ok"})
            self.reply(404, {"error": "NOT_FOUND"})

        def do_POST(self):
            if self.path != "/execute":
                return self.reply(404, {"error": "NOT_FOUND"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_048_576 or self.headers.get("Transfer-Encoding"):
                    return self.reply(413, {"error": "REQUEST_TOO_LARGE"})
                self.connection.settimeout(10)
                body = self.rfile.read(length)
                timestamp = int(self.headers.get("X-Resource-Timestamp", "0"))
                nonce = self.headers.get("X-Resource-Nonce", "")
                now = time.time()
                expected = build_resource_signature(secret, method="POST", path="/execute", timestamp=timestamp, nonce=nonce, body=body)
                with auth_lock:
                    for old in list(nonces):
                        if nonces[old] < now - 60:
                            del nonces[old]
                    if (len(body) != length or abs(now - timestamp) > 60 or not 16 <= len(nonce) <= 160 or nonce in nonces
                        or len(nonces) >= 10000 or self.headers.get("X-Resource-Credential") != credential_id
                        or not hmac.compare_digest(expected, self.headers.get("X-Resource-Signature", ""))):
                        return self.reply(401, {"error": "SIGNATURE_INVALID"})
                    nonces[nonce] = now
                request = json.loads(body)
                if request.get("capability") != capability:
                    return self.reply(422, {"error": "CAPABILITY_NOT_SUPPORTED"})
                worker = {"workspace": str(workspace), "capability": capability, "input": request.get("input", {})}
                if not execution_slot.acquire(blocking=False):
                    return self.reply(422, {"output": {"error": "TOOL_BUSY"}})
                try:
                    process = subprocess.run([sys.executable, "-m", "agentos_local_tools.worker"], input=json.dumps(worker),
                        capture_output=True, text=True, timeout=30, shell=False, encoding="utf-8")
                    result = json.loads(process.stdout) if process.returncode == 0 else {"output": {"error": "TOOL_PROCESS_FAILED"}}
                except subprocess.TimeoutExpired:
                    result = {"output": {"error": "TOOL_TIMEOUT"}}
                finally:
                    execution_slot.release()
                # 明确失败不能伪装成成功 AgentOutput，否则 ACG 会把失败步骤记成完成。
                self.reply(422 if "error" in result["output"] else 200, result)
            except (ValueError, TypeError, KeyError):
                self.reply(422, {"error": "INVALID_TOOL_INPUT"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    Path("ready.json").write_text(json.dumps({"port": server.server_port, "runtimeId": runtime_id}), encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    serve()
