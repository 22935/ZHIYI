"""Chat-facing adapter for the AgentOS-owned Local Runtime boundary.

This module deliberately contains no filesystem implementation and no transport
construction.  The composition root injects the existing ResourcePlane,
LocalRuntimeClient, health projector, and a server-issued authorization
reference.  Model arguments remain business arguments only.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Awaitable, Callable, Mapping

from adapters.local_runtime import LocalRuntimeClient
from components.resource.runtime.local_runtime import LocalRuntimeHealthTransport, LocalRuntimeHealthProjector
from components.resource.application.resource_plane import ResourcePlane
from contracts.capability import CapabilityInvocation
from contracts.local_runtime import (
    LocalRuntimeAuthorizationRef,
    LocalRuntimeCapability,
    ExecutionSecurityProfile,
    LocalRuntimeExecutionLimits,
)
from contracts.resource import Placement, RuntimeKind

from app.tools.contracts import ToolPayload


TOOL_CAPABILITIES: dict[str, LocalRuntimeCapability] = {
    "read_file": LocalRuntimeCapability.FS_READ,
    "list_files": LocalRuntimeCapability.FS_LIST,
    "write_file": LocalRuntimeCapability.FS_WRITE,
    "patch_file": LocalRuntimeCapability.FS_PATCH,
    "run_command": LocalRuntimeCapability.SHELL_EXEC,
}

_SAFE_RELATIVE_PATH = re.compile(r"^(?![\\/])(?!(?:[A-Za-z]:)).{1,4096}$")

LOGGER = logging.getLogger(__name__)


class LocalRuntimeToolError(RuntimeError):
    """Safe error returned to Chat when the Local Runtime cannot execute."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        activity: dict[str, Any] | None = None,
        terminal: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.activity = activity
        self.terminal = terminal


