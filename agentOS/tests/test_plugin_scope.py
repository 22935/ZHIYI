from pathlib import Path

import pytest

from agentos.agents import AgentOutput, AgentProfile, AgentRegistry, BaseAgent
from agentos.core.models.types import (
    PluginSnapshot,
    RunExecutionScope,
    WorkflowDefinition,
    WorkflowStepDefinition,
)
from agentos.core.native import register_native_runtime
from agentos.core.planning import PlanningCapabilityDescriptor
from agentos.core.planning.intent_parser import IntentParser
from agentos.core.recovery.bindings import CandidateResolver
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.plugin_scope import PluginScopeError, PluginScopeResolver
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.packs.registry import PackManifest


class _PluginAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            AgentProfile(
                agentName="plugin_agent",
                domain="special",
                capabilities=["plugin_capability"],
                source="plugin",
                pluginId="sample.plugin",
                pluginVersion="1.0.0",
                contributionId="plugin_agent",
            )
        )

    async def run(self, context):
        return AgentOutput(output={"result": "ok"})


def _resolver():
    catalog = build_default_capability_catalog()
    catalog.register(
        PlanningCapabilityDescriptor(
            capabilityId="plugin_capability",
            displayName="Plugin capability",
            aliases=["plugin work"],
            domainHints=["special"],
            source="plugin",
            pluginId="sample.plugin",
            pluginVersion="1.0.0",
            contributionId="plugin_capability",
        )
    )
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    register_native_runtime(agent_registry=agents, workflow_registry=workflows)
    agents.register(_PluginAgent())
    workflows.register(
        WorkflowDefinition(
            workflowId="sample_workflow",
            name="Sample",
            domain="special",
            intent="run",
            runtimeEngine="acg",
            steps=[
                WorkflowStepDefinition(
                    stepId="sample",
                    name="Sample",
                    agentName="plugin_agent",
                    capability="plugin_capability",
                )
            ],
            source="plugin",
            pluginId="sample.plugin",
            pluginVersion="1.0.0",
            contributionId="sample_workflow",
        )
    )
    return PluginScopeResolver(
        capability_catalog=catalog,
        agent_registry=agents,
        workflow_registry=workflows,
    )


def test_manifest_hash_and_contribution_revision_are_canonical():
    common = dict(
        pack_id="sample.plugin",
        name="Sample",
        version="1.0.0",
        description="Sample",
        module="packs.sample",
        enabled=True,
        path=Path("manifest.yaml"),
    )
    first = PackManifest(
        **common,
        capabilities=("b", "a"),
        agents=("agent_b", "agent_a"),
        workflows=("workflow_b", "workflow_a"),
    )
    reordered = PackManifest(
        **common,
        capabilities=("a", "b"),
        agents=("agent_a", "agent_b"),
        workflows=("workflow_a", "workflow_b"),
    )
    changed = PackManifest(
        **common,
        capabilities=("a", "c"),
        agents=("agent_a", "agent_b"),
        workflows=("workflow_a", "workflow_b"),
    )

    assert first.manifest_hash == reordered.manifest_hash
    assert first.contribution_revision == reordered.contribution_revision
    assert changed.contribution_revision != first.contribution_revision


def test_installed_plugin_projection_exposes_only_safe_metadata():
    resolver = _resolver()
    projection = resolver.installed_plugin_projection()

    assert projection == []

    manifest = PackManifest(
        pack_id="sample.plugin",
        name="Sample",
        version="1.0.0",
        description="Sample plugin",
        module="packs.sample",
        enabled=True,
        capabilities=("plugin_capability",),
        agents=("plugin_agent",),
        workflows=("sample_workflow",),
        path=Path("manifest.yaml"),
        ui_extension_id="sample.plugin",
    )
    resolver.manifests = (manifest,)

    assert resolver.installed_plugin_projection() == [{
        "pluginId": "sample.plugin",
        "version": "1.0.0",
        "displayName": "Sample",
        "description": "Sample plugin",
        "available": True,
        "capabilityCount": 1,
        "agentCount": 1,
        "workflowCount": 1,
        "uiExtensionId": "sample.plugin",
    }]


