"""HTTP adapters for the existing Initial C2 authorities; no execution dispatch."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.security.internal_auth import current_semantic_principal
from contracts.workflow import MissionRecordState, RunRecordState, RuntimeRunRecord
from contracts.planning_commit import PlanningCommitRecord
from contracts.graph_materialization import GraphMaterializationRecord
from contracts.graph_handoff import GraphHandoffRecord, GraphHandoffReceipt
from contracts.initial_planning import InitialPlanningSourceProvenance
from contracts import stable_checksum
from runtime.execution_permit import ExecutionPermitError
from support.stores.execution_permit_store import SQLiteExecutionPermitStore
from support.stores.graph_activation_store import SQLiteGraphActivationStore, validate_activation_run
from app.execution.run_capabilities import assert_mutable_run


class MaterializeInitialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    operation_id: str = Field(alias="operationId", min_length=1, max_length=200)
    commit_id: str = Field(alias="commitId", min_length=1, max_length=300)
    expected_commitment_revision: int = Field(alias="expectedCommitmentRevision", strict=True, ge=1)


class ActivateInitialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    operation_id: str = Field(alias="operationId", min_length=1, max_length=200)
    materialization_id: str = Field(alias="materializationId", min_length=1, max_length=300)
    expected_graph_id: str = Field(alias="expectedGraphId", min_length=1, max_length=300)
    expected_graph_version: int = Field(alias="expectedGraphVersion", strict=True, ge=1)


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    operation_id: str = Field(alias="operationId", min_length=1, max_length=200)
    activation_id: str = Field(alias="activationId", min_length=1, max_length=300)
    expected_graph_id: str = Field(alias="expectedGraphId", min_length=1, max_length=300)
    expected_graph_version: int = Field(alias="expectedGraphVersion", strict=True, ge=1)


class PermitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    operation_id: str = Field(alias="operationId", min_length=1, max_length=200)
    handoff_id: str = Field(alias="handoffId", min_length=1, max_length=300)
    expected_graph_id: str = Field(alias="expectedGraphId", min_length=1, max_length=300)
    expected_graph_version: int = Field(alias="expectedGraphVersion", strict=True, ge=1)


class DispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    operation_id: str = Field(alias="operationId", min_length=1, max_length=200)
    expected_permit_id: str = Field(alias="expectedPermitId", min_length=1, max_length=300)
    expected_graph_id: str = Field(alias="expectedGraphId", min_length=1, max_length=300)
    expected_graph_version: int = Field(alias="expectedGraphVersion", strict=True, ge=1)
    expected_runtime_revision: int = Field(alias="expectedRuntimeRevision", strict=True, ge=0)


@contextmanager
def control_errors():
    try:
        yield
    except PermissionError as exc:
        raise HTTPException(403, "semantic access denied") from exc
    except ExecutionPermitError as exc:
        code = str(getattr(exc.code, "value", exc.code))
        raise HTTPException(403 if code == "AUTHORITY_DENIED" else 409, {"code": code}) from exc
    except KeyError as exc:
        raise HTTPException(404, "C2 source not found") from exc
    except (RuntimeError, sqlite3.Error, ValueError, TypeError) as exc:
        # Never return compiler sources, signatures, storage paths or audit bodies.
        raise HTTPException(503, "C2 evidence unavailable; retry the same operation") from exc


def require_c2(runtime, mission_id, run_id, *, write):
    if any(getattr(runtime, name, None) is None for name in (
        "planning_commit_authority", "graph_materialization_authority", "graph_activation_authority",
    )):
        raise HTTPException(409, "C2 control is not enabled")
    principal = current_semantic_principal()
    if principal is None or runtime.semantic_principal_provider() != principal:
        raise HTTPException(403, "trusted semantic principal is required")
    service = runtime.mission_semantic_service
    service.require_write_access(principal, mission_id) if write else service.require_read_access(principal, mission_id)
    mission = runtime.workflow_store.get_mission(mission_id)
    run = runtime.workflow_store.get_run(run_id)
    if mission.record_state != MissionRecordState.ACTIVE or run.record_state != RunRecordState.ACTIVE:
        raise HTTPException(404, "C2 source not found")
    if run.mission_id != mission_id or not run.execution_state.get("planningCommitRequired"):
        raise HTTPException(409, "Run is not a C2 source of this Mission")
    if write:
        try:
            assert_mutable_run(run)
        except ValueError as exc:
            raise HTTPException(409, 'superseded Run is immutable') from exc
    return run


def initial_commit(runtime, run, commit_id):
    record = runtime.planning_commit_authority.get_commit(commit_id)
    origin = getattr(record, "source_provenance", None)
    if (record is None or record.proposal_type != "initial_plan" or origin is None
            or record.mission_id != run.mission_id or origin.source_run_id != run.run_id):
        raise HTTPException(409, "initial Commit does not belong to this Mission/Run")
    return record


def operation_key(action, run, operation_id):
    principal = current_semantic_principal()
    return "http-c2:" + hashlib.sha256(json.dumps([
        principal.tenant_id, principal.actor_id, action, run.mission_id, run.run_id, operation_id,
    ], separators=(",", ":")).encode()).hexdigest()


def receipt_response(receipt, operation_id):
    if receipt.status == "REJECTED":
        code = str(getattr(receipt.code, "value", receipt.code))
        status = 403 if code == "AUTHORITY_DENIED" else 503 if code == "STORAGE_UNAVAILABLE" else 409
        raise HTTPException(status, {"status": "REJECTED", "code": code, "operationId": operation_id})
    # Explicit public allowlist; the durable record is never serialized here.
    body = receipt.model_dump(by_alias=True, mode="json", exclude_none=True)
    return {"operationId": operation_id, **{k: v for k, v in body.items() if k in {
        "status", "materializationId", "activationId", "activeGraphVersion", "handoffId", "permitId", "runId", "graphVersion",
    }}}


def project_initial_control(runtime, run):
    """Read existing facts in one snapshot; preserve the legacy lifecycle status."""
    with control_errors():
        # load_run already checks owner/deletion. A switch disabling future C2
        # commands must not hide a previously persisted pause or grant execution.
        principal = current_semantic_principal()
        if principal is None:
            raise HTTPException(403, "trusted semantic principal is required")
        if runtime.mission_semantic_service is not None:
            runtime.mission_semantic_service.require_read_access(principal, run.mission_id)
        with runtime.workflow_store._connect() as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            try:
                row = conn.execute("SELECT payload FROM runs WHERE run_id=?", (run.run_id,)).fetchone()
                current = RuntimeRunRecord.model_validate_json(row[0])
                head = validate_activation_run(conn, current)
                row = conn.execute("SELECT payload FROM planning_commit_records WHERE idempotency_key=?",
                                   ("initial-planning:" + run.run_id,)).fetchone()
                commit = PlanningCommitRecord.model_validate_json(row[0]) if row else None
                if commit and (commit.mission_id != current.mission_id
                        or not isinstance(commit.source_provenance, InitialPlanningSourceProvenance)
                        or commit.source_provenance.source_run_id != current.run_id):
                    raise ValueError("initial Commit source mismatch")
                row = conn.execute("SELECT * FROM graph_materializations WHERE source_commit_id=?",
                                   (commit.commit_id,)).fetchone() if commit else None
                mat = GraphMaterializationRecord.model_validate_json(row["payload"]) if row else None
                if mat and (stable_checksum(mat) != row["checksum"] or mat.source_commit_id != commit.commit_id
                            or mat.source_run_id != run.run_id or mat.mission_id != run.mission_id):
                    raise ValueError("materialization evidence mismatch")
                row = conn.execute("SELECT * FROM graph_activations WHERE materialization_id=?",
                                   (mat.materialization_id,)).fetchone() if mat else None
                prepared = SQLiteGraphActivationStore._decode_activation(row) if row else None
                handoff_row = conn.execute("SELECT * FROM graph_handoffs WHERE activation_id=?",
                                          (head.activation_id,)).fetchone() if head else None
                handoff = GraphHandoffRecord.model_validate_json(handoff_row["payload"]) if handoff_row else None
                if handoff and (stable_checksum(handoff) != handoff_row["checksum"]
                        or handoff.activation_id != head.activation_id or handoff.run_id != current.run_id):
                    raise ValueError("handoff evidence mismatch")
                permit_row = conn.execute("SELECT * FROM graph_execution_permits WHERE activation_id=?",
                                         (head.activation_id,)).fetchone() if head else None
                permit = SQLiteExecutionPermitStore._decode(permit_row) if permit_row else None
                issued = permit is not None and permit.status in {"ISSUED", "REVOKED"}
                result = {
                    "status": "ACTIVATED_PAUSED" if head else "ACTIVATION_PREPARED" if prepared else
                              "MATERIALIZED_INACTIVE" if mat else "PLANNING_ACCEPTED" if commit else "AWAITING_PLANNING",
                    "executionAuthorized": False,
                    "permitIssued": issued,
                    "dispatchEligible": False,
                    "handoffId": handoff.handoff_id if handoff else None,
                    "handoffStatus": handoff.status if handoff else None,
                    "permitId": permit.permit_id if permit else None,
                    "permitStatus": permit.status if permit else None,
                    "commitId": commit.commit_id if commit else None,
                    "commitmentRevision": commit.commitment_revision if commit else None,
                    "materializationId": mat.materialization_id if mat else None,
                    "activationId": head.activation_id if head else prepared.activation_id if prepared else None,
                    "graphId": head.graph_id if head else mat.graph_id if mat else None,
                    "graphVersion": head.active_graph_version if head else mat.candidate_graph_version if mat else None,
                }
                # Discover an immutable public receipt; never reconcile/start work in GET.
                from support.stores.execution_dispatch_store import SQLiteExecutionDispatchStore
                enabled = bool(getattr(runtime, "execution_dispatch_enabled", False))
                command = None
                if enabled or conn.execute("SELECT 1 FROM sqlite_master WHERE name='execution_dispatch_commands'").fetchone():
                    SQLiteExecutionDispatchStore.check_schema(conn)
                    command = SQLiteExecutionDispatchStore.decode(conn.execute(
                        "SELECT * FROM execution_dispatch_commands WHERE run_id=?", (current.run_id,)).fetchone())
                    if command and (command.mission_id != current.mission_id
                            or command.permit_id != current.execution_state.get("executionPermitId")
                            or command.graph_id != current.execution_state.get("graphId")
                            or command.graph_version != current.execution_state.get("graphVersion")
                            or command.runtime_revision > current.runtime_revision):
                        raise ValueError("Dispatch source mismatch")
                result["dispatchEnabled"] = enabled
                result["dispatch"] = command.public() if command else None
                # A separately issued durable Permit must not be shown as paused.
                if issued:
                    result["status"] = "ACTIVATED"
            finally:
                conn.rollback()
        # No mutation or reconciliation in a query. Reuse the live authority's
        # complete dispatch gate (Mission, principal, Identity and checkpoint).
        authority = runtime.execution_permit_authority
        if issued and authority is not None:
            try:
                with runtime.run_lock_manager.lock_for(current.run_id):
                    authority.assert_dispatchable(current)
                    from runtime.permit_recovery import assert_settled_operations
                    assert_settled_operations(runtime, current)
                    if runtime.workflow_store.get_run(current.run_id) == current:
                        with runtime._execution_slot_guard:
                            result["dispatchEligible"] = (current.run_id not in runtime._active_execution_slots
                                                          and current.status.value != "waiting_review")
            except (ValueError, KeyError, RuntimeError, sqlite3.Error, TypeError, PermissionError):
                pass  # Unproven eligibility remains false; historical issuance survives.
        result["executionAuthorized"] = result["dispatchEligible"] and (not enabled or command is not None)
        return result


def require_execution_sources(runtime, mission_id, run_id, request, activation_id):
    run = require_c2(runtime, mission_id, run_id, write=True)
    if runtime.graph_handoff_authority is None or runtime.execution_permit_authority is None:
        raise HTTPException(409, "C2 execution control is not enabled")
    store = runtime.graph_activation_authority.store
    activation = store.get_activation(activation_id)
    head = store.head(run_id)
    if (activation is None or activation.run_id != run_id or activation.mission_id != mission_id
            or activation.status != "ACTIVATED_PAUSED" or head is None or head.activation_id != activation_id
            or head.graph_id != request.expected_graph_id or head.active_graph_version != request.expected_graph_version):
        raise HTTPException(409, "Activation Head does not match this Mission/Run/Graph")
    return run


def create_c2_router(runtime, coordinator=None):
    router = APIRouter()

    @router.post("/missions/{mission_id}/runs/{run_id}/execution/dispatches", status_code=202)
    async def dispatch(mission_id: str, run_id: str, request: DispatchRequest):
        from support.stores.execution_dispatch_store import DispatchCommand, DispatchConflict
        with control_errors():
            run = require_c2(runtime, mission_id, run_id, write=True)
            if coordinator is None or getattr(runtime, "execution_dispatch_store", None) is None:
                raise HTTPException(409, "Dispatch control is not enabled")
            principal = current_semantic_principal()
            key = operation_key("dispatch", run, request.operation_id)
            command = DispatchCommand(dispatch_id="dispatch_" + stable_checksum(key)[:40], operation_key=key,
                request_fingerprint=stable_checksum(request.model_dump(by_alias=True)),
                mission_id=mission_id, run_id=run_id, permit_id=request.expected_permit_id,
                graph_id=request.expected_graph_id, graph_version=request.expected_graph_version,
                runtime_revision=request.expected_runtime_revision, actor_id=principal.actor_id, tenant_id=principal.tenant_id)
            try:
                accepted, replay = await coordinator.submit_permitted(command)
            except (DispatchConflict, ValueError) as exc:
                raise HTTPException(409, "Dispatch is not eligible or operation conflicts") from exc
            current = runtime.get_status(run_id)
            return {"operationId": request.operation_id, **accepted.public(replay), "runStatus": current.status.value,
                    "errorCode": current.error.get("code") if isinstance(current.error, dict) else None}

    @router.post("/missions/{mission_id}/runs/{run_id}/graph/materializations")
    def materialize(mission_id: str, run_id: str, request: MaterializeInitialRequest):
        with control_errors():
            run = require_c2(runtime, mission_id, run_id, write=True)
            commit = initial_commit(runtime, run, request.commit_id)
            if commit.commitment_revision != request.expected_commitment_revision:
                raise HTTPException(409, "Commitment revision changed")
            receipt = runtime.materialize_initial_commit(commit.commit_id,
                idempotency_key=operation_key("materialize", run, request.operation_id))
            result = receipt_response(receipt, request.operation_id)
            mat = runtime.graph_materialization_authority.store.get_materialization(receipt.materialization_id)
            return {**result, "graphId": mat.graph_id, "graphVersion": mat.candidate_graph_version}

    @router.post("/missions/{mission_id}/runs/{run_id}/graph/activation")
    def activate(mission_id: str, run_id: str, request: ActivateInitialRequest):
        with control_errors():
            run = require_c2(runtime, mission_id, run_id, write=True)
            mat = runtime.graph_materialization_authority.store.get_materialization(request.materialization_id)
            if (mat is None or mat.source_kind != "initial_plan" or mat.mission_id != mission_id
                    or mat.source_run_id != run_id):
                raise HTTPException(409, "Materialization does not belong to this Mission/Run")
            initial_commit(runtime, run, mat.source_commit_id)
            if (mat.graph_id != request.expected_graph_id
                    or mat.candidate_graph_version != request.expected_graph_version):
                raise HTTPException(409, "Graph identity or version changed")
            key = operation_key("activate", run, request.operation_id)
            receipt_response(runtime.prepare_graph_activation(mat.materialization_id, idempotency_key=key), request.operation_id)
            return receipt_response(runtime.commit_graph_activation(mat.materialization_id, idempotency_key=key), request.operation_id)

    @router.post("/missions/{mission_id}/runs/{run_id}/graph/handoffs")
    async def handoff(mission_id: str, run_id: str, request: HandoffRequest):
        with control_errors():
            run = require_execution_sources(runtime, mission_id, run_id, request, request.activation_id)
            key = operation_key("handoff", run, request.operation_id)
            issued = runtime.execution_permit_authority.store.permit_for_activation(request.activation_id)
            if issued is not None and issued.status == "ISSUED":
                # The Handoff builder requires a pristine pre-Permit Run. Once
                # the saga legitimately advances it, replay only the immutable
                # confirmed receipt, under the complete current Permit gate.
                runtime.execution_permit_authority.assert_dispatchable(run)
                old = runtime.graph_handoff_authority.store.handoff_by_key(key)
                if old is None or old.handoff_id != issued.handoff_id or old.activation_id != request.activation_id:
                    raise HTTPException(409, {"code": "DUPLICATE_CONFLICT"})
                return {**receipt_response(GraphHandoffReceipt(status="IDEMPOTENT_REPLAY", handoffId=old.handoff_id),
                                          request.operation_id), "graphVersion": old.graph_version}
            return {**receipt_response(runtime.prepare_graph_handoff(request.activation_id,
                idempotency_key=key), request.operation_id), "graphVersion": request.expected_graph_version}

    @router.post("/missions/{mission_id}/runs/{run_id}/graph/permits")
    async def permit(mission_id: str, run_id: str, request: PermitRequest):
        with control_errors():
            # Authorization precedes reading a caller-selected durable reference.
            run = require_c2(runtime, mission_id, run_id, write=True)
            if runtime.graph_handoff_authority is None or runtime.execution_permit_authority is None:
                raise HTTPException(409, "C2 execution control is not enabled")
            source = runtime.graph_handoff_authority.store.get_handoff(request.handoff_id)
            if source is None or source.run_id != run_id or source.status != "STATE_PREPARED":
                raise HTTPException(409, "STATE_PREPARED Handoff of this Run is required")
            require_execution_sources(runtime, mission_id, run_id, request, source.activation_id)
            # Historical ISSUED replay does not itself revalidate dispatch in the
            # core saga. At HTTP, reject a stale grant before exposing a replay.
            existing = runtime.execution_permit_authority.store.permit_for_handoff(source.handoff_id)
            if existing is not None and existing.status == "ISSUED":
                runtime.execution_permit_authority.assert_dispatchable(run)
            return receipt_response(runtime.issue_execution_permit(source.handoff_id,
                idempotency_key=operation_key("permit", run, request.operation_id)), request.operation_id)

    return router
