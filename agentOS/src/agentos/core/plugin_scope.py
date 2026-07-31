"""Per-run visibility snapshots over process-wide installed contributions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from agentos.core.models.types import PluginSnapshot, RunExecutionScope


def stable_revision(value) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PluginScopeError(ValueError):
    """A requested or restored plugin scope cannot be honored."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class PluginScopeResolver:
    """Resolve immutable Run scopes without mutating shared registries."""

    def __init__(
        self,
        *,
        capability_catalog,
        agent_registry,
        workflow_registry,
        manifests: Iterable = (),
    ) -> None:
        self.capability_catalog = capability_catalog
        self.agent_registry = agent_registry
        self.workflow_registry = workflow_registry
        self.manifests = tuple(manifests)

    def resolve_enabled_plugin_ids(
        self,
        requested: list[str] | tuple[str, ...] | None,
        *,
        workflow_id: str | None,
        domain: str,
        intent: str,
    ) -> tuple[str, ...]:
        installed = self._installed_plugin_ids()
        if requested is None:
            workflow = None
            if workflow_id:
                workflow = self.workflow_registry.get(workflow_id)
            else:
                workflow = self.workflow_registry.recommend(domain, intent)
            plugin_id = getattr(workflow, "plugin_id", None) if workflow else None
            resolved = (plugin_id,) if plugin_id else ()
        else:
            resolved = tuple(
                dict.fromkeys(
                    str(item).strip() for item in requested if str(item).strip()
                )
            )

        unknown = sorted(set(resolved) - installed)
        if unknown:
            raise PluginScopeError(
                "PLUGIN_NOT_AVAILABLE", ", ".join(unknown)
            )
        return resolved

    def build_scope(self, enabled_plugin_ids: Iterable[str]) -> RunExecutionScope:
        enabled = tuple(dict.fromkeys(enabled_plugin_ids))
        enabled_set = set(enabled)
        capabilities = tuple(
            descriptor
            for descriptor in self.capability_catalog.available()
            if descriptor.source == "native" or descriptor.plugin_id in enabled_set
        )
        agents = tuple(
            agent
            for agent in self.agent_registry.all()
            if agent.profile.source == "native" or agent.profile.plugin_id in enabled_set
        )
        workflows = tuple(
            workflow
            for workflow in self.workflow_registry.all()
            if workflow.source == "native" or workflow.plugin_id in enabled_set
        )
        snapshots = tuple(self._snapshot(plugin_id) for plugin_id in enabled)
        catalog_payload = [
            descriptor.model_dump(by_alias=True, mode="json")
            for descriptor in sorted(capabilities, key=lambda item: item.capability_id)
        ]
        return RunExecutionScope(
            enabledPluginIds=enabled,
            capabilityIds=tuple(item.capability_id for item in capabilities),
            agentIds=tuple(
                self.agent_registry.agent_id(agent) for agent in agents
            ),
            workflowIds=tuple(item.workflow_id for item in workflows),
            pluginSnapshots=snapshots,
            capabilityCatalogRevision=stable_revision(catalog_payload),
        )

    def validate_snapshot(self, scope: RunExecutionScope) -> None:
        current_plugins = self._installed_plugin_ids()
        for expected in scope.plugin_snapshots:
            if expected.plugin_id not in current_plugins:
                raise PluginScopeError(
                    "PLUGIN_SNAPSHOT_UNAVAILABLE", expected.plugin_id
                )
            current = self._snapshot(expected.plugin_id)
            if current != expected:
                raise PluginScopeError(
                    "PLUGIN_SNAPSHOT_CHANGED", expected.plugin_id
                )
        current_scope = self.build_scope(scope.enabled_plugin_ids)
        if (
            current_scope.capability_catalog_revision
            != scope.capability_catalog_revision
        ):
            raise PluginScopeError(
                "PLUGIN_SNAPSHOT_CHANGED", "capability catalog revision"
            )

    def scoped_catalog(self, scope: RunExecutionScope):
        return self.capability_catalog.scoped(scope.capability_ids)

    def scoped_agents(self, scope: RunExecutionScope):
        return self.agent_registry.scoped(scope.agent_ids)

    def scoped_workflows(self, scope: RunExecutionScope):
        return self.workflow_registry.scoped(scope.workflow_ids)

    def installed_plugin_projection(self) -> list[dict]:
        """Return safe read-only metadata for UI plugin selection."""

        projections = []
        for manifest in sorted(self.manifests, key=lambda item: item.pack_id):
            contributions = self._actual_contributions(manifest.pack_id)
            projections.append(
                {
                    "pluginId": manifest.pack_id,
                    "version": manifest.version,
                    "displayName": manifest.name,
                    "description": manifest.description,
                    "available": bool(manifest.enabled),
                    "capabilityCount": len(contributions["capabilities"]),
                    "agentCount": len(contributions["agents"]),
                    "workflowCount": len(contributions["workflows"]),
                    "uiExtensionId": manifest.ui_extension_id,
                }
            )
        return projections

    def _installed_plugin_ids(self) -> set[str]:
        ids = {manifest.pack_id for manifest in self.manifests if manifest.enabled}
        ids.update(
            descriptor.plugin_id
            for descriptor in self.capability_catalog.available()
            if descriptor.source == "plugin" and descriptor.plugin_id
        )
        ids.update(
            agent.profile.plugin_id
            for agent in self.agent_registry.all()
            if agent.profile.source == "plugin" and agent.profile.plugin_id
        )
        ids.update(
            workflow.plugin_id
            for workflow in self.workflow_registry.all()
            if workflow.source == "plugin" and workflow.plugin_id
        )
        return set(ids)

    def _snapshot(self, plugin_id: str) -> PluginSnapshot:
        manifest = next(
            (item for item in self.manifests if item.pack_id == plugin_id),
            None,
        )
        contributions = self._actual_contributions(plugin_id)
        if manifest is not None:
            version = manifest.version
            manifest_hash = manifest.manifest_hash
        else:
            versions = {
                item
                for item in contributions.pop("versions")
                if item
            }
            version = sorted(versions)[-1] if versions else "0.0.0"
            manifest_hash = stable_revision(
                {"id": plugin_id, "version": version, "contributions": contributions}
            )
        contributions.pop("versions", None)
        return PluginSnapshot(
            pluginId=plugin_id,
            version=version,
            manifestHash=manifest_hash,
            contributionRevision=stable_revision(contributions),
        )

    def _actual_contributions(self, plugin_id: str) -> dict[str, list[str]]:
        capabilities = sorted(
            descriptor.capability_id
            for descriptor in self.capability_catalog.available()
            if descriptor.plugin_id == plugin_id
        )
        agents = sorted(
            self.agent_registry.agent_id(agent)
            for agent in self.agent_registry.all()
            if agent.profile.plugin_id == plugin_id
        )
        workflows = sorted(
            workflow.workflow_id
            for workflow in self.workflow_registry.all()
            if workflow.plugin_id == plugin_id
        )
        versions = sorted(
            {
                *(descriptor.plugin_version for descriptor in self.capability_catalog.available() if descriptor.plugin_id == plugin_id),
                *(agent.profile.plugin_version for agent in self.agent_registry.all() if agent.profile.plugin_id == plugin_id),
                *(workflow.plugin_version for workflow in self.workflow_registry.all() if workflow.plugin_id == plugin_id),
            }
            - {None}
        )
        return {
            "capabilities": capabilities,
            "agents": agents,
            "workflows": workflows,
            "versions": versions,
        }


__all__ = [
    "PluginScopeError",
    "PluginScopeResolver",
    "stable_revision",
]
