from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agentos.adapters.model_adapter import (
    StructuredGenerationError,
    StructuredGenerationResult,
)
from agentos.agents import AgentRegistry
from agentos.agents.base import AgentRunContext
from agentos.core.data_contracts import apply_contract_defaults
from agentos.core.models.types import (
    AgentTask,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)
from agentos.core.native import NativeGeneralAgent
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.memory.workflow_memory import WorkflowMemory
from agentos.core.workflow.orchestrator import Orchestrator


class _RepairRuntime:
    def __init__(self, valid_runtime):
        self.valid_runtime = valid_runtime
        self.calls = 0

    def is_available(self):
        return True

    async def generate_json(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return StructuredGenerationResult(
                data={"task_summary": "incomplete"},
                provider="test-provider",
                model="test-model",
                promptVersion=kwargs["prompt_version"],
            )
        return await self.valid_runtime.generate_json(**kwargs)


class _JsonRepairRuntime:
    def __init__(self, valid_runtime, *, invalid_after_retry=False):
        self.valid_runtime = valid_runtime
        self.invalid_after_retry = invalid_after_retry
        self.calls = []

    def is_available(self):
        return True

    async def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise StructuredGenerationError(
                "MODEL_OUTPUT_INVALID_JSON",
                "Invalid JSON returned by provider: Unterminated string",
            )
        if self.invalid_after_retry:
            return StructuredGenerationResult(
                data={"task_summary": "still incomplete"},
                provider="test-provider",
                model="test-model",
                promptVersion=kwargs["prompt_version"],
            )
        return await self.valid_runtime.generate_json(**kwargs)


class _ThinkingFinalizationRuntime:
    def __init__(self, valid_runtime, *, fail_always=False):
        self.valid_runtime = valid_runtime
        self.fail_always = fail_always
        self.calls = []

    def is_available(self):
        return True

    async def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1 or self.fail_always:
            raise StructuredGenerationError(
                "MODEL_EMPTY_RESPONSE",
                "OpenAI-compatible provider returned empty JSON content",
            )
        return await self.valid_runtime.generate_json(**kwargs)


class _FixedRuntime:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def is_available(self):
        return True

    async def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        return StructuredGenerationResult(
            data=self.data,
            provider="test-provider",
            model="test-model",
            promptVersion=kwargs["prompt_version"],
        )


def _context(
    model_runtime,
    *,
    objective="Design a measurable delivery plan",
    capability="task_understanding",
    thinking_mode="disabled",
):
    catalog = build_default_capability_catalog()
    descriptor = catalog.get(capability)
    task = AgentTask(
        title=objective,
        input={"userIntent": objective, "thinkingMode": thinking_mode},
    )
    run = WorkflowRun(
        taskId=task.task_id,
        workflowId="native_test",
        domain="general",
        runtimeEngine="acg",
        input=dict(task.input),
    )
    workflow = WorkflowDefinition(
        workflowId="native_test",
        name="Native test",
        domain="general",
        intent="general",
        runtimeEngine="acg",
        steps=[],
        definitionType="native_bootstrap",
    )
    step = WorkflowStep(
        stepId="execute",
        name=f"Execute {capability}",
        agentName="native_general_agent",
        capability=capability,
        outputSpec=descriptor.output_contract,
    )
    return AgentRunContext(
        task=task,
        run=run,
        workflow=workflow,
        step=step,
        memory=WorkflowMemory(run_id=run.run_id, task_input=dict(task.input)),
        modelRuntime=model_runtime,
        capabilityDescriptor=descriptor,
    )


def test_native_agent_repairs_invalid_structured_output_once(structured_model_runtime):
    runtime = _RepairRuntime(structured_model_runtime)

    result = asyncio.run(NativeGeneralAgent().run(_context(runtime)))

    assert runtime.calls == 2
    assert len(result.model_invocations) == 2
    assert result.output["constraints"]


def test_native_prompt_is_input_sensitive_and_domain_neutral(structured_model_runtime):
    agent = NativeGeneralAgent()

    asyncio.run(agent.run(_context(structured_model_runtime, objective="Plan alpha")))
    asyncio.run(agent.run(_context(structured_model_runtime, objective="Plan beta")))

    prompts = [item["prompt"] for item in structured_model_runtime.calls]
    assert "Plan alpha" in prompts[0]
    assert "Plan beta" in prompts[1]
    assert all("industrial_graph" not in prompt for prompt in prompts)
    assert all("software_graph" not in prompt for prompt in prompts)


def test_native_prompt_deduplicates_workbench_task_text(structured_model_runtime):
    objective = "Unique canonical objective with measurable constraints"
    context = _context(structured_model_runtime, objective=objective)
    context.task.input.update({"taskGoal": objective, "materialText": objective})

    asyncio.run(NativeGeneralAgent().run(context))

    prompt = structured_model_runtime.calls[-1]["prompt"]
    assert prompt.count(objective) == 1
    assert "authenticatedUserId" not in prompt


def test_native_agent_repairs_truncated_json_once(structured_model_runtime):
    runtime = _JsonRepairRuntime(structured_model_runtime)

    result = asyncio.run(NativeGeneralAgent().run(_context(runtime)))

    assert len(runtime.calls) == 2
    assert runtime.calls[-1]["prompt_version"].endswith(".json-repair1")
    assert "smaller response" in runtime.calls[-1]["prompt"]
    assert result.output["constraints"]


def test_native_agent_materializes_final_json_after_thinking_returns_empty_content(
    structured_model_runtime,
):
    runtime = _ThinkingFinalizationRuntime(structured_model_runtime)

    result = asyncio.run(
        NativeGeneralAgent().run(_context(runtime, thinking_mode="standard"))
    )

    assert [call["thinking_mode"] for call in runtime.calls] == [
        "standard",
        "disabled",
    ]
    assert runtime.calls[-1]["prompt_version"].endswith(".thinking-finalization1")
    assert result.output["constraints"]
    assert result.model_invocations[-1]["usage"] == {
        "thinkingFallback": True,
        "thinkingFallbackReason": "MODEL_EMPTY_RESPONSE",
        "requestedThinkingMode": "standard",
        "effectiveThinkingMode": "disabled",
    }


def test_native_agent_does_not_hide_empty_content_when_thinking_is_disabled(
    structured_model_runtime,
):
    runtime = _ThinkingFinalizationRuntime(structured_model_runtime)

    with pytest.raises(StructuredGenerationError) as raised:
        asyncio.run(
            NativeGeneralAgent().run(_context(runtime, thinking_mode="disabled"))
        )

    assert raised.value.code == "MODEL_EMPTY_RESPONSE"
    assert len(runtime.calls) == 1


def test_native_agent_stops_after_one_thinking_finalization_attempt(
    structured_model_runtime,
):
    runtime = _ThinkingFinalizationRuntime(
        structured_model_runtime,
        fail_always=True,
    )

    with pytest.raises(StructuredGenerationError) as raised:
        asyncio.run(
            NativeGeneralAgent().run(_context(runtime, thinking_mode="deep"))
        )

    assert raised.value.code == "MODEL_EMPTY_RESPONSE"
    assert [call["thinking_mode"] for call in runtime.calls] == ["deep", "disabled"]


def test_native_agent_never_uses_more_than_one_repair(structured_model_runtime):
    runtime = _JsonRepairRuntime(structured_model_runtime, invalid_after_retry=True)

    with pytest.raises(StructuredGenerationError) as raised:
        asyncio.run(NativeGeneralAgent().run(_context(runtime)))

    assert raised.value.code == "OUTPUT_CONTRACT_VIOLATION"
    assert len(runtime.calls) == 2


def test_native_analysis_contract_bounds_response_shape():
    schema = build_default_capability_catalog().get("analysis").output_contract
    properties = schema["properties"]["analysis"]["properties"]

    assert properties["findings"]["maxItems"] == 12
    assert properties["findings"]["items"]["maxLength"] == 400
    assert properties["assumptions"]["maxItems"] == 12
    assert properties["assumptions"]["default"] == []
    assert properties["gaps"]["maxItems"] == 12
    assert properties["gaps"]["default"] == []


def test_contract_defaults_are_schema_driven_and_do_not_mutate_model_output():
    payload = {"analysis": {"findings": ["finding"]}}
    schema = build_default_capability_catalog().get("analysis").output_contract

    normalized = apply_contract_defaults(payload, schema)

    assert payload == {"analysis": {"findings": ["finding"]}}
    assert normalized["analysis"]["assumptions"] == []
    assert normalized["analysis"]["gaps"] == []


def test_native_analysis_accepts_ten_findings_and_declared_empty_defaults():
    findings = [f"finding {index}" for index in range(10)]
    runtime = _FixedRuntime({"analysis": {"findings": findings}})

    result = asyncio.run(
        NativeGeneralAgent().run(_context(runtime, capability="analysis"))
    )

    assert len(runtime.calls) == 1
    assert result.output == {
        "analysis": {
            "findings": findings,
            "assumptions": [],
            "gaps": [],
        }
    }


def test_failed_run_has_partial_artifacts_but_no_completion_message():
    run = WorkflowRun(
        taskId="task_failed",
        workflowId="native_test",
        domain="general",
        runtimeEngine="acg",
        status=WorkflowStatus.FAILED,
        steps=[
            WorkflowStep(
                stepId="understand",
                name="Task understanding",
                agentName="native_general_agent",
                status="completed",
                output={"task_summary": "partial"},
            )
        ],
    )

    output = Orchestrator(AgentRegistry()).compose_final_output(run)

    assert "final_answer" not in output
    assert output["artifacts"] == {"understand": {"task_summary": "partial"}}


def test_artifact_generation_consumes_all_upstream_and_normalizes_envelope(
    structured_model_runtime,
):
    catalog = build_default_capability_catalog()
    descriptor = catalog.get("artifact_generation")
    task = AgentTask(
        title="Factory delivery plan",
        input={"userIntent": "Produce one complete delivery plan"},
    )
    run = WorkflowRun(
        runId="run_artifact",
        taskId=task.task_id,
        workflowId="native_test",
        domain="general",
        runtimeEngine="acg",
        input=dict(task.input),
    )
    workflow = WorkflowDefinition(
        workflowId="native_test",
        name="Native test",
        domain="general",
        intent="general",
        runtimeEngine="acg",
        steps=[],
        definitionType="native_bootstrap",
    )
    step = WorkflowStep(
        stepId="deliver",
        name="Compose final artifact",
        agentName="native_general_agent",
        capability="artifact_generation",
        outputSpec=descriptor.output_contract,
        attempt=2,
    )
    upstream = {
        "task_summary": "Build a production line",
        "requirements": [{"id": "R1"}],
        "acceptance_criteria": [{"target": "55 seconds"}],
        "capacity_plan": {"conclusion": "240000 units/year"},
        "cost_analysis": {"total": 8000000},
        "risks": [{"risk": "schedule"}],
        "verification": {"status": "partial"},
    }
    context = AgentRunContext(
        task=task,
        run=run,
        workflow=workflow,
        step=step,
        memory=WorkflowMemory(run_id=run.run_id, task_input=dict(task.input)),
        contextPack=SimpleNamespace(
            data=upstream,
            source_data={"upstream": upstream},
            evidence_refs=["source-1"],
        ),
        modelRuntime=structured_model_runtime,
        capabilityDescriptor=descriptor,
    )

    result = asyncio.run(NativeGeneralAgent().run(context))

    prompt = structured_model_runtime.calls[-1]["prompt"]
    generation_schema = structured_model_runtime.calls[-1]["schema"]
    for field in upstream:
        assert field in prompt
    assert "consumeAllRelevantUpstreamFields" in prompt
    assert set(generation_schema["properties"]) == {"deliverable", "verification"}
    assert set(generation_schema["required"]) == {"deliverable", "verification"}
    assert "final_answer" not in generation_schema["properties"]
    assert "artifact" not in generation_schema["properties"]
    assert result.output["final_answer"].startswith("# generated:title")
    assert result.output["artifact"] == {
        "artifactId": "artifact_52676df0e94b2d89",
        "type": "report",
        "title": "generated:title",
        "mediaType": "text/markdown",
        "content": result.output["final_answer"],
        "structuredData": result.output["deliverable"],
    }
    assert result.output["verification"]["status"] == "passed"


def test_artifact_markdown_is_deterministically_rendered_from_semantic_output():
    runtime = _FixedRuntime(
        {
            "deliverable": {
                "title": "知识库整理计划",
                "executiveSummary": "两周内完成可验收的知识整理。",
                "sections": [
                    {
                        "title": "实施阶段",
                        "content": "先盘点，再整理，最后验收。",
                        "sourceFields": ["requirements"],
                    }
                ],
                "calculations": [
                    {
                        "name": "工作量",
                        "formula": "文档数 / 每日处理量",
                        "inputs": ["100 份", "20 份/天"],
                        "result": "5 天",
                        "assumptions": ["资料可访问"],
                    }
                ],
                "assumptions": ["负责人按时参与"],
                "openQuestions": ["历史资料保留期限"],
                "sourceRefs": ["src-1"],
            },
            "verification": {
                "status": "partial",
                "checks": [
                    {
                        "criterion": "范围明确",
                        "result": "通过",
                        "evidence": "requirements",
                    }
                ],
                "unresolvedGaps": ["待确认保留期限"],
            },
        }
    )

    result = asyncio.run(
        NativeGeneralAgent().run(_context(runtime, capability="artifact_generation"))
    )

    final_answer = result.output["final_answer"]
    assert "# 知识库整理计划" in final_answer
    assert "## 实施阶段" in final_answer
    assert "## 计算与依据" in final_answer
    assert "## 验收核对" in final_answer
    assert result.output["artifact"]["content"] == final_answer
    assert result.output["artifact"]["structuredData"] == result.output["deliverable"]
