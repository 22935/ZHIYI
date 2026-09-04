"""Run a reproducible three-process terminal/edge/cloud acceptance flow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(url: str, payload: dict | None = None) -> tuple[int, dict]:
    body = None
    headers = {}
    method = "GET" if payload is None else "POST"
    if payload is not None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=4) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())
    except (URLError, TimeoutError, OSError) as error:
        return 503, {"error": str(error)}


def wait_for(url: str, process: subprocess.Popen, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"child process exited before ready: {url}")
        try:
            status, _ = request_json(url)
            if status == 200:
                return
        except (OSError, URLError, ValueError):
            pass
        time.sleep(0.05)
    raise RuntimeError(f"process did not become ready: {url}")


def start(script: str, *args: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "edge_cloud_demo" / script), *args],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def require(status: int, payload: dict, expected: int = 200) -> dict:
    if status != expected:
        raise RuntimeError(f"unexpected HTTP {status}: {payload}")
    return payload


def run(work_dir: Path) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    ports = {name: free_port() for name in ("terminal", "edge", "cloud")}
    processes: dict[str, subprocess.Popen] = {}
    try:
        processes["terminal"] = start("terminal_node.py", "--name", "terminal", "--port", str(ports["terminal"]))
        processes["edge"] = start("edge_node.py", "--name", "edge", "--port", str(ports["edge"]))
        processes["cloud"] = start(
            "cloud_node.py",
            "--port", str(ports["cloud"]),
            "--resource-db", str(work_dir / "resources.sqlite3"),
            "--health-db", str(work_dir / "resource_health.sqlite3"),
        )
        for name in ("terminal", "edge", "cloud"):
            wait_for(f"http://127.0.0.1:{ports[name]}/health", processes[name])

        cloud = f"http://127.0.0.1:{ports['cloud']}"
        edge = f"http://127.0.0.1:{ports['edge']}"
        terminal = f"http://127.0.0.1:{ports['terminal']}"
        registrations = {}
        for resource_id, tier, address in (
            ("terminal-01", "terminal", f"{terminal}/execute"),
            ("edge-01", "edge", f"{edge}/execute"),
            ("cloud-01", "cloud", f"{cloud}/execute"),
        ):
            status, response = request_json(
                f"{cloud}/resources/register",
                {
                    "resourceId": resource_id,
                    "deploymentTier": tier,
                    "address": address,
                    "protocol": "http",
                    "ownerScope": "demo",
                },
            )
            registrations[tier] = require(status, response, 201)

        for node_name, base_url, tier in (
            ("terminal", terminal, "terminal"),
            ("edge", edge, "edge"),
        ):
            registration = registrations[tier]
            require(*request_json(
                f"{base_url}/configure",
                {
                    "credentialId": registration["credentialId"],
                    "secret": registration["secret"],
                    "observationUrl": f"{cloud}/resources/{registration['resourceId']}/observation",
                },
            ))
            require(*request_json(f"{base_url}/emit-observation", {}))

        initial_status, initial = request_json(
            f"{cloud}/run",
            {
                "primaryResourceId": "edge-01",
                "fallbackResourceId": "cloud-01",
                "input": {"value": "第一次执行"},
            },
        )
        require(initial_status, initial)

        require(*request_json(f"{edge}/control/fail", {"failed": True}))
        failed_status, after_failure = request_json(
            f"{cloud}/run",
            {
                "primaryResourceId": "edge-01",
                "fallbackResourceId": "cloud-01",
                "input": {"value": "边节点故障"},
            },
        )
        require(failed_status, after_failure)

        processes["edge"].terminate()
        processes["edge"].wait(timeout=3)
        terminated_status, after_termination = request_json(
            f"{cloud}/run",
            {
                "primaryResourceId": "edge-01",
                "fallbackResourceId": "cloud-01",
                "input": {"value": "边节点进程退出"},
            },
        )
        require(terminated_status, after_termination)

        processes["edge"] = start("edge_node.py", "--name", "edge", "--port", str(ports["edge"]))
        wait_for(f"{edge}/health", processes["edge"])
        edge_registration = registrations["edge"]
        require(*request_json(
            f"{edge}/configure",
            {
                "credentialId": edge_registration["credentialId"],
                "secret": edge_registration["secret"],
                "observationUrl": f"{cloud}/resources/edge-01/observation",
            },
        ))
        require(*request_json(f"{edge}/emit-observation", {}))
        resources = require(*request_json(f"{cloud}/resources"))
        edge_projection = next(item for item in resources["items"] if item["resourceId"] == "edge-01")

        registration_report = {
            tier: {
                "resourceId": value["resourceId"],
                "credentialId": value["credentialId"],
                "secretIssued": bool(value.get("secret")),
            }
            for tier, value in registrations.items()
        }
        return {
            "registration": registration_report,
            "execution": {
                "initial": initial,
                "afterEdgeFailure": after_failure,
                "afterEdgeTermination": after_termination,
            },
            "recovery": {
                "edgeHealthyAfterRestart": edge_projection["health"]["healthy"],
                "healthSource": edge_projection["health"]["healthSource"],
            },
        }
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", default=None)
    args = parser.parse_args()
    temporary = args.work_dir is None
    work_dir = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="edge-cloud-demo-"))
    try:
        print(json.dumps(run(work_dir), ensure_ascii=True, sort_keys=True))
    finally:
        if temporary:
            pass


if __name__ == "__main__":
    main()
