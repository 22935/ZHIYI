"""真 hands 服务的 chat 工具链端到端测试。

子进程 = node tsx 跑 apps/agentOS/src/hands 独立服务（配置镜像 persistent_runtime.start_hands），
调用侧 = HandsHttpTransport + LocalRuntimeClient + LocalRuntimeToolExecutor +
ChatToolCatalog + AgentsToolRuntime 完整 chat 链。每个工具执行在 hands 账本
（dataDir/ledger.jsonl）落一行，收据 checksum 可对账。
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from adapters.hands_http import HandsHttpTransport
from adapters.local_runtime import LocalRuntimeClient
from app.tools.chat_catalog import ChatToolCatalog
from app.tools.local_runtime import LocalRuntimeToolExecutor
from app.tools.permissions import ApprovalDecision, ChatPermissionService
from app.tools.runtime import ToolInvocationContext
from components.resource.domain.runtime_health import ResourceHealthMonitor
from components.resource.infrastructure.health_store import InMemoryResourceHealthStore
from components.resource.runtime.local_runtime import (
    LocalRuntimeHealthProjector,
    LocalRuntimeResourceConfig,
    ensure_local_runtime_resource,
)
from components.resource.application.resource_plane import ResourcePlane
from components.resource.infrastructure.runtime_store import InMemoryResourceStore
from contracts.local_runtime import LocalRuntimeAuthorizationRef

pytestmark = pytest.mark.skipif(os.name != "nt", reason="hands 执行基座依赖 Windows Job/koffi")

HANDS_ROOT = Path(__file__).resolve().parents[2] / "agentOS" / "src" / "hands"
RESOURCE_ID = "chat-hands-e2e-runtime"
CREDENTIAL_ID = "chat-hands-e2e-credential"
CREDENTIAL_SECRET = "chat-hands-e2e-secret"
WORKSPACE_ID = "chat-hands-e2e-workspace"
GRANT_ID = "chat-hands-e2e-grant"


def _node_launch() -> list[str] | None:
    node = shutil.which("node")
    tsx = HANDS_ROOT / "node_modules" / "tsx" / "dist" / "cli.mjs"
    tsconfig = HANDS_ROOT / "tsconfig.json"
    service_main = HANDS_ROOT / "hands" / "service-main.ts"
    if node is None or not tsx.is_file() or not service_main.is_file():
        return None
    return [node, str(tsx), "--tsconfig", str(tsconfig), str(service_main)]


def _spawn_hands(tmp_path: Path):
    """按 persistent_runtime.start_hands 的同款配置起真 hands 服务，返回 (process, port, 句柄)。"""
    launch = _node_launch()
    if launch is None:
        pytest.skip("node/tsx not available for hands service")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger_dir = tmp_path / "hands-ledger"
    ledger_dir.mkdir()
    (tmp_path / "hands-keys.json").write_text(
        json.dumps({"credentials": [{"credentialId": CREDENTIAL_ID, "secret": CREDENTIAL_SECRET}]}),
        encoding="utf-8")
    (tmp_path / "hands-grants.json").write_text(json.dumps({"grants": [{
        "grantId": GRANT_ID, "workspaceId": WORKSPACE_ID, "canonicalRoot": str(workspace),
        "capabilities": ["fs.list", "fs.patch", "fs.read", "fs.write", "shell.exec"],
        "allowedCallers": [CREDENTIAL_ID], "revoked": False,
    }]}), encoding="utf-8")
    config_path = tmp_path / "hands-service.json"
    config_path.write_text(json.dumps({
        "workspaceRoot": str(workspace), "credentialsFile": str(tmp_path / "hands-keys.json"),
        "grantsFile": str(tmp_path / "hands-grants.json"), "dataDir": str(ledger_dir),
        "host": "127.0.0.1", "port": 0, "confinement": "none", "dynamicWorkspaces": True,
    }), encoding="utf-8")
    stdout_path = tmp_path / "hands-stdout.log"
    creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    process = subprocess.Popen(
        [*launch, "--config", str(config_path)],
        cwd=str(HANDS_ROOT),
        env={**os.environ, "TSX_TSCONFIG_PATH": str(HANDS_ROOT / "tsconfig.json")},
        stdout=open(stdout_path, "w", encoding="utf-8"),
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creationflags,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"hands service exited before READY: {process.returncode}")
        try:
            for line in stdout_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("READY "):
                    port = int(json.loads(line[len("READY "):])["port"])
                    return process, port, workspace, ledger_dir
        except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError):
            pass
        time.sleep(0.1)
    process.kill()
    raise AssertionError("hands service did not report READY within 30s")


def _stop_hands(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _register_resource(plane, address: str):
    """先注册资源再建传输：hands health() 会向 credential_provider 查注册画像。"""
    return ensure_local_runtime_resource(plane, LocalRuntimeResourceConfig(
        resource_id=RESOURCE_ID, owner_scope="chat-hands-e2e",
        execution_endpoint=address, credential_id=CREDENTIAL_ID,
        credential_secret=CREDENTIAL_SECRET, shell_exec_enabled=True,
    ))


def _chat_stack(plane, transport, registered, permission_service=None):
    executor = LocalRuntimeToolExecutor(
        resource_plane=plane, client=LocalRuntimeClient(transport),
        health_projector=LocalRuntimeHealthProjector(plane, RESOURCE_ID),
        health_transport=transport, resource_id=registered.profile.runtime_id,
        authorization=LocalRuntimeAuthorizationRef(grantId=GRANT_ID, workspaceId=WORKSPACE_ID),
    )
    catalog = ChatToolCatalog(
        local_runtime_executor=executor, legacy_terminal_enabled=False,
        permission_service=permission_service,
    )
    return executor, catalog


def _ledger_records(ledger_dir: Path) -> list[dict]:
    path = ledger_dir / "ledger.jsonl"
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _ledger_receipts(ledger_dir: Path) -> list[dict]:
    return [record["receipt"] for record in _ledger_records(ledger_dir) if record.get("t") == "receipt"]


def _wait_for_receipt(ledger_dir: Path, predicate, timeout: float = 5.0) -> list[dict]:
    """账本落盘与事件总线异步，终态断言前轮询等待。"""
    deadline = time.monotonic() + timeout
    receipts = _ledger_receipts(ledger_dir)
    while time.monotonic() < deadline:
        if any(predicate(receipt) for receipt in receipts):
            return receipts
        time.sleep(0.1)
        receipts = _ledger_receipts(ledger_dir)
    return receipts


@pytest.mark.asyncio
async def test_chat_tools_roundtrip_and_receipt_ledger_on_real_hands(tmp_path: Path):
    process, port, workspace, ledger_dir = _spawn_hands(tmp_path)
    transport = None
    try:
        plane = ResourcePlane(
            store=InMemoryResourceStore(),
            health_monitor=ResourceHealthMonitor(
                store=InMemoryResourceHealthStore(), heartbeat_timeout=timedelta(seconds=5)),
        )
        address = f"http://127.0.0.1:{port}/v1/executions"
        registered = _register_resource(plane, address)
        transport = HandsHttpTransport(
            resource_id=RESOURCE_ID, address=address,
            credential_provider=plane, timeout_seconds=10,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"hands exited early: {process.returncode}")
            try:
                health = await transport.health()
                if "fs.write" in health["capabilities"]:
                    break
            except Exception:
                await asyncio.sleep(0.1)
        else:
            raise AssertionError("hands transport did not become healthy")
        _, catalog = _chat_stack(plane, transport, registered)
        from app.tools.runtime import AgentsToolRuntime
        runtime = AgentsToolRuntime(catalog=catalog)

        write = await asyncio.wait_for(
            runtime.execute("write_file", {"path": "hello.txt", "content": "alpha\nbeta\n", "overwrite": False}),
            timeout=30)
        assert write.text and json.loads(write.text)["ok"] is True

        # overwrite:False 映射为 hands createIfAbsent 守卫：拒绝覆盖已存在文件。
        # chat 契约把工具失败折成 ok:false 载荷回给模型，而不是抛异常。
        refused = await asyncio.wait_for(
            runtime.execute("write_file", {"path": "hello.txt", "content": "clobber", "overwrite": False}),
            timeout=30)
        refused_payload = json.loads(refused.text)
        assert refused_payload["ok"] is False
        assert refused_payload["error"] == "FS_NOT_OBSERVED"
        still = await asyncio.wait_for(runtime.execute("read_file", {"path": "hello.txt"}), timeout=30)
        assert json.loads(still.text)["data"]["result"]["content"] == "alpha\nbeta\n"

        read = await asyncio.wait_for(runtime.execute("read_file", {"path": "hello.txt"}), timeout=30)
        assert json.loads(read.text)["data"]["result"]["content"] == "alpha\nbeta\n"

        patched = await asyncio.wait_for(runtime.execute("patch_file", {
            "path": "hello.txt", "patch": "@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n",
        }), timeout=30)
        assert json.loads(patched.text)["ok"] is True
        final = await asyncio.wait_for(runtime.execute("read_file", {"path": "hello.txt"}), timeout=30)
        assert json.loads(final.text)["data"]["result"]["content"] == "alpha\ngamma\n"
        listed = await asyncio.wait_for(runtime.execute("list_files", {"path": "."}), timeout=30)
        assert any(item["path"] == "hello.txt"
                   for item in json.loads(listed.text)["data"]["result"]["entries"])
        assert (workspace / "hello.txt").read_text(encoding="utf-8") == "alpha\ngamma\n"

        # 工作区外路径在 hands 沙箱被拒，chat 工具不得返回成功。
        escaped = await asyncio.wait_for(runtime.execute("read_file", {"path": "../outside.txt"}), timeout=30)
        assert json.loads(escaped.text)["ok"] is False

        # 每个工具执行在账本落收据行（claim/state/receipt），checksum 可对账。
        receipts = _wait_for_receipt(ledger_dir, lambda receipt: str(
            receipt.get("idempotencyKey", "")).endswith(":patch-write"))
        assert len(receipts) >= 6
        assert all(receipt["status"] in {"completed", "failed"} for receipt in receipts)
        assert all(receipt.get("checksum") for receipt in receipts)
        # patch 读改写 = fs.read + fs.write 两张收据，幂等键带派生后缀。
        assert any(receipt["capabilityId"] == "fs.read"
                   and str(receipt.get("idempotencyKey", "")).endswith(":patch-read")
                   for receipt in receipts)
        assert any(str(receipt.get("idempotencyKey", "")).endswith(":patch-write")
                   for receipt in receipts)
        assert "terminal" not in catalog.TOOL_NAMES
    finally:
        if transport is not None:
            await transport.aclose()
        _stop_hands(process)


@pytest.mark.asyncio
async def test_chat_run_command_streams_and_cancels_on_real_hands(tmp_path: Path):
    process, port, workspace, ledger_dir = _spawn_hands(tmp_path)
    transport = None
    try:
        plane = ResourcePlane(
            store=InMemoryResourceStore(),
            health_monitor=ResourceHealthMonitor(
                store=InMemoryResourceHealthStore(), heartbeat_timeout=timedelta(seconds=5)),
        )
        address = f"http://127.0.0.1:{port}/v1/executions"
        registered = _register_resource(plane, address)
        transport = HandsHttpTransport(
            resource_id=RESOURCE_ID, address=address,
            credential_provider=plane, timeout_seconds=10,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(f"hands exited early: {process.returncode}")
            try:
                health = await transport.health()
                if "shell.exec" in health["capabilities"]:
                    break
            except Exception:
                await asyncio.sleep(0.1)
        else:
            raise AssertionError("shell-enabled hands transport did not become healthy")
        executor, catalog = _chat_stack(plane, transport, registered, permission_service=ChatPermissionService())
        assert "run_command" in catalog.TOOL_NAMES

        permission = catalog.permission_service
        queue = asyncio.Queue()
        context = ToolInvocationContext(
            catalog, frozenset({"run_command"}),
            session_id="chat-hands-session", request_id="chat-hands-request",
            permission_event_queue=queue,
        )
        task = asyncio.create_task(context.invoke(
            "run_command", {"mode": "shell", "command": "echo chat-hands-e2e", "cwd": "."},
            call_id="chat-hands-call",
        ))
        event, payload = await asyncio.wait_for(queue.get(), timeout=5)
        assert event == "approval_required"
        await permission.resolve(
            payload["approval"]["approvalId"], decision=ApprovalDecision.ALLOW_ONCE,
            session_id="chat-hands-session", invocation_id="chat-hands-call",
            capability_id="shell.exec", relative_path=".",
        )
        result = json.loads(await asyncio.wait_for(task, timeout=30))
        assert result["ok"] is True
        assert "chat-hands-e2e" in result["data"]["terminal"]["stdout"]
        assert result["data"]["terminal"]["exitCode"] == 0

        cancel_queue = asyncio.Queue()
        cancel_context = ToolInvocationContext(
            catalog, frozenset({"run_command"}),
            session_id="chat-hands-cancel-session", request_id="chat-hands-cancel",
            permission_event_queue=cancel_queue,
        )
        cancel_task = asyncio.create_task(cancel_context.invoke(
            "run_command", {"mode": "shell", "command": "ping 127.0.0.1 -n 30", "cwd": "."},
            call_id="chat-hands-cancel-call",
        ))
        cancel_event, cancel_payload = await asyncio.wait_for(cancel_queue.get(), timeout=5)
        assert cancel_event == "approval_required"
        await permission.resolve(
            cancel_payload["approval"]["approvalId"], decision=ApprovalDecision.ALLOW_ONCE,
            session_id="chat-hands-cancel-session", invocation_id="chat-hands-cancel-call",
            capability_id="shell.exec", relative_path=".",
        )
        await asyncio.wait_for(cancel_queue.get(), timeout=5)  # approval_resolved
        started_event, _ = await asyncio.wait_for(cancel_queue.get(), timeout=10)
        assert started_event == "execution_started"
        assert await executor.cancel("chat-hands-cancel") is True
        cancelled = json.loads(await asyncio.wait_for(cancel_task, timeout=15))
        assert cancelled["ok"] is False
        assert cancelled["error"] == "EXECUTION_CANCELLED"

        records = _ledger_records(ledger_dir)
        cancelled_receipts = _wait_for_receipt(
            ledger_dir, lambda receipt: receipt["status"] == "cancelled")
        assert any(receipt["status"] == "cancelled" for receipt in cancelled_receipts)
        # 取消协议的账本痕迹：markCancelRequested 落 cancel-requested 行。
        assert any(record.get("t") == "cancel-requested" for record in records)

        # DENY：审批拒绝后工具不执行，hands 账本无新收据（对齐已删 python shell E2E 的覆盖）。
        deny_queue = asyncio.Queue()
        deny_context = ToolInvocationContext(
            catalog, frozenset({"run_command"}),
            session_id="chat-hands-deny-session", request_id="chat-hands-deny",
            permission_event_queue=deny_queue,
        )
        deny_task = asyncio.create_task(deny_context.invoke(
            "run_command", {"mode": "shell", "command": "echo should-never-run", "cwd": "."},
            call_id="chat-hands-deny-call",
        ))
        deny_event, deny_payload = await asyncio.wait_for(deny_queue.get(), timeout=5)
        assert deny_event == "approval_required"
        await permission.resolve(
            deny_payload["approval"]["approvalId"], decision=ApprovalDecision.DENY,
            session_id="chat-hands-deny-session", invocation_id="chat-hands-deny-call",
            capability_id="shell.exec", relative_path=".",
        )
        denied = json.loads(await asyncio.wait_for(deny_task, timeout=10))
        assert denied["ok"] is False
        assert denied["error"] != "EXECUTION_CANCELLED"
        after_deny = len(_ledger_receipts(ledger_dir))
        await asyncio.sleep(0.5)
        assert len(_ledger_receipts(ledger_dir)) == after_deny  # 无新执行落账
    finally:
        if transport is not None:
            await transport.aclose()
        _stop_hands(process)
