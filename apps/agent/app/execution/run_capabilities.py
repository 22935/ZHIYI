"""Read-only UI offers from WorkflowStore facts, never command authorization.

Commands must still enter their existing Review/C2/Revision/Runtime authorities.
No capability is persisted, accepted from a client, or used as a branch pointer.
"""
import sqlite3
from fastapi import HTTPException

from app.security.internal_auth import current_trusted_user, current_semantic_principal
from contracts.workflow import MissionRecordState, RunRecordState, WorkflowStatus


ACTIVE = {'pending', 'planning', 'running', 'retrying', 'waiting_review'}
TERMINAL = {'completed', 'failed', 'cancelled', 'superseded'}
ACTIONS = ('canInspect', 'canDiscuss', 'canCancel', 'canReview', 'canExecuteFormalAction',
    'canResolveToolApproval', 'canAnswerPlanner', 'canCollaborate', 'canRetrySuccessor',
    'canRerunSuccessor', 'canDecideRevision', 'canApplyRevision', 'canDelete')
EVIDENCE_ERRORS = (KeyError, ValueError, TypeError, AttributeError, RuntimeError, sqlite3.Error, PermissionError, HTTPException)


def is_superseded(run):
    return run.status == WorkflowStatus.SUPERSEDED or bool(run.execution_state.get('supersededByRunId'))


def assert_mutable_run(run):
    """A source edge is not supersession. This guard grants no permission."""
    if run.record_state != RunRecordState.ACTIVE or is_superseded(run):
        raise ValueError('superseded or deleted Run is immutable')


def _formal_actions(control):
    if not control or control.get('dispatch'):
        return []
    status = control.get('status')
    if status == 'PLANNING_ACCEPTED' and control.get('commitId') and control.get('commitmentRevision'):
        return ['materialize']
    if not control.get('graphId') or not control.get('graphVersion'):
        return []
    if status in {'MATERIALIZED_INACTIVE', 'ACTIVATION_PREPARED'} and control.get('materializationId'):
        return ['activate']
    if status == 'ACTIVATED_PAUSED':
        if not control.get('handoffId') and control.get('activationId'):
            return ['handoff']
        if control.get('handoffStatus') == 'STATE_PREPARED' and not control.get('permitIssued'):
            return ['permit']
    if (status == 'ACTIVATED' and control.get('permitStatus') == 'ISSUED'
            and control.get('dispatchEnabled') is True and control.get('dispatchEligible') is True
            and control.get('permitId')):
        return ['dispatch']
    return []