def test_enabled_plugin_tristate_and_unknown_rejection():
    resolver = _resolver()

    assert resolver.resolve_enabled_plugin_ids(
        None, workflow_id=None, domain="general", intent="general"
    ) == ()
    assert resolver.resolve_enabled_plugin_ids(
        [], workflow_id="sample_workflow", domain="special", intent="run"
    ) == ()
    assert resolver.resolve_enabled_plugin_ids(
        None, workflow_id="sample_workflow", domain="special", intent="run"
    ) == ("sample.plugin",)
    assert resolver.resolve_enabled_plugin_ids(
        ["sample.plugin", "sample.plugin"],
        workflow_id=None,
        domain="special",
        intent="run",
    ) == ("sample.plugin",)
    with pytest.raises(PluginScopeError, match="PLUGIN_NOT_AVAILABLE"):
        resolver.resolve_enabled_plugin_ids(
            ["missing.plugin"], workflow_id=None, domain="general", intent="general"
        )


def test_scope_views_include_native_and_only_selected_plugin_contributions():
    resolver = _resolver()
    native = resolver.build_scope(())
    selected = resolver.build_scope(("sample.plugin",))

    assert "plugin_capability" not in native.capability_ids
    assert "plugin_agent" not in native.agent_ids
    assert "sample_workflow" not in native.workflow_ids
    assert "plugin_capability" in selected.capability_ids
    assert "plugin_agent" in selected.agent_ids
    assert "sample_workflow" in selected.workflow_ids
    with pytest.raises(KeyError):
        resolver.scoped_catalog(native).get("plugin_capability")
    assert resolver.scoped_catalog(selected).get("plugin_capability").plugin_id == "sample.plugin"


def test_run_scope_and_snapshot_round_trip_as_frozen_models():
    scope = _resolver().build_scope(("sample.plugin",))
    restored = RunExecutionScope.model_validate(
        scope.model_dump(by_alias=True, mode="json")
    )
    snapshot = PluginSnapshot.model_validate(
        restored.plugin_snapshots[0].model_dump(by_alias=True, mode="json")
    )

    assert restored == scope
    assert snapshot.plugin_id == "sample.plugin"
    with pytest.raises(Exception):
        restored.enabled_plugin_ids = ()


def test_global_registration_after_scope_creation_does_not_expand_old_scope():
    resolver = _resolver()
    old_scope = resolver.build_scope(())
    resolver.capability_catalog.register(
        PlanningCapabilityDescriptor(
            capabilityId="late_capability",
            displayName="Late capability",
            source="plugin",
            pluginId="late.plugin",
            pluginVersion="1.0.0",
            contributionId="late_capability",
        )
    )
    new_scope = resolver.build_scope(("late.plugin",))

    resolver.validate_snapshot(old_scope)
    assert old_scope.enabled_plugin_ids == ()
    assert "late_capability" not in old_scope.capability_ids
    assert "late_capability" in new_scope.capability_ids


def test_snapshot_validation_detects_contribution_change():
    resolver = _resolver()
    scope = resolver.build_scope(("sample.plugin",))
    descriptor = resolver.capability_catalog.get("plugin_capability")
    descriptor.description = "changed after the run started"

    with pytest.raises(PluginScopeError, match="PLUGIN_SNAPSHOT_CHANGED"):
        resolver.validate_snapshot(scope)


def test_scoped_parser_drops_llm_capability_outside_run_scope():
    class _LLM:
        def generate_json(self, prompt, schema):
            return {
                "primaryGoal": "Attempt plugin work",
                "requiredCapabilities": ["plugin_capability"],
                "estimatedComplexity": "medium",
            }

    resolver = _resolver()
    native_scope = resolver.build_scope(())
    parser = IntentParser(_LLM(), resolver.scoped_catalog(native_scope))

    profile = parser.parse(
        intent="plugin work",
        domain="general",
        task_type="general",
    )

    assert "plugin_capability" not in profile.required_capabilities
    assert profile.required_capabilities == [
        "task_understanding",
        "analysis",
        "artifact_generation",
    ]


def test_candidate_scope_is_a_hard_filter_before_binding_ranking():
    resolver = _resolver()
    native_scope = resolver.build_scope(())
    selected_scope = resolver.build_scope(("sample.plugin",))
    candidates = CandidateResolver(resolver.agent_registry)

    assert candidates.resolve_candidates(
        domain="special",
        capability="plugin_capability",
        allowed_agent_ids=native_scope.agent_ids,
    ) == []
    assert candidates.resolve_candidates(
        domain="special",
        capability="plugin_capability",
        allowed_agent_ids=selected_scope.agent_ids,
    )[0].plugin_id == "sample.plugin"
