"""Ordered integration coverage for the general native runtime pack."""

from __future__ import annotations

import json

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
