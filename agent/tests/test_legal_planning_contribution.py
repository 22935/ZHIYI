"""Legal Pack ownership and shared planning-catalog registration tests."""

from pathlib import Path

import pytest

from agentos.agents import AgentRegistry
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from agentos.packs.registry import discover_pack_manifests
from packs.legal import register_pack as register_legal_pack
from packs.legal.planning import (
    LEGAL_CAPABILITY_IDS,
    legal_capability_descriptors,
    register_legal_capabilities,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_legal_pack_registers_shared_catalog_and_manifest_consistently():
    runtime = WorkflowRuntime(
        agent_registry=AgentRegistry(),
        workflow_registry=WorkflowRegistry(),
    )
    planning_engine = runtime.planning_engine

    with pytest.raises(KeyError):
        runtime.capability_catalog.get("风险识别")

    register_legal_pack(
        agent_registry=runtime.agent_registry,
        workflow_registry=runtime.workflow_registry,
        capability_catalog=runtime.capability_catalog,
    )

    assert planning_engine.capability_catalog is runtime.capability_catalog
    assert set(LEGAL_CAPABILITY_IDS) == {
        descriptor.capability_id for descriptor in legal_capability_descriptors()
    }
    manifest = next(
        manifest
        for manifest in discover_pack_manifests()
        if manifest.pack_id == "kinlin.legal"
    )
    assert set(LEGAL_CAPABILITY_IDS) == set(manifest.capabilities)
    assert set(manifest.agents) == {
        agent.profile.agent_name
        for agent in runtime.agent_registry.all()
        if agent.profile.plugin_id == "kinlin.legal"
    }
    assert set(manifest.workflows) == {
        workflow.workflow_id
        for workflow in runtime.workflow_registry.all()
        if workflow.plugin_id == "kinlin.legal"
    }
    assert runtime.capability_catalog.resolve("法律知识应用").capability_id == "证据检索"
    assert runtime.capability_catalog.get("风险识别").risk_level_hint == "high"
    assert runtime.capability_catalog.get("证据检索").requires_evidence is True
    assert runtime.capability_catalog.get("人工审核").requires_review is True
    assert runtime.capability_catalog.get("人工审核").risk_level_hint == "elevated"
    assert runtime.workflow_registry.get("legal_contract_review_v1").domain == "legal"
    assert runtime.agent_registry.resolve(
        "legal", agent_name="risk_detect"
    ).profile.agent_name == "risk_detect"
    runtime.capability_catalog.validate()


def test_legal_pack_registration_is_idempotent_and_partial_catalog_is_rejected():
    runtime = WorkflowRuntime()
    kwargs = {
        "agent_registry": runtime.agent_registry,
        "workflow_registry": runtime.workflow_registry,
        "capability_catalog": runtime.capability_catalog,
    }

    register_legal_pack(**kwargs)
    register_legal_pack(**kwargs)

    assert {item.capability_id for item in runtime.capability_catalog.available("legal")} >= set(
        LEGAL_CAPABILITY_IDS
    )

    partial = build_default_capability_catalog()
    partial.register(legal_capability_descriptors()[0])
    with pytest.raises(ValueError, match="partial Legal Pack"):
        register_legal_capabilities(partial)


def test_core_source_has_no_legal_pack_dependency_or_compatibility_copy():
    core = PROJECT_ROOT / "agentOS" / "src" / "agentos"
    planning = core / "core" / "planning"
    forbidden = (
        "from agent.packs.legal",
        "import agent.packs.legal",
        "planning.compat.legal_legacy",
        "register_legal_compatibility_capabilities",
    )

    assert not (planning / "compat" / "legal_legacy.py").exists()
    for path in core.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert all(marker not in text for marker in forbidden), path
