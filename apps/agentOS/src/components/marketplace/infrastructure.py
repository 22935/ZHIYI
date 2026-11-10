"""资源商店目录、安装任务与包校验的基础设施实现。"""

from __future__ import annotations

import hashlib
import httpx
import sqlite3
import subprocess
import zipfile
import os
import sys
import json
import uuid
import secrets
import time
import importlib.util
from pathlib import Path
from urllib.parse import urlsplit
from threading import RLock

from components.resource.infrastructure.sqlite.connection import configure_sqlite_connection

from .contracts import CatalogItem, InstallationJob
from .ports import Catalog, InstallationJobStore
from contracts.resource import RuntimeProfile


class InMemoryCatalog:
    """用于测试和受控进程内平台目录的不可变目录映射。"""

    def __init__(self, items: list[CatalogItem]) -> None:
        self._items = {item.catalog_id: item for item in items}

    def list_items(self) -> list[CatalogItem]:
        return list(self._items.values())

    def get(self, catalog_id: str) -> CatalogItem:
        try:
            return self._items[catalog_id]
        except KeyError as exc:
            raise KeyError(f"unknown catalog item: {catalog_id}") from exc


class DirectoryCatalog:
    """从平台只读目录加载 JSON 清单，不接受 API 请求动态声明启动内容。"""

    def __init__(self, catalog_root: str | Path) -> None:
        self.root = Path(catalog_root).resolve()

    def list_items(self) -> list[CatalogItem]:
        if not self.root.exists():
            return []
        items = []
        for manifest in sorted(self.root.glob("*.json")):
            items.append(CatalogItem.model_validate_json(manifest.read_text(encoding="utf-8")))
        return items

    def get(self, catalog_id: str) -> CatalogItem:
        for item in self.list_items():
            if item.catalog_id == catalog_id:
                return item
        raise KeyError(f"unknown catalog item: {catalog_id}")


