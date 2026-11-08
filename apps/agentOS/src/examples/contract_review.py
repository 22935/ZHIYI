"""Offline native v1 -> v2 vertical slice, using the existing authorities.

Run from apps/agentOS: python -m examples.contract_review NEW_DIRECTORY
Only a NEW directory may be initialized. Reopening never upgrades schemas.
v1 uses the existing bootstrap; initial-plan materialization is not implemented.
"""
from __future__ import annotations

import asyncio
from contextlib import closing
import json
from pathlib import Path
import re
import shutil
import sqlite3
from tempfile import TemporaryDirectory

from adapters.model.native import NativeGeneralAgent
from components.auditor import SQLiteDecisionStore
from components.communicator.provenance_store import SQLiteProvenanceStore
from components.content import SQLiteContentManifestStore
from components.executor.value_store import SQLiteExecutionValueStore
from components.memory.store import SQLiteMemoryStore
from components.mission_manager.semantic_service import MissionSemanticService
from components.mission_manager.store import WorkflowRegistry
from components.recovery.checkpoint import ACGCheckpointStore
from contracts.mission_semantic import MissionSemanticRequest, SemanticPrincipal
from contracts.planning import PlannedTask, TaskPlanPatch, TaskPlanRelation
from contracts.runtime_planning import RuntimePlanningDecision
from contracts.recovery import SemanticPatchRequest
from contracts.workflow import WorkflowDefinition, WorkflowStepDefinition, WorkflowStatus
from runtime import ExecutionRuntime
from runtime import AcgIdentityLifecycleService, IdentityProjectionBridge, IdentityQueryService
from service.agents import AgentRegistry
from service.agents.base import AgentOutput, AgentProfile, BaseAgent
from storage.v2 import SQLiteV2Repositories, SQLiteV2Storage
from storage.v2.schema import SCHEMA_SQL as IDENTITY_SCHEMA_SQL
from storage.v2.sqlite import CURRENT_SCHEMA_VERSION
from support.stores.sqlite_workflow_store import SQLiteWorkflowStore
from support.stores.planning_commit_store import SQLitePlanningCommitStore
from support.stores.graph_materialization_store import SQLiteGraphMaterializationStore
from support.stores.graph_activation_store import SQLiteGraphActivationStore
from support.stores.graph_handoff_store import (
    SQLiteGraphHandoffStore, SQLiteStagedGraphCheckpointStore, schema, HANDOFF_SQL, STAGE_SQL,
)
from support.stores.execution_permit_store import SQLiteExecutionPermitStore, _check_schema as check_permit_schema
from support.acg.native_capabilities import build_default_capability_catalog


CONTRACT = "CRM软件开发合同：金额80万元，付款30%/70%，60日交付。验收默认通过；知识产权共同所有。"
WORKFLOW_ID = "offline_contract_review"
OWNER = SemanticPrincipal(actorId="local-contract-owner", tenantId="local-example")


