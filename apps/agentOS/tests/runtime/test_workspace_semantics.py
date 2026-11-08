"""Workspace read projections never become semantic writers or Run capture points."""
import pytest

from components.mission_manager.semantic_resolver import MissionSemanticResolver
from contracts.mission_semantic import MissionSemanticOperation
from contracts.workflow import RuntimeMissionRecord
from domain.models import Mission, RunStatus
from runtime.workspace import MissionWorkspaceProjection, WorkspaceRunSummary, with_mission_semantics
from support.stores.memory_workflow_store import MemoryWorkflowStore


def foundation():
    store = MemoryWorkflowStore()
    store.save_mission(RuntimeMissionRecord(missionId="mission_0123456789ab", title="legacy title", input={"objective": "legacy input"}))
    mission = Mission(missionId="mission_0123456789ab", userId="owner", goal="Identity old goal")
    return store, MissionWorkspaceProjection(mission=mission)


def commit(store, revision=0, op="one", objective="formal objective"):
    return store.commit_semantics(MissionSemanticOperation(missionId="mission_0123456789ab", operationId=op,
        expectedMissionRevision=revision, objective=objective, constraints=[], actorId="owner", tenantId="tenant"))


def compose(store, projection, basis=None, status="NO_RUN"):
    view = MissionSemanticResolver.resolve(store.get_semantic_snapshot("mission_0123456789ab"))
    return with_mission_semantics(projection, view, basis=basis, basis_status=status,
        legacy_input=store.get_mission("mission_0123456789ab").input, legacy_title="legacy title")


def test_current_semantics_and_historical_basis_remain_distinct_and_readonly():
    store, projection = foundation()
    commit(store)
    basis = MissionSemanticResolver.freeze(MissionSemanticResolver.resolve(store.get_semantic_snapshot("mission_0123456789ab")))
    projection.active_run = WorkspaceRunSummary(runId="run_0123456789ab", status=RunStatus.PENDING,
        createdAt=projection.mission.created_at, isActive=True)
    commit(store, 1, "two", "current objective")
    before = store.get_semantic_snapshot("mission_0123456789ab")
    result = compose(store, projection, basis, "BOUND")
    assert result.mission_display.objective == "current objective"
    assert result.mission_semantic_view.mission_revision == 2
    assert result.selected_run_basis == basis and basis.source_revision == 1
    assert result.mission.goal == projection.mission.goal == "Identity old goal"
    assert "Identity old goal" not in result.entries[0].content
    assert "formal objective" in result.entries[0].content
    assert result.diagnostics[-1].code == "MISSION_RUN_REVISION_DIFFERS"
    assert store.get_semantic_snapshot("mission_0123456789ab") == before
    assert len(store.list_semantic_commits("mission_0123456789ab")) == len(store.list_semantic_outbox("mission_0123456789ab")) == 2
    assert projection.entries == []


@pytest.mark.parametrize("identity,input_value,title,source,objective", [
    ("Identity old goal", "legacy input", "title", "IDENTITY_COMPATIBILITY", "Identity old goal"),
    (" ", "legacy input", "title", "LEGACY_INPUT", "legacy input"),
    (" ", "", "title", "LEGACY_TITLE", "title"),
    (" ", "", "", "NONE", None),
])
def test_uninitialized_display_priority_never_promotes_legacy(identity, input_value, title, source, objective):
    store, projection = foundation()
    projection.mission.goal = identity
    view = MissionSemanticResolver.resolve(store.get_semantic_snapshot("mission_0123456789ab"))
    result = with_mission_semantics(projection, view, basis=None, basis_status="NO_RUN",
        legacy_input={"objective": input_value}, legacy_title=title)
    assert result.mission_display.source_type == source and result.mission_display.objective == objective
    assert result.mission_semantic_view.mission_revision == 0
    assert store.get_semantic_snapshot("mission_0123456789ab").state is None
    assert store.list_semantic_commits("mission_0123456789ab") == []


@pytest.mark.parametrize("status", ["UNBOUND", "RUNTIME_UNAVAILABLE", "NO_RUN"])
def test_absent_basis_has_explicit_status_without_current_state_backfill(status):
    store, projection = foundation()
    commit(store)
    if status != "NO_RUN":
        projection.active_run = WorkspaceRunSummary(runId="run_0123456789ab", status=RunStatus.PENDING,
            createdAt=projection.mission.created_at, isActive=True)
    result = compose(store, projection, status=status)
    assert result.selected_run_basis is None and result.selected_run_basis_status == status


def test_cross_mission_projection_rejected():
    store, projection = foundation()
    projection.mission.mission_id = "mission_abcdef012345"
    with pytest.raises(ValueError, match="another Mission"):
        compose(store, projection)