class LocalPackageLauncher:
    """解包平台校验包并以无 shell 子进程启动目录声明的入口。"""

    def __init__(self, *, package_root: str | Path, install_root: str | Path) -> None:
        self.package_root = Path(package_root).resolve()
        self.install_root = Path(install_root).resolve()
        self.install_root.mkdir(parents=True, exist_ok=True)
        self._processes: dict[str, subprocess.Popen] = {}
        self._install_paths: dict[str, Path] = {}
        self._endpoints: dict[str, str] = {}
        self._credentials: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    def start(self, item: CatalogItem, *, owner_scope: str) -> RuntimeProfile:
        package = validate_package(self.package_root, item)
        if not zipfile.is_zipfile(package):
            raise ValueError("catalog package must be a ZIP bundle")
        declared = RuntimeProfile.model_validate(item.runtime)
        if declared.endpoint is None:
            raise ValueError("catalog runtime must declare a local service endpoint")
        host = urlsplit(declared.endpoint.address).hostname
        if host not in {"127.0.0.1", "localhost", "::1", "[::1]"}:
            raise ValueError("catalog service endpoint must be loopback")
        entrypoint = item.startup.get("entrypoint")
        module = item.startup.get("pythonModule")
        if module is not None:
            return self._start_builtin(item, declared, package, owner_scope, module)
        arguments = item.startup.get("arguments", [])
        if not isinstance(entrypoint, str) or not entrypoint or not isinstance(arguments, list) or not all(
            isinstance(argument, str) for argument in arguments
        ):
            raise ValueError("catalog startup template is invalid")
        destination = (self.install_root / item.catalog_id.replace("/", "_")).resolve()
        if self.install_root not in destination.parents:
            raise ValueError("catalog install path escapes platform root")
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(package) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if destination not in target.parents and target != destination:
                    raise ValueError("catalog archive contains an unsafe path")
            archive.extractall(destination)
        executable = (destination / entrypoint).resolve()
        if destination not in executable.parents or not executable.is_file():
            raise ValueError("catalog entrypoint is missing or unsafe")
        process = subprocess.Popen(
            [str(executable), *arguments], cwd=destination, shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with self._lock:
            self._processes[declared.runtime_id] = process
            self._install_paths[declared.runtime_id] = destination
            self._endpoints[declared.runtime_id] = declared.endpoint.address
        return declared.model_copy(update={
            "owner_scope": owner_scope,
            "metadata": {**declared.metadata, "managedBy": "marketplace", "catalogId": item.catalog_id},
        })

    def stop(self, runtime_id: str) -> None:
        with self._lock:
            process = self._processes.pop(runtime_id, None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def healthy(self, runtime_id: str) -> bool:
        endpoint = self._endpoints.get(runtime_id)
        process = self._processes.get(runtime_id)
        return process is not None and process.poll() is None and endpoint is not None and LoopbackHttpEndpointProbe().healthy(endpoint)

    def _start_builtin(self, item, declared, package, owner_scope, module):
        """只运行平台固定模块；每次安装独占身份、目录、随机端口和签名凭据。"""
        if module != "agentos_local_tools.server" or item.startup.get("capability") not in {"pdf.parse", "file.convert"}:
            raise ValueError("unsupported platform Python module")
        if any(importlib.util.find_spec(name) is None for name in ("pypdf", "docx", "openpyxl", "markdown")):
            raise ValueError("local tool dependencies missing; install requirements-local-tools.txt")
        token = uuid.uuid4().hex
        runtime_id = declared.runtime_id + ":installation:" + token
        destination = self.install_root / token
        destination.mkdir()
        try:
            with zipfile.ZipFile(package) as archive:
                members = archive.infolist()
                if len(members) > 100 or sum(m.file_size for m in members) > 10 * 1024 * 1024:
                    raise ValueError("platform bundle too large")
                for member in members:
                    target = (destination / member.filename).resolve()
                    if destination not in target.parents or "\\" in member.filename or ":" in member.filename:
                        raise ValueError("unsafe platform bundle path")
                archive.extractall(destination)
            credential = ("rc_" + uuid.uuid4().hex, secrets.token_urlsafe(32))
            environment = {key: value for key, value in os.environ.items() if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG", "LC_ALL"}}
            environment.update(AGENTOS_TOOL_RUNTIME_ID=runtime_id, AGENTOS_TOOL_CREDENTIAL_ID=credential[0],
                AGENTOS_TOOL_SECRET=credential[1], AGENTOS_TOOL_CAPABILITY=item.startup["capability"])
            environment.pop("PYTHONPATH", None)
            process = subprocess.Popen([sys.executable, "-m", module], cwd=destination, env=environment, shell=False,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            with self._lock:
                self._processes[runtime_id] = process
                self._install_paths[runtime_id] = destination
                self._credentials[runtime_id] = credential
            deadline = time.monotonic() + 15
            ready = destination / "ready.json"
            while time.monotonic() < deadline and process.poll() is None:
                if ready.exists():
                    try:
                        data = json.loads(ready.read_text(encoding="utf-8"))
                        if data["runtimeId"] == runtime_id:
                            endpoint = f'http://127.0.0.1:{int(data["port"])}'
                            self._endpoints[runtime_id] = endpoint
                            if self.healthy(runtime_id):
                                return declared.model_copy(update={"runtime_id": runtime_id, "owner_scope": owner_scope,
                                    "node_id": "node:device:tools:" + hashlib.sha256(owner_scope.encode()).hexdigest()[:20],
                                    "endpoint": declared.endpoint.model_copy(update={"address": endpoint})})
                    except (ValueError, KeyError):
                        pass
                time.sleep(0.05)
            raise RuntimeError("platform tool startup timed out")
        except Exception:
            import shutil
            self.stop(runtime_id)
            self._install_paths.pop(runtime_id, None)
            self._credentials.pop(runtime_id, None)
            self._endpoints.pop(runtime_id, None)
            shutil.rmtree(destination)
            raise

    def signing_credential(self, runtime_id):
        return self._credentials[runtime_id]

    def workspace(self, runtime_id):
        if not self.healthy(runtime_id) or runtime_id not in self._credentials:
            raise ValueError("managed tool is not running")
        return self._install_paths[runtime_id] / "workspace"

    def close(self):
        for runtime_id in list(self._processes):
            self.stop(runtime_id)

    def remove(self, runtime_id: str) -> None:
        self.stop(runtime_id)
        with self._lock:
            path = self._install_paths.get(runtime_id)
            self._endpoints.pop(runtime_id, None)
            self._credentials.pop(runtime_id, None)
        if path is not None and self.install_root in path.parents:
            self._remove_installation_path(path)
        elif ":installation:" in runtime_id:
            # 重启后没有进程对象，仅可清理由平台随机生成的安装目录。
            token = runtime_id.rsplit(":installation:", 1)[1]
            if len(token) == 32 and all(c in "0123456789abcdef" for c in token):
                target = (self.install_root / token).resolve()
                if self.install_root in target.parents and target.is_dir():
                    self._remove_installation_path(target)
        self._install_paths.pop(runtime_id, None)

    def _remove_installation_path(self, path: Path) -> None:
        """Windows 进程退出后目录锁可能短暂滞后；有界重试且不吞掉真实删除失败。"""
        import shutil
        if self.install_root not in path.resolve().parents:
            raise ValueError("installation path escapes platform root")
        for attempt in range(5):
            try:
                if path.exists():
                    shutil.rmtree(path)
                return
            except OSError as error:
                if not isinstance(error, PermissionError) and getattr(error, "winerror", None) not in {5, 32, 145}:
                    raise
                if attempt == 4:
                    raise
                time.sleep(0.05 * (2 ** attempt))

class LoopbackHttpEndpointProbe:
    """仅探测 loopback 服务的固定健康路径，不访问用户指定的公网主机。"""

    def healthy(self, endpoint: str) -> bool:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1", "localhost", "::1", "[::1]"
        }:
            return False
        base = endpoint.rstrip("/")
        for path in ("/health", "/v1/models", "/"):
            try:
                response = httpx.get(f"{base}{path}", timeout=2.0, follow_redirects=False)
                if 200 <= response.status_code < 400:
                    return True
            except httpx.HTTPError:
                continue
        return False


class SQLiteInstallationJobStore:
    """以独立 SQLite 表持久化任务状态，跨 AgentOS 重启可查询。"""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = configure_sqlite_connection(
            sqlite3.connect(path, check_same_thread=False, timeout=30.0)
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS marketplace_installations (
                job_id TEXT PRIMARY KEY,
                owner_scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                job_json TEXT NOT NULL
            )"""
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_marketplace_installations_owner "
            "ON marketplace_installations(owner_scope, created_at DESC)"
        )
        self._connection.commit()
        self._lock = RLock()

    @staticmethod
    def _parse(value: str) -> InstallationJob:
        return InstallationJob.model_validate_json(value)

    @staticmethod
    def _serialize(job: InstallationJob) -> str:
        return job.model_dump_json(by_alias=True)

    def create(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            self._connection.execute(
                "INSERT INTO marketplace_installations(job_id, owner_scope, created_at, job_json) VALUES (?, ?, ?, ?)",
                (job.job_id, job.owner_scope, job.created_at.isoformat(), self._serialize(job)),
            )
            self._connection.commit()
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> InstallationJob:
        with self._lock:
            row = self._connection.execute(
                "SELECT job_json FROM marketplace_installations WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown installation job: {job_id}")
        return self._parse(str(row[0]))

    def update(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE marketplace_installations SET job_json = ? WHERE job_id = ? AND owner_scope = ?",
                (self._serialize(job), job.job_id, job.owner_scope),
            )
            if cursor.rowcount != 1:
                self._connection.rollback()
                raise KeyError(f"unknown installation job: {job.job_id}")
            self._connection.commit()
            return job.model_copy(deep=True)

    def list(self, owner_scope: str) -> list[InstallationJob]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT job_json FROM marketplace_installations WHERE owner_scope = ? ORDER BY created_at DESC",
                (owner_scope,),
            ).fetchall()
        return [self._parse(str(row[0])) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def list_all(self) -> list[InstallationJob]:
        with self._lock:
            rows = self._connection.execute("SELECT job_json FROM marketplace_installations ORDER BY created_at").fetchall()
        return [self._parse(str(row[0])) for row in rows]


class InMemoryInstallationJobs:
    """线程安全的任务仓储，仅用于测试。"""

    def __init__(self) -> None:
        self._jobs: dict[str, InstallationJob] = {}
        self._lock = RLock()

    def create(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            if job.job_id in self._jobs:
                raise ValueError(f"installation job already exists: {job.job_id}")
            self._jobs[job.job_id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def get(self, job_id: str) -> InstallationJob:
        with self._lock:
            try:
                return self._jobs[job_id].model_copy(deep=True)
            except KeyError as exc:
                raise KeyError(f"unknown installation job: {job_id}") from exc

    def update(self, job: InstallationJob) -> InstallationJob:
        with self._lock:
            if job.job_id not in self._jobs:
                raise KeyError(f"unknown installation job: {job.job_id}")
            self._jobs[job.job_id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def list(self, owner_scope: str) -> list[InstallationJob]:
        with self._lock:
            return [job.model_copy(deep=True) for job in self._jobs.values() if job.owner_scope == owner_scope]

    def list_all(self) -> list[InstallationJob]:
        with self._lock:
            return [job.model_copy(deep=True) for job in self._jobs.values()]


def validate_package(package_root: Path, item: CatalogItem) -> Path:
    """解析目录内包路径并校验真实文件内容摘要。"""
    root = package_root.resolve()
    package = (root / item.package_path).resolve()
    if root not in package.parents or not package.is_file():
        raise ValueError("catalog package is missing or escapes platform root")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    if digest.lower() != item.sha256.lower():
        raise ValueError("catalog package checksum mismatch")
    return package


__all__ = [
    "InMemoryCatalog", "InMemoryInstallationJobs", "SQLiteInstallationJobStore", "validate_package",
]