def project_run_capabilities(runtime, run, *, formal_control=None):
    """Compute one Run, using its persisted owner, tenant, revision and authorities.

    Identity may lag Runtime. It can explain lineage, never overwrite execution
    status. Scope conflicts close all offers; ordinary projection lag does not
    prevent stopping a genuinely active Run owned by the requesting principal.
    """
    status = run.status.value
    lineage = {key: run.execution_state.get(key) for key in
        ('parentRunId', 'sourceRunId', 'supersedesRunId', 'supersededByRunId')}
    result = {**dict.fromkeys(ACTIONS, False), 'schemaVersion': 1,
        'missionId': run.mission_id, 'runId': run.run_id, 'runtimeRevision': run.runtime_revision,
        'status': status, 'isExecutionActive': status in ACTIVE, 'isSuperseded': is_superseded(run),
        'lineage': lineage, 'formalActions': [], 'retryStepId': None}
    reasons = dict.fromkeys(ACTIONS, 'EVIDENCE_UNAVAILABLE')
    reasons.update(canCancel='RUN_NOT_ACTIVE', canCollaborate='RUN_NOT_ACTIVE',
        canReview='REVIEW_EVIDENCE_UNAVAILABLE' if status == 'waiting_review' else 'RUN_NOT_WAITING_REVIEW',
        canAnswerPlanner='NO_VERIFIED_PLANNER_QUESTION', canExecuteFormalAction='FORMAL_AUTHORITY_UNAVAILABLE',
        canResolveToolApproval='NO_VERIFIED_TOOL_APPROVAL', canRetrySuccessor='RECOVERY_EVIDENCE_UNAVAILABLE',
        canRerunSuccessor='RUN_NOT_TERMINAL', canDelete='RUN_NOT_TERMINAL',
        canDecideRevision='NO_APPLICABLE_REVISION_CHANGE', canApplyRevision='NO_APPLICABLE_REVISION_DECISION')

    def allow(action):
        result[action] = True
        reasons.pop(action, None)

    def finish(reason=None):
        if reason:
            for action in ACTIONS:
                if action not in {'canInspect', 'canDiscuss'}:
                    result[action] = False
                if not result[action]:
                    reasons[action] = reason
            result['formalActions'] = []
        result['unavailableReasons'] = [{'action': action, 'code': code} for action, code in reasons.items()]
        return result

    try:
        actor = current_trusted_user()
        principal = current_semantic_principal()
        mission = runtime.workflow_store.get_mission(run.mission_id)
        owner = run.input.get('authenticatedUserId')
        tenant = run.input.get('authenticatedTenantId')
        semantic = getattr(runtime, 'mission_semantic_service', None)
        mission_tenant = mission.input.get('authenticatedTenantId')
        # The established semantic authority names tenant-less trusted requests
        # __unscoped__. It must prove that scope; absence alone grants nothing.
        tenant_matches = actor is not None and ((bool(tenant) and actor.tenant_id == tenant and mission_tenant == tenant)
            or (not tenant and not mission_tenant and not actor.tenant_id and semantic is not None))
        if (actor is None or not owner or actor.user_id != owner or not tenant_matches
                or mission.input.get('authenticatedUserId') != owner
                or run.record_state != RunRecordState.ACTIVE or mission.record_state == MissionRecordState.DELETED):
            return finish('TRUSTED_SCOPE_UNAVAILABLE')
        identity = getattr(runtime, 'identity_lifecycle', None)
        repositories = getattr(identity, 'repositories', None)
        if repositories:
            projected = repositories.runs.get(run.run_id)
            if projected and (projected.mission_id != run.mission_id
                    or (projected.metadata or {}).get('recordState') == 'deleted'):
                return finish('IDENTITY_SCOPE_CONFLICT')
        if semantic:
            semantic.require_read_access(principal, run.mission_id)
        allow('canInspect')
        allow('canDiscuss')
        if status not in ACTIVE | TERMINAL:
            return finish('UNKNOWN_STATUS')
        if is_superseded(run):
            return finish('RUN_SUPERSEDED')
        if mission.record_state != MissionRecordState.ACTIVE:
            return finish('MISSION_NOT_ACTIVE')
        if semantic:
            semantic.require_write_access(principal, run.mission_id)
        formal_write_proven = not run.execution_state.get('planningCommitRequired') or semantic is not None
        if status in ACTIVE:
            allow('canCancel')
            if formal_write_proven:
                allow('canCollaborate')
        if status in TERMINAL:
            allow('canDelete')
            # This is an offer to submit a new snapshot, not partial replay.
            # prepare_run rechecks the effective Mission semantic basis.
            if run.workflow_id and isinstance(run.input, dict):
                allow('canRerunSuccessor')
        if status == 'failed' and not run.execution_state.get('executionPermitId'):
            for step in run.steps:
                if step.status.value != 'failed':
                    continue
                try:
                    # validate_only returns before any writes; the final
                    # revision/scope comparison closes a changing snapshot.
                    # A GET must not block an event-loop on a mutation lock.
                    runtime.runtime_recovery_coordinator.prepare_single_step_retry(
                        run.run_id, step.step_id, expected_runtime_revision=run.runtime_revision,
                        validate_only=True)
                    allow('canRetrySuccessor')
                    result['retryStepId'] = step.step_id
                    break
                except EVIDENCE_ERRORS:
                    pass
        elif status == 'failed':
            reasons['canRetrySuccessor'] = 'PERMIT_RETRY_REQUIRES_INTERNAL_AUTHORITY'
        if status == 'waiting_review' and formal_write_proven:
            try:
                from components.executor import ACGExecutionState
                from support.stores._policy import acg_review_subject
                checkpoint = runtime.checkpoint_store.load(run_id=run.run_id,
                    checkpoint_id=str(run.execution_state.get('checkpointId') or ''))
                state = ACGExecutionState.model_validate(checkpoint)
                if state.run_id != run.run_id or state.review_payload != run.execution_state.get('reviewPayload'):
                    raise ValueError('Review source mismatch')
                runtime.review_service._validate_state_references(run=run, state=state)
                subject_type, subject_id = acg_review_subject(state.review_payload)
                if subject_type == 'planner' and state.review_payload.get('question'):
                    allow('canAnswerPlanner')
                elif subject_type == 'step' and run.get_step(subject_id).status.value == 'waiting_review':
                    allow('canReview')
                elif subject_type in {'control', 'planner'}:
                    allow('canReview')
            except EVIDENCE_ERRORS:
                pass
        if (status == 'running' and run.execution_state.get('executionPermitId') and semantic is not None
                and getattr(runtime, 'execution_permit_authority', None) is not None):
            try:
                from app.tools.permissions import get_chat_permission_service
                pending = getattr(runtime, 'formal_tool_pending', {})
                if any(item.get('sessionId') == run.run_id and get_chat_permission_service().pending(key) is not None
                        for key, item in pending.items()):
                    allow('canResolveToolApproval')
            except EVIDENCE_ERRORS:
                pass
        if status in {'pending', 'planning'} and run.execution_state.get('planningCommitRequired'):
            try:
                from app.api.agentos_c2 import project_initial_control, require_c2
                from contracts.mission_semantic import run_intent_basis
                require_c2(runtime, run.mission_id, run.run_id, write=True)
                basis = run_intent_basis(run)
                snapshot = semantic.get_effective_snapshot(principal, run.mission_id)
                if basis is None or basis.source_type != 'SEMANTIC' or basis.source_revision != snapshot.mission_revision:
                    reasons['canExecuteFormalAction'] = 'FORMAL_SOURCE_CHANGED'
                    raise ValueError('Formal semantic source changed')
                control = formal_control if formal_control is not None else project_initial_control(runtime, run)
                actions = _formal_actions(control)
                # Reuse read-only authority validators, never prepare/commit
                # operations or a synthetic authorization record in a GET.
                if actions == ['materialize']:
                    commit = runtime.planning_commit_authority.get_commit(control['commitId'])
                    runtime.graph_materialization_authority._validate_initial(commit, principal=principal)
                if actions == ['activate']:
                    materialization = runtime.graph_activation_authority.store.get_materialization(control['materializationId'])
                    runtime.graph_activation_authority._verify(materialization, principal=principal)
                if actions == ['handoff']:
                    authority = runtime.graph_handoff_authority
                    activation = authority.store.get_activation(control['activationId'])
                    # The durable activation key is only a read-validation input;
                    # no new command identity or receipt is generated/persisted.
                    authority._validated_candidate(activation.activation_id, activation.idempotency_key)
                if actions == ['permit']:
                    authority = runtime.graph_handoff_authority
                    handoff = authority.store.get_handoff(control['handoffId'])
                    candidate = authority._validated_candidate(handoff.activation_id, handoff.idempotency_key)
                    if candidate != handoff.model_copy(update={'status': 'STAGING'}) or runtime.execution_permit_authority is None:
                        raise ValueError('Permit source changed')
                result['formalActions'] = actions
                if result['formalActions']:
                    allow('canExecuteFormalAction')
            except EVIDENCE_ERRORS:
                pass
        if semantic:
            try:
                from contracts.mission_revision import revision_observation
                snapshot = semantic.get_effective_snapshot(principal, run.mission_id)
                choices = semantic.list_run_revision_decisions(principal, run.mission_id, run.run_id)
                observation = revision_observation(run, snapshot, choices)
                if status in ACTIVE and observation['status'] != 'CURRENT' and snapshot.mission_revision > 0:
                    allow('canDecideRevision')
                if (status == 'cancelled' and choices and choices[-1].decision == 'REQUEST_REPLAN'
                        and choices[-1].actor_id == principal.actor_id and choices[-1].tenant_id == principal.tenant_id
                        and choices[-1].target_revision == snapshot.mission_revision):
                    allow('canApplyRevision')
            except EVIDENCE_ERRORS:
                pass
        latest = runtime.workflow_store.get_run(run.run_id)
        if (latest.runtime_revision != run.runtime_revision or latest.status != run.status or latest.mission_id != run.mission_id
                or latest.record_state != run.record_state or is_superseded(latest) != is_superseded(run)
                or runtime.workflow_store.get_mission(run.mission_id).record_state != mission.record_state):
            return finish('SNAPSHOT_CHANGED')
        return finish()
    except PermissionError:
        return finish('AUTHORITY_DENIED')
    except EVIDENCE_ERRORS:
        return finish('AUTHORITY_UNAVAILABLE')
