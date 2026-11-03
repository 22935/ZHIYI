"""Ordered integration coverage for Packs migrated to the execution runtime."""

from __future__ import annotations

import json

from contracts.memory import MemoryType
from contracts.workflow import WorkflowStatus

from app.execution.wiring import build_default_runtime, close_runtime
from app.tools.contracts import SourceReference, ToolExecutionRecord, ToolRunResult


def _environment(tmp_path, name: str) -> dict[str, str]:
    root = tmp_path / name
    return {
        "AGENTOS_WORKFLOW_DB_PATH": str(root / "workflows.sqlite3"),
        "AGENTOS_LANGGRAPH_CHECKPOINT_DB": str(root / "checkpoints.sqlite3"),
        "AGENTOS_EXECUTION_VALUE_DB": str(root / "values.sqlite3"),
        "AGENTOS_EXECUTION_MEMORY_DB": str(root / "memory.sqlite3"),
        "AGENTOS_PROVENANCE_DB": str(root / "provenance.sqlite3"),
        "AGENTOS_AUDIT_DB": str(root / "decisions.sqlite3"),
    }


def _output(runtime, run, step_id: str) -> dict:
    return runtime.execution_value_store.get_output(
        run_id=run.run_id,
        output_ref=run.execution_state["outputRefs"][step_id],
    )


class _PackToolRuntime:
    def __init__(self, allowed_tools=("codebase_search",)) -> None:
        self.allowed_tools = frozenset(allowed_tools)

    def scoped(self, allowed_tools):
        return _PackToolRuntime(self.allowed_tools.intersection(allowed_tools))

    async def execute(self, name, arguments, **kwargs):
        if name not in self.allowed_tools:
            raise PermissionError(f"tool is not allowed: {name}")
        source = SourceReference(
            citationId="src_pack_code",
            title="apps/agent/app/execution/wiring.py:1",
            filename="apps/agent/app/execution/wiring.py",
            snippet="Composition root",
            provider="pack-fixture",
            retrievedAt="2026-08-15T00:00:00+00:00",
        )
        record = ToolExecutionRecord(
            callId="call_pack_code",
            toolName=name,
            status="completed",
            durationMs=1,
            inputSummary="query, top_k",
            outputSummary="one code hit",
            sourceRefs=[source.citation_id],
        )
        payload = {
            "ok": True,
            "tool": name,
            "data": {
                "results": [
                    {
                        "citationId": source.citation_id,
                        "file_path": source.filename,
                        "line": 1,
                        "language": "python",
                        "score": 1.0,
                        "content": source.snippet,
                    }
                ]
            },
        }
        return ToolRunResult(text=json.dumps(payload), sources=[source], toolExecutions=[record])


async def test_01_general_native_pack_runs_planner_model_and_reference_output(tmp_path) -> None:
    runtime = build_default_runtime(environment=_environment(tmp_path, "native"), tool_runtime=_PackToolRuntime())
    try:
        mission = runtime.create_mission(
            title="Analyze a release plan and provide a verified deliverable",
            domain="general",
            intent="analysis",
            workflow_id="native_acg_runtime_v1",
            input={
                "userIntent": "analyze the release requirements, risks, and verification",
                "usePlanner": True,
                "planningSeed": 42,
                "planningDiversity": "stable",
            },
        )
        run = await runtime.start(mission.mission_id, workflow_id="native_acg_runtime_v1")

        assert run.status is WorkflowStatus.COMPLETED
        assert run.execution_state["selectedCapabilities"]
        assert run.execution_state["outputRefs"]
        assert run.output["outputRef"] in run.execution_state["outputRefs"].values()
        assert all(step.agent_name == "native_general_agent" for step in run.steps)
    finally:
        close_runtime(runtime)


async def test_02_programmer_pack_runs_tool_context_memory_and_output_contracts(tmp_path) -> None:
    runtime = build_default_runtime(
        environment=_environment(tmp_path, "programmer"),
        tool_runtime=_PackToolRuntime(),
    )
    try:
        mission = runtime.create_mission(
            title="Implement a secure FastAPI authentication endpoint",
            domain="programmer",
            intent="requirement_analysis",
            workflow_id="programmer_requirement_analysis_v1",
            input={"requirement": "Implement secure FastAPI authentication", "targetLanguage": "python"},
        )
        run = await runtime.start(mission.mission_id, workflow_id="programmer_requirement_analysis_v1")

        assert run.status is WorkflowStatus.COMPLETED
        assert [step.step_id for step in run.steps] == [
            "task_understanding", "requirement_analysis", "codebase_semantic_search", "code_generation", "diagram_generation"
        ]
        assert _output(runtime, run, "codebase_semantic_search")["evidence_refs"] == ["src_pack_code"]
        assert _output(runtime, run, "code_generation")["context_refs"][0]["file_path"] == "apps/agent/app/execution/wiring.py"
        assert _output(runtime, run, "diagram_generation")["diagram_type"] == "mermaid"
        assert any(event.event_type.value == "tool_called" for event in run.trace)
        assert runtime.memory_store.get(f"memory:{run.run_id}:codebase_semantic_search").memory_type is MemoryType.EVIDENCE
        assert runtime.memory_store.get(f"memory:{run.run_id}:code_generation").memory_type is MemoryType.PROCEDURAL
    finally:
        close_runtime(runtime)


async def test_03_education_pack_runs_declared_profile_memory_and_output_contract(tmp_path) -> None:
    runtime = build_default_runtime(environment=_environment(tmp_path, "education"), tool_runtime=_PackToolRuntime())
    try:
        mission = runtime.create_mission(
            title="Design a lesson about linear equations",
            domain="education",
            intent="lesson_plan",
            workflow_id="education_lesson_plan_v1",
            input={"topic": "linear equations", "subject": "mathematics", "grade": "grade 7"},
        )
        run = await runtime.start(mission.mission_id, workflow_id="education_lesson_plan_v1")

        output = _output(runtime, run, "lesson_plan")
        assert run.status is WorkflowStatus.COMPLETED
        assert output["lesson_plan"]["topic"] == "linear equations"
        assert output["final_answer"]
        assert runtime.memory_store.get(f"memory:{run.run_id}:lesson_plan").memory_type is MemoryType.PROCEDURAL
    finally:
        close_runtime(runtime)


async def test_04_writer_pack_runs_declared_profile_memory_and_output_contract(tmp_path) -> None:
    runtime = build_default_runtime(environment=_environment(tmp_path, "writer"), tool_runtime=_PackToolRuntime())
    try:
        mission = runtime.create_mission(
            title="A detective discovers a city that forgets one day every year",
            domain="writer",
            intent="story_outline",
            workflow_id="writer_story_outline_v1",
            input={"premise": "A detective discovers a city that forgets one day every year", "genre": "mystery"},
        )
        run = await runtime.start(mission.mission_id, workflow_id="writer_story_outline_v1")

        output = _output(runtime, run, "outline_generate")
        assert run.status is WorkflowStatus.COMPLETED
        assert len(output["outline"]["chapters"]) == 3
        assert output["outline_markdown"] == output["final_answer"]
        assert runtime.memory_store.get(f"memory:{run.run_id}:outline_generate").memory_type is MemoryType.EPISODIC
    finally:
        close_runtime(runtime)
