"""Initial planning must target the DAG-only formal materialization contract."""
from copy import deepcopy

import pytest

from components.planner.task_decomposer import TaskDecomposer, TaskDecompositionError
from support.acg.models import TaskSemanticProfile, build_default_capability_catalog


class Model:
    def __init__(self, *responses):
        self.responses = responses
        self.calls = []

    def generate_json(self, prompt, schema, **kwargs):
        self.calls.append(dict(prompt=prompt, schema=deepcopy(schema), **kwargs))
        return deepcopy(self.responses[len(self.calls) - 1])


def candidate(loop=True):
    return {"tasks": [
        {"key": key, "title": key, "objective": objective, "capabilityId": capability,
         "acceptanceCriteria": ["Evidence is recorded"], "sourceRefs": [],
         "logicalRole": role, "decompositionRationale": "Preserve acceptance obligations"}
        for key, objective, capability, role in (
            ("understand", "Resolve activity goals and constraints", "task_understanding", "task"),
            ("refine", "Prepare and correct the activity deliverables", "solution_design", "decision"),
            ("verify", "Verify every activity acceptance criterion", "verification", "verification"))],
        "relations": [{"sourceKey": "understand", "targetKey": "refine", "relationType": "depends_on"},
                      {"sourceKey": "refine", "targetKey": "verify", "relationType": "depends_on"}],
        "controlPolicies": [{"type": "verification_loop", "bodyEntryKey": "refine", "bodyExitKey": "verify",
                             "conditionSourceKey": "verify", "maxRevisions": 2}] if loop else []}


def plan(model, strategy="initial_commit_candidate", full=False):
    return TaskDecomposer(build_default_capability_catalog(), model).decompose(
        mission_id="mission_0123456789ab",
        profile=TaskSemanticProfile(primaryGoal="Prepare and verify activity files",
                                    requiredCapabilities=["task_understanding", "solution_design", "verification"]),
        strategy=strategy, task_input={"_effectiveCapabilityProfile": "full"} if full else {}, use_llm=True)


def test_initial_commit_repairs_a_loop_candidate_before_acceptance():
    model = Model(candidate(), candidate(False))
    result = plan(model)
    assert not result.control_policies
    assert len(model.calls) == 2
    assert model.calls[0]["schema"]["properties"]["controlPolicies"]["maxItems"] == 0
    assert "INITIAL DAG CONTRACT" in model.calls[0]["prompt"]
    assert "INITIAL_CONTROL_GRAPH_UNSUPPORTED" in model.calls[1]["prompt"]
    assert {"refine", "verify"}.issubset({node.title for node in result.nodes})


def test_initial_commit_rejects_persistently_unsupported_loops_after_one_repair():
    model = Model(candidate(), candidate())
    with pytest.raises(TaskDecompositionError, match="INITIAL_CONTROL_GRAPH_UNSUPPORTED"):
        plan(model)
    assert len(model.calls) == 2


def test_existing_non_initial_planning_keeps_supported_verification_loops():
    model = Model(candidate())
    result = plan(model, strategy="dynamic_generation")
    assert len(result.control_policies) == 1
    assert len(model.calls) == 1


def test_staged_initial_planning_repairs_only_the_relation_unit():
    payload = candidate()
    outline = {"tasks": [{k: task[k] for k in ("key", "title", "capabilityId", "logicalRole", "sourceRefs")}
                         for task in payload["tasks"]]}
    relations = {k: payload[k] for k in ("relations", "controlPolicies")}
    model = Model(outline, {"tasks": payload["tasks"]}, relations, {**relations, "controlPolicies": []})
    result = plan(model, full=True)
    assert not result.control_policies
    assert len(model.calls) == 4
    assert model.calls[2]["schema"]["properties"]["controlPolicies"]["maxItems"] == 0
    assert "INITIAL DAG CONTRACT" in model.calls[2]["prompt"]
    assert model.calls[-1]["prompt_version"].endswith(".relations.initial-dag-repair1")
