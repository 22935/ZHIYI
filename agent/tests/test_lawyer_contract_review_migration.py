import pytest

from agentos.agents import AgentRegistry
from agentos.core.runtime import WorkflowRuntime
from agentos.core.workflow.registry import WorkflowRegistry
from packs.legal import register_pack as register_legal_pack


def test_canonical_contract_review_has_no_legacy_engine_aliases():
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    register_legal_pack(
        agent_registry=agents,
        workflow_registry=workflows,
        capability_catalog=runtime.capability_catalog,
    )
    workflow = workflows.get("legal_contract_review_v1")
    assert workflow.runtime_engine == "acg"
    assert workflow.implementation_id is None
    assert workflow.aliases == []
    with pytest.raises(KeyError):
        workflows.get("legal_contract_review_legacy_v1")


def test_public_step_ids_map_to_acg_agents():
    agents = AgentRegistry()
    workflows = WorkflowRegistry()
    runtime = WorkflowRuntime(agent_registry=agents, workflow_registry=workflows)
    register_legal_pack(
        agent_registry=agents,
        workflow_registry=workflows,
        capability_catalog=runtime.capability_catalog,
    )
    workflow = workflows.get("legal_contract_review_v1")
    assert [(step.step_id, step.agent_name) for step in workflow.steps] == [
        ("parse_contract", "contract_parse"),
        ("classify_clauses", "clause_classify"),
        ("risk_detect", "risk_detect"),
        ("legal_evidence_match", "legal_evidence_match"),
        ("suggestion_generate", "revision_suggest"),
        ("human_review", "human_review"),
        ("report_generate", "report_generate"),
    ]