class ContractReviewAgent(BaseAgent):
    """Small rule-based business agent, not a mock model or a receipt writer.

    All findings are derived from actual input text. No legal completeness or
    business acceptance is claimed. Runtime alone creates execution evidence.
    """
    def __init__(self):
        super().__init__(AgentProfile(agentName="offline_contract_reviewer", domain="general",
            capabilities=["task_understanding", "artifact_generation"]))
        self.calls = []

    async def run(self, context):
        text = str(context.run.input.get("contractText") or "")
        amount = re.search(r"金额\s*(\d+)\s*万元", text)
        ratios = re.search(r"(\d+)%\s*/\s*(\d+)%", text)
        days = re.search(r"(\d+)\s*日交付", text)
        if not amount or not ratios or not days or sum(map(int, ratios.groups())) != 100:
            raise ValueError("contract requires amount, balanced payment percentages and delivery days")
        terms = {"amount": int(amount[1]) * 10000, "ratios": list(map(int, ratios.groups())), "days": int(days[1])}
        findings = []
        if "验收默认通过" in text:
            findings.append("删除验收默认通过，明确验收标准、异议期限与整改流程。")
        if "知识产权共同所有" in text:
            findings.append("明确既有知识产权、定制成果归属及双方使用授权。")
        if terms["ratios"][1] > 50:
            findings.append("尾款比例较高，约定验收及交付物与付款条件的对应关系。")
        self.calls.append(context.step.step_id)
        if context.step.capability == "task_understanding":
            upstream = context.context_pack.data if context.context_pack else {}
            summary = json.dumps({"stage": context.step.step_id, "terms": terms,
                "findings": findings, "upstream": upstream.get("task_summary")}, ensure_ascii=False)
            return AgentOutput(output={"task_summary": summary, "constraints": []}, summary=summary)
        data = context.context_pack.data if context.context_pack else {}
        if not data.get("task_summary"):
            raise ValueError("final synthesis requires a real upstream review")
        deliverable = {"title": "CRM软件开发合同审查", "executiveSummary": "确定性条款检查；签署前需专业复核。",
            "sections": [{"title": "事实与条款风险", "content": json.dumps(terms, ensure_ascii=False) + "\n" + "\n".join(findings),
                          "sourceFields": ["input:contractText", "task_summary"]}],
            "calculations": [{"name": f"第{i+1}期付款", "formula": f"{terms['amount']} * {ratio} / 100",
                "inputs": ["合同金额", "付款比例"], "result": str(terms["amount"] * ratio // 100), "assumptions": []}
                for i, ratio in enumerate(terms["ratios"])],
            "assumptions": [], "openQuestions": ["需人工确认验收标准与知识产权安排"], "sourceRefs": ["input:contractText"]}
        output = NativeGeneralAgent._normalize_artifact_output(context, {"deliverable": deliverable,
            "verification": {"status": "partial", "checks": [], "unresolvedGaps": ["未作法律完整性鉴定"]}})
        return AgentOutput(output=output, summary="规则审查完成；法律判断仍需复核")


def workflow():
    fields = ["task_summary", "constraints"]
    descriptor = build_default_capability_catalog().get("task_understanding")
    return WorkflowDefinition(workflowId=WORKFLOW_ID, name="离线合同审查", domain="general", runtimeEngine="acg",
        planningNodes=[PlannedTask(key=f"step:{k}", title=k, objective=goal,
            capabilityRequirements=("task_understanding",), sourceRefs=("input:contractText",))
            for k, goal in (("A", "提取合同事实"), ("B", "审查付款安排"), ("C", "审查验收与知识产权"))],
        planningRelations=[TaskPlanRelation(sourceKey=f"step:{a}", targetKey=f"step:{b}", relationType="depends_on")
                           for a,b in (("A","B"),("B","C"))],
        steps=[WorkflowStepDefinition(stepId=k, name=k, agentName="offline_contract_reviewer", capability="task_understanding",
            outputSpec=descriptor.output_contract,
            input={"from": {previous: fields}} if previous else {}) for k,previous in (("A",None),("B","A"),("C","B"))])


class BoundaryPlanner:
    def decide_runtime(self, *, observation, task_plan):
        # Host-owned deterministic policy, consuming the real observation.
        action = ("wait" if task_plan.plan_version == 1 and any(s.step_id == "A" and s.status == "completed" for s in observation.steps) and observation.remaining_step_ids
                  else "continue" if observation.remaining_step_ids else "complete")
        return RuntimePlanningDecision(observationId=observation.fingerprint(), action=action,
            reason="v1 inspection boundary" if action == "wait" else "native contract review")


# Required existing columns, including columns older constructors would migrate.
# This is a sample preflight, not a schema upgrader or execution authority.
RESUME_SCHEMA = {
    "workflow.sqlite3": {
        "tasks": "mission_id payload updated_at",
        "runs": "run_id mission_id payload updated_at status owner_user_id owner_tenant_id domain workflow_id lifecycle_phase lifecycle_message source current_step_id started_at created_at runtime_revision record_state",
        "task_copilot_permissions": "mission_id permission",
        "run_planning_inputs": "sequence run_id operation_id payload",
        "run_copilot_exchanges": "sequence run_id operation_id payload",
        "lifecycle_outbox": "event_id event_type aggregate_id payload status attempts last_error created_at",
        "mission_semantic_state": "mission_id revision payload",
        "mission_semantic_commits": "commit_id mission_id revision operation_id payload",
        "mission_semantic_receipts": "mission_id operation_id payload",
        "mission_semantic_outbox": "event_id mission_id revision payload status",
        "mission_revision_decisions": "mission_id run_id operation_id payload",
        "planning_commit_records": "commit_id mission_id revision idempotency_key payload",
        "planning_commit_outbox": "commit_id payload",
    },
    "checkpoint.sqlite3": {
        "acg_execution_checkpoints": "thread_id checkpoint_id state_json version created_at",
    },
    "identity.sqlite3": {},  # Derived below from the existing canonical schema.
    "content.sqlite3": {
        "content_manifests": "manifest_id kind owner_type owner_id media_type checksum byte_length fragment_count estimated_tokens chunking_version sealed created_at",
        "content_fragments": "manifest_id sequence fragment_id checksum byte_length estimated_tokens source_refs constraint_refs verification_status content",
    },
    "values.sqlite3": {
        "execution_values": "reference run_id step_id kind payload_json created_at operation_id",
        "acg_node_executions": "operation_id run_id payload_json phase",
        "acg_node_commits": "commit_id run_id payload_json stage",
    },
    "memory.sqlite3": {"execution_memory": "memory_id record_json"},
    "provenance.sqlite3": {"acg_provenance_events": "run_id event_id event_json"},
    "audit.sqlite3": {"acg_audit_decisions": "decision_id run_id step_id decision_json decision_hash created_at"},
}


def _preflight_resume(folder):
    paths = [folder / name for name in RESUME_SCHEMA]
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("sample recovery requires all existing database files")
    if any(p.with_name(p.name + "-journal").exists() for p in paths):
        raise ValueError("sample recovery cannot settle a rollback journal")
    try:
        # A mode=ro connection can still create WAL/SHM; immutable=1 ignores WAL.
        # Check read-only private copies INCLUDING committed WAL, never the source.
        with TemporaryDirectory(prefix="agentos-sample-preflight-") as staging:
            for path in paths:
                target = Path(staging) / path.name
                shutil.copyfile(path, target)
                wal = path.with_name(path.name + "-wal")
                if wal.exists():
                    if not wal.is_file() or wal.is_symlink():
                        raise ValueError("invalid sample WAL file")
                    shutil.copyfile(wal, target.with_name(target.name + "-wal"))
                with closing(sqlite3.connect(target.as_uri() + "?mode=ro", uri=True)) as conn:
                    conn.execute("PRAGMA query_only=ON")
                    tables = RESUME_SCHEMA[path.name]
                    if path.name == "identity.sqlite3":
                        if conn.execute("PRAGMA user_version").fetchone()[0] != CURRENT_SCHEMA_VERSION:
                            raise ValueError("sample Identity schema requires explicit preparation")
                        with closing(sqlite3.connect(":memory:")) as expected:
                            expected.executescript(IDENTITY_SCHEMA_SQL)
                            tables = {name: " ".join(r[1] for r in expected.execute(f'PRAGMA table_info("{name}")'))
                                      for (name,) in expected.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                            indexes = dict(expected.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"))
                            actual_indexes = dict(conn.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"))
                            if any(actual_indexes.get(name) != sql for name, sql in indexes.items()):
                                raise ValueError("sample Identity indexes require explicit preparation")
                    for table, columns in tables.items():
                        actual = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
                        if not actual or not set(columns.split()) <= actual:
                            raise ValueError(f"incomplete sample schema: {path.name}/{table}")
                    if path.name == "workflow.sqlite3":
                        for name in ("idx_runs_mission_updated_at", "idx_runs_owner_overview"):
                            if "record_state" not in {r[2] for r in conn.execute(f"PRAGMA index_info({name})")}:
                                raise ValueError("sample Workflow index requires explicit preparation: " + name)
                        for version_table in ("mission_semantic_schema", "planning_commit_schema"):
                            if list(conn.execute(f"SELECT version FROM {version_table}")) != [(1,)]:
                                raise ValueError("unsupported sample schema: " + version_table)
                        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='planning_graph_source_unique'").fetchone():
                            raise ValueError("missing graph revision source index")
                        SQLiteGraphMaterializationStore._check_schema(conn)
                        SQLiteGraphActivationStore._check_schema(conn)
                        schema(conn, "graph_handoffs", HANDOFF_SQL)
                        check_permit_schema(conn)
                    elif path.name == "checkpoint.sqlite3":
                        schema(conn, "staged_graph_checkpoints", STAGE_SQL)
                    elif path.name == "content.sqlite3":
                        if [r[2] for r in conn.execute("PRAGMA index_info(idx_content_manifest_owner)")] != ["owner_type", "owner_id", "kind"]:
                            raise ValueError("sample content index requires explicit preparation")
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        raise ValueError("sample recovery schema unavailable; no automatic upgrade") from exc


def open_runtime(folder: Path, *, initialize=False):
    folder = Path(folder).resolve()
    if initialize:
        folder.mkdir(parents=True, exist_ok=False)  # Never upgrade a business database.
        (folder / "example.json").write_text(json.dumps({"example": WORKFLOW_ID, "version": 1}), encoding="utf-8")
    if (not folder.is_dir() or not (folder / "example.json").is_file()
            or json.loads((folder / "example.json").read_text(encoding="utf-8")) != {"example": WORKFLOW_ID, "version": 1}):
        raise ValueError("not an initialized contract review sample directory")
    if not initialize:
        _preflight_resume(folder)
    agents, workflows = AgentRegistry(), WorkflowRegistry()
    agent = ContractReviewAgent()
    agents.register(agent)
    workflows.register(workflow())
    store = SQLiteWorkflowStore(folder / "workflow.sqlite3", enable_mission_semantics=initialize)
    if not initialize:
        store.enable_existing_mission_semantics()
    content = SQLiteContentManifestStore(folder / "content.sqlite3")
    lifecycle = AcgIdentityLifecycleService(SQLiteV2Repositories(SQLiteV2Storage(str(folder / "identity.sqlite3"))))
    rt = ExecutionRuntime(agent_registry=agents, workflow_registry=workflows, workflow_store=store,
        checkpoint_store=ACGCheckpointStore(db_path=folder / "checkpoint.sqlite3"),
        execution_value_store=SQLiteExecutionValueStore(db_path=folder / "values.sqlite3"),
        memory_store=SQLiteMemoryStore(db_path=folder / "memory.sqlite3"),
        provenance_store=SQLiteProvenanceStore(db_path=folder / "provenance.sqlite3"),
        decision_store=SQLiteDecisionStore(db_path=folder / "audit.sqlite3"), content_manifest_store=content,
        identity_lifecycle=IdentityProjectionBridge(lifecycle, lifecycle.repositories, content))
    rt.mission_semantic_service = MissionSemanticService(store=store, authorize=lambda p,m,a: p == OWNER)
    rt.semantic_principal_provider = lambda: OWNER
    rt.allow_legacy_mission_intent = False
    rt.runtime_planning_coordinator.planner_for_run = lambda _: BoundaryPlanner()
    rt.runtime_planning_coordinator.observe_progress = lambda run,state: state.graph_version == 1 and state.completed_step_ids == ["A"]
    if initialize:
        SQLitePlanningCommitStore.upgrade_schema(store.db_path)
        SQLiteGraphMaterializationStore.upgrade_schema(store.db_path)
        SQLiteGraphActivationStore.upgrade_schema(store.db_path)
        SQLiteGraphHandoffStore.upgrade_schema(store.db_path)
        SQLiteExecutionPermitStore.upgrade_schema(store.db_path)
        SQLiteStagedGraphCheckpointStore.upgrade_schema(rt.checkpoint_store.db_path)
    else:
        attach_authorities(rt)
    return rt, agent


def attach_authorities(rt):
    path = rt.workflow_store.db_path
    rt.enable_planning_commit(SQLitePlanningCommitStore(path))
    rt.enable_graph_materialization(SQLiteGraphMaterializationStore(path))
    rt.enable_graph_activation(SQLiteGraphActivationStore(path))
    rt.enable_graph_handoff(SQLiteGraphHandoffStore(path), SQLiteStagedGraphCheckpointStore(rt.checkpoint_store.db_path))
    rt.enable_execution_permit(SQLiteExecutionPermitStore(path))


async def prepare_revision(folder, contract=CONTRACT):
    rt, agent = open_runtime(folder, initialize=True)
    mission = rt.create_mission("CRM软件开发合同审查", workflow_id=WORKFLOW_ID, input={"contractText": contract,
        "authenticatedUserId": OWNER.actor_id, "authenticatedTenantId": OWNER.tenant_id, "deterministicIntent": True})
    rt.mission_semantic_service.commit(OWNER, MissionSemanticRequest(missionId=mission.mission_id,
        operationId="contract-basis", expectedMissionRevision=0, objective="审查CRM开发合同并交付可追溯报告",
        constraints=[], sourceRefs=["input:contractText"]))
    _, run = rt.prepare_run(mission.mission_id)
    paused = await rt.execute_prepared_run(run.run_id)
    if paused.status != WorkflowStatus.WAITING_REVIEW or paused.completed_step_ids != ["A"]:
        raise ValueError(f"no legal A boundary: {paused.status}: {paused.error}")
    attach_authorities(rt)
    rt.require_planning_commit(run.run_id)
    paused = rt.workflow_store.get_run(run.run_id)
    patch = TaskPlanPatch(missionId=mission.mission_id, basePlanVersion=1, planVersion=2,
        addNodes=(PlannedTask(key="step:D", title="合同审查报告", objective="综合审查结果并交付报告",
            capabilityRequirements=("artifact_generation",), logicalRole="final_synthesis", sourceRefs=("input:contractText",)),),
        relations=(*[TaskPlanRelation.model_validate(r) for r in paused.execution_state["taskPlan"]["relations"]],
                   TaskPlanRelation(sourceKey="step:C", targetKey="step:D", relationType="depends_on")))
    receipt = await rt.apply_semantic_patch(SemanticPatchRequest(runId=run.run_id,
        graphId=paused.acg_blueprint["graphId"], baseGraphVersion=1,
        taskPlanPatch=patch, patchId="contract-report", idempotencyKey="contract-report"))
    if receipt.status != "ACCEPTED":
        raise ValueError(f"plan acceptance failed: {receipt}")
    graph = rt.accept_graph_revision(run.run_id, receipt.commit_id, idempotency_key="contract-graph")
    if graph.status != "ACCEPTED":
        raise ValueError(f"graph acceptance failed: {graph}")
    mat = rt.materialize_graph_revision(graph.commit_id, idempotency_key="contract-materialize")
    if mat.status != "MATERIALIZED_INACTIVE":
        raise ValueError(f"materialization failed: {mat}")
    prepared = rt.prepare_graph_activation(mat.materialization_id, idempotency_key="contract-activate")
    if prepared.status != "ACTIVATION_PREPARED":
        raise ValueError(f"activation preparation failed: {prepared}")
    activation = rt.commit_graph_activation(mat.materialization_id, idempotency_key="contract-activate")
    if activation.status != "ACTIVATED_PAUSED":
        raise ValueError(f"activation failed: {activation}")
    handoff = rt.prepare_graph_handoff(activation.activation_id, idempotency_key="contract-handoff")
    if handoff.status != "STATE_PREPARED":
        raise ValueError(f"handoff failed: {handoff}")
    permit = rt.issue_execution_permit(handoff.handoff_id, idempotency_key="contract-permit")
    if permit.status != "ISSUED":
        raise ValueError(f"permit failed: {permit}")
    return rt, agent, run.run_id


def result_projection(rt, run_id):
    run = rt.workflow_store.get_run(run_id)
    query = IdentityQueryService(rt.identity_lifecycle.repositories, rt.content_manifest_store)
    return {"run": run.model_dump(mode="json", by_alias=True),
        "workspace": query.mission_workspace(run.mission_id, run_id=run_id).model_dump(mode="json", by_alias=True),
        "artifacts": [item.model_dump(mode="json", by_alias=True) for item in query.artifacts_for_run(run_id)]}


async def main(folder, run_id=None):
    if run_id is None:
        rt, _, run_id = await prepare_revision(folder)
    else:
        rt, _ = open_runtime(folder)
    result = await rt.execute_prepared_run(run_id)
    if result.status != WorkflowStatus.COMPLETED:
        raise ValueError(f"sample did not complete: {result.status}")
    return result_projection(rt, run_id)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--resume-run", help="Resume an existing Run through current Permit and recovery gates")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(main(args.directory, args.resume_run)), ensure_ascii=False, indent=2))
