"""AgentOS Core 的 Pack registry 模块，负责应用层 Pack 的发现、注册和资源定位。"""


from __future__ import annotations

import importlib
import hashlib
import inspect
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PackManifest:
    """AgentOS 工作流 Pack 的元数据和注册入口。"""

    pack_id: str
    name: str
    version: str
    description: str
    module: str
    enabled: bool
    capabilities: tuple[str, ...]
    agents: tuple[str, ...]
    workflows: tuple[str, ...]
    path: Path
    ui_extension_id: str | None = None

    def normalized(self) -> dict[str, Any]:
        """Return formatting- and key-order-independent manifest data."""

        return {
            "id": self.pack_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "module": self.module,
            "enabled": self.enabled,
            "uiExtensionId": self.ui_extension_id,
            "contributions": {
                "capabilities": sorted(set(self.capabilities)),
                "agents": sorted(set(self.agents)),
                "workflows": sorted(set(self.workflows)),
            },
        }

    @property
    def manifest_hash(self) -> str:
        return _stable_hash(self.normalized())

    @property
    def contribution_revision(self) -> str:
        return _stable_hash(self.normalized()["contributions"])


def discover_pack_manifests(packs_dir: Path | None = None) -> tuple[PackManifest, ...]:
    root = packs_dir or default_packs_dir()
    root = root.resolve()
    manifests = []
    for manifest_path in sorted(root.glob("*/manifest.yaml")):
        manifest = load_pack_manifest(manifest_path)
        if manifest.enabled:
            manifests.append(manifest)
    return tuple(manifests)


def load_pack_manifest(path: Path) -> PackManifest:
    data = _load_manifest_data(path)
    pack_id = str(data.get("id") or "").strip()
    if not pack_id:
        raise ValueError(f"pack manifest missing id: {path}")

    module = str(data.get("module") or f"packs.{pack_id}").strip()
    contributions = data.get("contributions") or {}
    if not isinstance(contributions, dict):
        raise ValueError(f"pack manifest contributions must be an object: {path}")
    normalized_contributions: dict[str, list[str]] = {}
    for kind in ("capabilities", "agents", "workflows"):
        values = contributions.get(kind) or []
        if not isinstance(values, list):
            raise ValueError(f"pack manifest {kind} must be an array: {path}")
        normalized_contributions[kind] = sorted(
            {str(item).strip() for item in values if str(item).strip()}
        )

    return PackManifest(
        pack_id=pack_id,
        name=str(data.get("name") or pack_id),
        version=str(data.get("version") or "0.0.0"),
        description=str(data.get("description") or ""),
        module=module,
        enabled=bool(data.get("enabled", True)),
        capabilities=tuple(normalized_contributions["capabilities"]),
        agents=tuple(normalized_contributions["agents"]),
        workflows=tuple(normalized_contributions["workflows"]),
        path=path,
        ui_extension_id=(
            str(data.get("uiExtensionId") or "").strip() or None
        ),
    )


def register_installed_packs(
    *,
    agent_registry,
    workflow_registry,
    capability_catalog=None,
    packs_dir: Path | None = None,
) -> tuple[PackManifest, ...]:
    root = (packs_dir or default_packs_dir()).resolve()
    import_root = str(root.parent)
    if import_root not in sys.path:
        sys.path.insert(0, import_root)

    registered = []
    for manifest in discover_pack_manifests(root):
        before_agents = {id(agent) for agent in agent_registry.all()}
        before_workflows = {
            workflow.workflow_id for workflow in workflow_registry.all()
        }
        before_capabilities = (
            {
                descriptor.capability_id
                for descriptor in capability_catalog.available()
            }
            if capability_catalog is not None
            else set()
        )
        module = importlib.import_module(manifest.module)
        register_pack = getattr(module, "register_pack", None)
        if register_pack is None:
            raise ValueError(f"pack module missing register_pack: {manifest.module}")
        kwargs = {
            "agent_registry": agent_registry,
            "workflow_registry": workflow_registry,
        }
        if "capability_catalog" in inspect.signature(register_pack).parameters:
            if capability_catalog is None:
                raise ValueError(
                    f"pack requires capability catalog: {manifest.module}"
                )
            kwargs["capability_catalog"] = capability_catalog
        if "manifest" in inspect.signature(register_pack).parameters:
            kwargs["manifest"] = manifest
        register_pack(**kwargs)
        for agent in agent_registry.all():
            if id(agent) in before_agents:
                continue
            agent.profile = agent.profile.model_copy(
                update={
                    "source": "plugin",
                    "plugin_id": manifest.pack_id,
                    "plugin_version": manifest.version,
                    "contribution_id": agent.profile.contribution_id
                    or agent.profile.agent_name,
                }
            )
        for workflow in workflow_registry.all():
            if workflow.workflow_id in before_workflows:
                continue
            workflow.source = "plugin"
            workflow.plugin_id = manifest.pack_id
            workflow.plugin_version = manifest.version
            workflow.contribution_id = workflow.contribution_id or workflow.workflow_id
        if capability_catalog is not None:
            for descriptor in capability_catalog.available():
                if descriptor.capability_id in before_capabilities:
                    continue
                descriptor.source = "plugin"
                descriptor.plugin_id = manifest.pack_id
                descriptor.plugin_version = manifest.version
                descriptor.contribution_id = (
                    descriptor.contribution_id or descriptor.capability_id
                )
        actual_agents = {
            agent_registry.agent_id(agent)
            for agent in agent_registry.all()
            if id(agent) not in before_agents
        }
        actual_workflows = {
            workflow.workflow_id
            for workflow in workflow_registry.all()
            if workflow.workflow_id not in before_workflows
        }
        actual_capabilities = (
            {
                descriptor.capability_id
                for descriptor in capability_catalog.available()
                if descriptor.capability_id not in before_capabilities
            }
            if capability_catalog is not None
            else set()
        )
        declared_and_actual = (
            ("agents", set(manifest.agents), actual_agents),
            ("workflows", set(manifest.workflows), actual_workflows),
            ("capabilities", set(manifest.capabilities), actual_capabilities),
        )
        for kind, declared, actual in declared_and_actual:
            if declared and declared != actual:
                raise ValueError(
                    f"pack {manifest.pack_id} {kind} contribution mismatch: "
                    f"declared={sorted(declared)}, actual={sorted(actual)}"
                )
        registered.append(manifest)
    return tuple(registered)


def default_packs_dir() -> Path:
    """返回应用层 Pack 目录。优先使用迁移后的 agent/packs 路径，旧路径仅作兜底。"""

    configured = os.getenv("AGENTOS_PACKS_DIR", "").strip()
    if configured:
        return Path(configured).resolve()
    project_root = Path(__file__).resolve().parents[4]
    return (project_root / "agent" / "packs").resolve()


def pack_path(pack_id: str, *parts: str) -> Path:
    """解析应用层 Pack 内部资源路径。"""

    return default_packs_dir().joinpath(pack_id, *parts)


def _load_manifest_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except ModuleNotFoundError:
        data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError(f"pack manifest must be an object: {path}")
    return data


def _stable_hash(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