class LocalRuntimeToolExecutor:
    """Translate Chat tool calls into existing AgentOS capability invocations."""

    def __init__(
        self,
        *,
        resource_plane: ResourcePlane,
        client: LocalRuntimeClient,
        health_projector: LocalRuntimeHealthProjector,
        health_transport: LocalRuntimeHealthTransport,
        resource_id: str,
        authorization: LocalRuntimeAuthorizationRef,
        limits: LocalRuntimeExecutionLimits | None = None,
    ) -> None:
        self.resource_plane = resource_plane
        self.client = client
        self.health_projector = health_projector
        self.health_transport = health_transport
        self.resource_id = str(resource_id).strip()
        self.authorization = authorization
        self.limits = limits or LocalRuntimeExecutionLimits(
            timeoutSeconds=30.0,
            maxStdoutBytes=12_000,
            maxStderrBytes=12_000,
        )
        if not self.resource_id:
            raise ValueError("resource_id must not be empty")
        self._active: dict[str, tuple[str, str, str]] = {}

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        call_id: str,
        request_id: str | None = None,
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> ToolPayload:
        capability = TOOL_CAPABILITIES.get(tool_name)
        if capability is None:
            raise LocalRuntimeToolError("CAPABILITY_NOT_ALLOWED", "Chat file capability is not allowed")
        if not str(call_id or "").strip():
            raise LocalRuntimeToolError("INVOCATION_INVALID", "tool invocation is invalid")
        if tool_name == "run_command":
            forbidden = {
                "securityProfile", "security_profile", "grantId", "workspaceId",
                "resourceId", "endpoint", "credential", "allowedRoot", "allowedPaths",
            }
            if forbidden.intersection(arguments):
                raise LocalRuntimeToolError(
                    "INPUT_FORBIDDEN", "command security and host authority are system-controlled"
                )

        input_payload = self._business_input(tool_name, arguments)
        relative_path = self._safe_relative_path(
            input_payload.get("path") if tool_name != "run_command" else input_payload.get("cwd")
        )
        if tool_name == "run_command":
            if relative_path is None:
                raise LocalRuntimeToolError(
                    "PATH_INVALID", "process working directory must be workspace-relative"
                )
            return await self._execute_command(
                input_payload,
                call_id=call_id,
                request_id=str(request_id or call_id),
                event_sink=event_sink,
                activity=self._activity(
                    tool_name,
                    capability.value,
                    relative_path,
                    status="running",
                    arguments=input_payload,
                ),
            )
        try:
            await self._ensure_healthy_candidate(capability.value)
            invocation = CapabilityInvocation(
                invocationId=str(call_id),
                capabilityId=capability.value,
                input=input_payload,
            )
            result = await self.client.execute(
                invocation,
                resource_id=self.resource_id,
                authorization=self.authorization,
                limits=self.limits,
                idempotency_key=f"chat:{call_id}",
            )
        except LocalRuntimeToolError as exc:
            if exc.activity is None:
                exc.activity = self._activity(
                    tool_name,
                    capability.value,
                    relative_path,
                    status="failed",
                    error_code=exc.code,
                )
            raise
        except Exception as exc:
            raise LocalRuntimeToolError(
                "LOCAL_RUNTIME_UNAVAILABLE",
                "Local Runtime is unavailable.",
                activity=self._activity(
                    tool_name,
                    capability.value,
                    relative_path,
                    status="failed",
                    error_code="LOCAL_RUNTIME_UNAVAILABLE",
                ),
            ) from exc

        if result.status == "failed":
            error = result.error
            code = str(error.code if error else "LOCAL_RUNTIME_FAILED")
            message = str(error.message if error else "Local Runtime execution failed.")
            raise LocalRuntimeToolError(
                code,
                message,
                activity=self._activity(
                    tool_name,
                    capability.value,
                    relative_path,
                    status="failed",
                    error_code=code,
                ),
            )

        output = result.output if isinstance(result.output, dict) else {}
        output_path = self._safe_relative_path(output.get("path")) or relative_path
        completed_activity = self._activity(
            tool_name,
            capability.value,
            output_path,
            status="completed",
            output=output,
            arguments=input_payload,
        )
        return ToolPayload(
            summary=self._summary(tool_name, output_path, output),
            data={"result": output, "activity": completed_activity},
        )

    async def _ensure_healthy_candidate(self, capability_id: str) -> None:
        try:
            healthy = await self.health_projector.refresh(self.health_transport)
        except Exception as exc:
            raise LocalRuntimeToolError(
                "LOCAL_RUNTIME_UNAVAILABLE", "Local Runtime is unavailable."
            ) from exc
        if not healthy:
            raise LocalRuntimeToolError("LOCAL_RUNTIME_UNAVAILABLE", "Local Runtime is unavailable.")
        try:
            candidates = self.resource_plane.runtime_candidates([capability_id])
        except Exception as exc:
            raise LocalRuntimeToolError("LOCAL_RUNTIME_UNAVAILABLE", "Local Runtime is unavailable.") from exc
        selected = [
            candidate
            for candidate in candidates
            if candidate.profile.runtime_id == self.resource_id
            and candidate.profile.kind is RuntimeKind.EXECUTION_BACKEND
            and candidate.profile.placement is Placement.DEVICE
            and capability_id in candidate.profile.capabilities
        ]
        if not selected:
            raise LocalRuntimeToolError("LOCAL_RUNTIME_UNAVAILABLE", "Local Runtime is unavailable.")

    async def _execute_command(
        self,
        input_payload: dict[str, Any],
        *,
        call_id: str,
        request_id: str,
        event_sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
        activity: dict[str, Any],
    ) -> ToolPayload:
        capability = LocalRuntimeCapability.SHELL_EXEC.value
        started = time.perf_counter()
        cwd = str(input_payload.get("cwd") or ".")
        command_text = self._command_display(input_payload)
        terminal: dict[str, Any] = {
            "command": command_text,
            "cwd": cwd,
            "exitCode": None,
            "stdout": "",
            "stderr": "",
            "timedOut": False,
            "truncated": False,
        }
        try:
            await self._ensure_healthy_candidate(capability)
            process_input = dict(input_payload)
            process_input["securityProfile"] = ExecutionSecurityProfile.HOST_APPROVED.value
            timeout = process_input.get("timeout")
            if timeout is not None:
                process_input["timeout"] = min(float(timeout), self.limits.timeout_seconds)
            else:
                process_input.pop("timeout", None)
            invocation = CapabilityInvocation(
                invocationId=str(call_id),
                capabilityId=capability,
                input=process_input,
            )
            result = await self.client.execute(
                invocation,
                resource_id=self.resource_id,
                authorization=self.authorization,
                limits=self.limits,
                idempotency_key=f"chat:{call_id}",
            )
            if result.status == "failed":
                error = result.error
                code = str(error.code if error else "LOCAL_RUNTIME_FAILED")
                raise LocalRuntimeToolError(
                    code,
                    str(error.message if error else "Local Runtime execution failed."),
                    activity=self._activity(
                        "run_command", capability, cwd, status="failed", error_code=code,
                        arguments=input_payload,
                    ),
                    terminal=terminal,
                )
            output = result.output if isinstance(result.output, dict) else {}
            execution_id = str(output.get("executionId") or "").strip()
            if not execution_id:
                raise LocalRuntimeToolError(
                    "EXECUTION_NOT_ACCEPTED",
                    "Local Runtime did not return an execution identity.",
                    activity=self._activity(
                        "run_command", capability, cwd, status="failed",
                        error_code="EXECUTION_NOT_ACCEPTED", arguments=input_payload,
                    ),
                    terminal=terminal,
                )
            self._active[request_id] = (result.request_id, execution_id, result.invocation_id)
            await self._emit_execution(
                event_sink,
                "execution_started",
                {
                    "callId": call_id,
                    "toolName": "run_command",
                    "executionId": execution_id,
                    "terminal": dict(terminal),
                },
            )
            terminal_state: str | None = None
            async for event in self.client.stream_events(
                execution_id=execution_id,
                request_id=result.request_id,
                invocation_id=result.invocation_id,
            ):
                data = dict(event.data or {})
                if event.event_type in {"stdout_delta", "stderr_delta"}:
                    delta = str(data.get("delta") or "")
                    stream_name = "stdout" if event.event_type == "stdout_delta" else "stderr"
                    terminal[stream_name] = str(terminal.get(stream_name) or "") + delta
                    if data.get("truncated"):
                        terminal["truncated"] = True
                    await self._emit_execution(
                        event_sink,
                        event.event_type,
                        {
                            "callId": call_id,
                            "toolName": "run_command",
                            "executionId": execution_id,
                            "stream": stream_name,
                            "delta": delta,
                            "truncated": bool(data.get("truncated")),
                            "terminal": dict(terminal),
                        },
                    )
                elif event.event_type in {"completed", "failed", "cancelled"}:
                    terminal_state = event.event_type
                    if isinstance(data.get("exitCode"), int):
                        terminal["exitCode"] = data["exitCode"]
                    if data.get("code") == "EXECUTION_TIMEOUT":
                        terminal["timedOut"] = True
                    terminal["durationMs"] = int((time.perf_counter() - started) * 1000)
                    terminal["truncated"] = bool(terminal.get("truncated") or data.get("truncated"))
                    mapped = "execution_completed" if event.event_type == "completed" else (
                        "execution_cancelled" if event.event_type == "cancelled" else "execution_failed"
                    )
                    await self._emit_execution(
                        event_sink,
                        mapped,
                        {
                            "callId": call_id,
                            "toolName": "run_command",
                            "executionId": execution_id,
                            "errorCode": data.get("code"),
                            "terminal": dict(terminal),
                        },
                    )
                    if event.event_type == "cancelled":
                        raise LocalRuntimeToolError(
                            "EXECUTION_CANCELLED", "command execution was cancelled",
                            activity=self._activity(
                                "run_command", capability, cwd, status="cancelled",
                                error_code="EXECUTION_CANCELLED", arguments=input_payload,
                            ),
                            terminal=terminal,
                        )
                    if event.event_type == "failed":
                        code = str(data.get("code") or "PROCESS_EXECUTION_FAILED")
                        raise LocalRuntimeToolError(
                            code, "command execution failed",
                            activity=self._activity(
                                "run_command", capability, cwd, status="failed",
                                error_code=code, arguments=input_payload,
                            ),
                            terminal=terminal,
                        )
                    break
            if terminal_state != "completed":
                raise LocalRuntimeToolError(
                    "EXECUTION_INCOMPLETE", "command execution did not complete",
                    activity=self._activity(
                        "run_command", capability, cwd, status="failed",
                        error_code="EXECUTION_INCOMPLETE", arguments=input_payload,
                    ),
                    terminal=terminal,
                )
            completed_activity = self._activity(
                "run_command", capability, cwd, status="completed",
                output=terminal, arguments=input_payload,
            )
            return ToolPayload(
                summary=f"Command completed (exit code {terminal.get('exitCode')})",
                data={"result": terminal, "terminal": terminal, "activity": completed_activity},
            )
        except LocalRuntimeToolError as exc:
            if exc.activity is None:
                exc.activity = self._activity(
                    "run_command", capability, cwd, status="failed",
                    error_code=exc.code, arguments=input_payload,
                )
            if exc.terminal is None:
                exc.terminal = terminal
            raise
        except Exception as exc:
            LOGGER.warning("run_command local runtime execution failed", exc_info=True)
            raise LocalRuntimeToolError(
                "LOCAL_RUNTIME_UNAVAILABLE",
                "Local Runtime is unavailable.",
                activity=self._activity(
                    "run_command", capability, cwd, status="failed",
                    error_code="LOCAL_RUNTIME_UNAVAILABLE", arguments=input_payload,
                ),
                terminal=terminal,
            ) from exc
        finally:
            self._active.pop(request_id, None)

    async def cancel(self, request_id: str) -> bool:
        active = self._active.get(str(request_id or ""))
        if active is None:
            return False
        runtime_request_id, execution_id, invocation_id = active
        await self.client.cancel(
            execution_id=execution_id,
            request_id=runtime_request_id,
            invocation_id=invocation_id,
        )
        return True

    def supports_capability(self, capability_id: str) -> bool:
        try:
            profile = self.resource_plane.runtime(self.resource_id)
        except Exception:
            return False
        return capability_id in profile.capabilities

    @staticmethod
    async def _emit_execution(
        sink: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        if sink is not None:
            await sink(event_type, payload)

    @staticmethod
    def _business_input(tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        allowed: dict[str, tuple[str, ...]] = {
            "read_file": ("path", "encoding", "binary", "versioned"),
            "list_files": ("path", "maxEntries"),
            "write_file": ("path", "content", "overwrite", "createParents", "encoding", "binary", "expectedVersion"),
            "patch_file": ("path", "patch", "encoding", "expectedSha256"),
            "run_command": ("mode", "program", "args", "command", "cwd", "timeout"),
        }[tool_name]
        payload = {key: arguments[key] for key in allowed if arguments.get(key) is not None}
        if tool_name == "run_command":
            payload.setdefault("mode", "shell")
            payload.setdefault("cwd", ".")
        return payload

    @staticmethod
    def _safe_relative_path(value: Any) -> str | None:
        path = str(value or "").strip().replace("\\", "/")
        if not path or not _SAFE_RELATIVE_PATH.match(path) or ".." in path.split("/"):
            return None
        return path

    @staticmethod
    def _activity(
        tool_name: str,
        capability_id: str,
        relative_path: str | None,
        *,
        status: str,
        error_code: str | None = None,
        output: dict[str, Any] | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kind = {
            "read_file": "file_read",
            "list_files": "file_list",
            "write_file": "file_write",
            "patch_file": "file_patch",
            "run_command": "terminal",
        }[tool_name]
        activity: dict[str, Any] = {
            "kind": kind,
            "capabilityId": capability_id,
            "status": status,
        }
        if relative_path:
            activity["relativePath"] = relative_path
        if output and tool_name == "list_files" and isinstance(output.get("count"), int):
            activity["entryCount"] = output["count"]
        if output and tool_name == "write_file":
            activity["summary"] = "Updated file" if output.get("overwritten") else "Created file"
        elif tool_name == "patch_file":
            activity["summary"] = "Edited file"
            patch = str((arguments or {}).get("patch") or "")
            activity["addedLines"] = sum(1 for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
            activity["removedLines"] = sum(1 for line in patch.splitlines() if line.startswith("-") and not line.startswith("---"))
        elif tool_name == "read_file":
            activity["summary"] = "Read file"
        elif tool_name == "list_files":
            activity["summary"] = "Listed directory"
        if error_code:
            activity["errorCode"] = error_code
        return activity

    @staticmethod
    def _command_display(arguments: Mapping[str, Any]) -> str:
        if str(arguments.get("mode") or "shell") == "direct":
            return " ".join(
                [str(arguments.get("program") or ""), *[str(item) for item in arguments.get("args") or []]]
            ).strip()
        return str(arguments.get("command") or "")

    @staticmethod
    def _summary(tool_name: str, path: str | None, output: dict[str, Any]) -> str:
        label = {
            "read_file": "Read",
            "list_files": "Listed",
            "write_file": "Created" if not output.get("overwritten") else "Updated",
            "patch_file": "Edited",
            "run_command": "Command completed",
        }[tool_name]
        if tool_name == "run_command":
            return f"{label} (exit code {output.get('exitCode')})"
        return f"{label} {path or 'workspace file'}"


__all__ = ["LocalRuntimeToolError", "LocalRuntimeToolExecutor", "TOOL_CAPABILITIES"]
