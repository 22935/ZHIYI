"""Cloud coordinator process for the real terminal-edge-cloud demo."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agentOS" / "src"))
sys.path.insert(0, str(ROOT / "agentOS"))

from adapters.resource_execution import ResourceExecutionError, build_resource_execution_adapter
from components.resource.auth import (
    ResourceRequestAuthenticator,
    ResourceRequestExpired,
    ResourceRequestInvalid,
    ResourceRequestNotFound,
    ResourceRequestReplay,
)
from components.resource.health import ResourceHealthMonitor
from components.resource.health_store import SQLiteResourceHealthStore
from components.resource.service import ResourceService
from components.resource.store import SQLiteResourceStore, StaleResourceObservation
from contracts.resource import (
    DeploymentTier,
    ResourceEndpoint,
    ResourceHealthStatus,
    ResourceProfile,
    ResourceSnapshot,
    ResourceType,
)

from common import read_json, write_json


def make_context(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        task=SimpleNamespace(mission_id=str(payload.get("missionId", "demo-mission"))),
        run=SimpleNamespace(run_id=str(payload.get("runId", "demo-run"))),
        step=SimpleNamespace(
            step_id=str(payload.get("stepId", "demo-step")),
            agent_name="demo-worker",
            capability="demo.execute",
            goal="run demo",
        ),
        context_pack=SimpleNamespace(
            data=dict(payload.get("input") or {"value": "端边云联调"}),
            evidence_refs=[],
            attempt_id="demo-attempt",
        ),
        commit_id="demo-commit",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--resource-db", required=True)
    parser.add_argument("--health-db", required=True)
    args = parser.parse_args()
    service = ResourceService(
        store=SQLiteResourceStore(args.resource_db),
        health_monitor=ResourceHealthMonitor(
            store=SQLiteResourceHealthStore(args.health_db),
            heartbeat_timeout=__import__("datetime").timedelta(seconds=5),
        ),
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if self.path == "/health":
                write_json(self, 200, {"status": "ok", "node": "cloud"})
                return
            if self.path == "/resources":
                items = []
                for profile in service.profiles():
                    snapshot = service.snapshot(profile.resource_id)
                    health = service.health_monitor.health(profile.resource_id)
                    items.append({
                        "resourceId": profile.resource_id,
                        "snapshot": snapshot.snapshot.model_dump(by_alias=True, mode="json"),
                        "snapshotVersion": snapshot.version,
                        "health": {
                            "healthy": health.healthy,
                            "reliability": health.reliability,
                            "latencyMs": health.latency_ms,
                            "lastHeartbeat": health.last_heartbeat.isoformat() if health.last_heartbeat else None,
                            "healthSource": type(service.health_monitor.store).__name__,
                        },
                    })
                write_json(self, 200, {"items": items})
                return
            write_json(self, 404, {"error": "not found"})

        def do_POST(self) -> None:
            try:
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                payload = json.loads(raw_body or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("request JSON must be an object")
                if self.path == "/resources/register":
                    profile = ResourceProfile(
                        resourceId=str(payload["resourceId"]),
                        resourceType=ResourceType(str(payload.get("resourceType", "worker"))),
                        deploymentTier=DeploymentTier(str(payload["deploymentTier"])),
                        capabilities=list(payload.get("capabilities") or ["demo.execute"]),
                        ownerScope=str(payload.get("ownerScope", "demo")),
                        executionEndpoint=ResourceEndpoint(
                            protocol=str(payload.get("protocol", "http")),
                            address=str(payload["address"]),
                        ),
                    )
                    issued = service.register_remote(
                        profile,
                        ResourceSnapshot(
                            resourceId=profile.resource_id,
                            availableSlots=1,
                            utilization=0.0,
                            healthStatus=ResourceHealthStatus.UNKNOWN,
                        ),
                    )
                    write_json(self, 201, {
                        "resourceId": issued.resource_id,
                        "credentialId": issued.credential_id,
                        "secret": issued.secret,
                    })
                    return
                if self.path in {"/execute", "/cloud-execute"}:
                    credential = service.credential("cloud-01")
                    ResourceRequestAuthenticator(service).authenticate(
                        resource_id="cloud-01",
                        credential_id=self.headers.get("X-Resource-Credential", ""),
                        method="POST",
                        path=self.path,
                        timestamp=int(self.headers.get("X-Resource-Timestamp", "0")),
                        nonce=self.headers.get("X-Resource-Nonce", ""),
                        signature=self.headers.get("X-Resource-Signature", ""),
                        body=raw_body,
                    )
                    write_json(self, 200, {
                        "output": {
                            "node": "cloud",
                            "signatureVerified": True,
                            "input": payload.get("input", {}),
                        },
                        "summary": "executed by cloud",
                    })
                    return
                if self.path.startswith("/resources/") and self.path.endswith("/observation"):
                    resource_id = self.path.split("/")[2]
                    headers = {
                        "X-Resource-Credential": self.headers.get("X-Resource-Credential", ""),
                        "X-Resource-Timestamp": self.headers.get("X-Resource-Timestamp", ""),
                        "X-Resource-Nonce": self.headers.get("X-Resource-Nonce", ""),
                        "X-Resource-Signature": self.headers.get("X-Resource-Signature", ""),
                    }
                    try:
                        timestamp = int(headers["X-Resource-Timestamp"])
                        ResourceRequestAuthenticator(service).authenticate(
                            resource_id=resource_id,
                            credential_id=headers["X-Resource-Credential"],
                            method="POST",
                            path=self.path,
                            timestamp=timestamp,
                            nonce=headers["X-Resource-Nonce"],
                            signature=headers["X-Resource-Signature"],
                            body=raw_body,
                        )
                    except (ValueError, ResourceRequestInvalid) as error:
                        write_json(self, 401, {"error": str(error)})
                        return
                    except ResourceRequestNotFound as error:
                        write_json(self, 404, {"error": str(error)})
                        return
                    except ResourceRequestReplay as error:
                        write_json(self, 409, {"error": str(error)})
                        return
                    except ResourceRequestExpired as error:
                        write_json(self, 401, {"error": str(error)})
                        return
                    observed_at = payload.get("observedAt")
                    service.observe_remote(
                        resource_id,
                        available_slots=int(payload.get("availableSlots", 1)),
                        utilization=float(payload.get("utilization", 0.0)),
                        latency_ms=payload.get("latencyMs"),
                        observed_at=(
                            datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
                            if observed_at else datetime.now(timezone.utc)
                        ),
                        observation_sequence=int(payload.get("observationSequence", 0)),
                    )
                    write_json(self, 200, {"resourceId": resource_id, "accepted": True})
                    return
                if self.path == "/run":
                    primary_id = str(payload["primaryResourceId"])
                    fallback_id = str(payload.get("fallbackResourceId") or "")
                    try:
                        result = execute(service, primary_id, payload)
                        write_json(self, 200, {
                            "selectedResourceId": primary_id,
                            "signatureVerified": bool(result.output.get("signatureVerified")),
                            "output": result.model_dump(mode="json"),
                            "failoverApplied": False,
                        })
                        return
                    except ResourceExecutionError as first_error:
                        service.set_health(primary_id, healthy=False)
                        if not fallback_id:
                            write_json(self, 502, {"error": str(first_error)})
                            return
                        result = execute(service, fallback_id, payload)
                        write_json(self, 200, {
                            "selectedResourceId": fallback_id,
                            "failedResourceId": primary_id,
                            "signatureVerified": bool(result.output.get("signatureVerified")),
                            "output": result.model_dump(mode="json"),
                            "failoverApplied": True,
                        })
                        return
                write_json(self, 404, {"error": "not found"})
            except StaleResourceObservation as error:
                write_json(self, 409, {"error": str(error)})
            except Exception as error:
                write_json(self, 400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


def execute(service: ResourceService, resource_id: str, payload: dict):
    profile = service.profile(resource_id)
    adapter = build_resource_execution_adapter(
        profile,
        credential_provider=service,
        timeout_seconds=2.0,
    )

    async def invoke():
        try:
            return await adapter.run(make_context(payload))
        finally:
            await adapter.aclose()

    return asyncio.run(invoke())


if __name__ == "__main__":
    main()
