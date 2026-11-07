"""Trusted Runtime proposal adapter. Accept facts; never lower or execute graphs."""
from contextlib import nullcontext
import hashlib
import json
from time import monotonic

from components.planner.planning_commit import PlanningCommitService
from components.planner.service import apply_task_plan_patch
from components.planner.task_decomposer import TaskDecompositionError
from components.planner.topology import EdgeOrigin, TopologyCompileError, validate_task_plan_for_execution
from contracts.mission_semantic import run_intent_basis
from contracts.planning import TaskPlan, TaskPlanPatch
from contracts import stable_checksum
from contracts.compiled_acg import load_compiled_acg_package
from contracts.planning_commit import (
    FrozenPlanningSources, PlanningCommitRequest, PlanningCommitRejection,
    PlanningCommitRejectionCode as Code,
)
from contracts.workflow import RuntimeRunRecord, RuntimeMissionRecord, MissionRecordState, WorkflowStatus
from support.acg.schema import RuntimeBlueprintSpec
from support.acg.capabilities import CapabilityCatalog
from runtime.planner_input_adapter import planner_input
from support.stores.planning_commit_store import content_fingerprint
from contracts.initial_planning import InitialPlanningSourceProvenance, initial_strategy_fingerprint


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def freeze_capability_catalog(catalog):
    frozen = CapabilityCatalog(descriptor.model_copy(deep=True) for descriptor in catalog.available())
    frozen.validate()
    return frozen


def with_semantic_ancestors(plan, keys):
    """Protect every declared parent path without compiling execution topology."""
    parents = {node.key: set() for node in plan.nodes}
    for node in plan.nodes:
        if node.parent_key is not None:
            parents[node.key].add(node.parent_key)
    for relation in plan.relations:
        if relation.relation_type.value == "parent":
            parents[relation.target_key].add(relation.source_key)
    protected = set(keys)
    pending = list(protected)
    while pending:
        for parent in parents.get(pending.pop(), ()):
            if parent not in protected:
                protected.add(parent)
                pending.append(parent)
    return protected


class RuntimePlanningCommitProvider:
    """One captured server candidate, with live SQLite sources inside acceptance.

    Caller holds the Runtime Run lock before entering the ledger transaction.
    BEGIN IMMEDIATE protects persisted Run/Mission sources; no reverse lock acquisition.
    """
    def __init__(self, authority, run_id, payload, initial, principal):
        self.authority = authority
        self.runtime = authority.runtime
        self.store = authority.store
        self.run_id = run_id
        self.payload = payload
        self.initial = initial
        self.principal = principal
        self.legacy_initial_sources = False
        self.initial_provenance = None

    def planning_guard(self, mission_id):
        return nullcontext()  # Runtime Run lock + store write transaction already held.

    @property
    def requires_versioned_initial_sources(self):
        return self.initial and not self.legacy_initial_sources

    def run(self):
        with self.store.connection() as conn:
            row = conn.execute("SELECT payload FROM runs WHERE run_id=?", (self.run_id,)).fetchone()
            if not row:
                raise ValueError("planning Run unavailable")
            return RuntimeRunRecord.model_validate_json(row[0])

    def authorize(self, request=None):
        run = self.run()
        if self.initial and (self.runtime.semantic_principal_provider is None
                or self.runtime.semantic_principal_provider() != self.principal):
            return False
        if (request is not None and run.mission_id != request.sources.mission_id) or self.principal is None:
            return False
        if self.runtime._run_cancellation_requested(run.run_id) or run.status in {
                WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED, WorkflowStatus.SUPERSEDED}:
            return False
        service = self.runtime.mission_semantic_service
        if service is None or service.store is not self.runtime.workflow_store:
            return False
        try:
            service.require_read_access(self.principal, run.mission_id)
            service.require_write_access(self.principal, run.mission_id)
            with self.store.connection() as conn:
                row = conn.execute("SELECT payload FROM tasks WHERE mission_id=?", (run.mission_id,)).fetchone()
            return bool(row and RuntimeMissionRecord.model_validate_json(row[0]).record_state == MissionRecordState.ACTIVE)
        except (PermissionError, ValueError, KeyError):
            return False

    def get_current_sources(self, mission_id, *, catalog_snapshot=None):
        sources = self._runtime_sources(mission_id, catalog_snapshot=catalog_snapshot)
        if self.initial and not self.legacy_initial_sources:
            try:
                origin = self.capture_initial_provenance(sources)
            except (ValueError, KeyError, TypeError):
                # A source that can no longer be captured is stale, never a
                # fallback to the old source projection or an accepted origin.
                return sources.model_copy(update={"strategy_fingerprint": fingerprint({
                    "projection": "initial-source-unavailable-v1", "runtime": sources.strategy_fingerprint})})
            return sources.model_copy(update={"strategy_fingerprint":
                initial_strategy_fingerprint(sources.strategy_fingerprint, origin)})
        return sources

    def capture_initial_provenance(self, sources=None):
        from runtime.initial_planning_sources import capture_initial_sources
        sources = sources or self._runtime_sources(self.run().mission_id)
        return capture_initial_sources(self, sources.strategy_fingerprint)

    def _runtime_sources(self, mission_id, *, catalog_snapshot=None):
        run = self.run()
        basis = run_intent_basis(run)
        if basis is None or basis.source_type != "SEMANTIC":
            raise ValueError("formal frozen basis required")
        with self.store.connection() as conn:
            row = conn.execute("SELECT revision FROM mission_semantic_state WHERE mission_id=?", (mission_id,)).fetchone()
        if not row:
            raise ValueError("formal Mission unavailable")
        loop = run.execution_state.get("planningLoop") or {}
        current = loop.get("current") or {}
        plan = run.execution_state.get("taskPlan")
        graph = run.acg_blueprint
        repositories = getattr(self.runtime.identity_lifecycle, "repositories", None)
        latest = repositories.task_plans.latest(run.mission_id) if repositories is not None else None
        context = {
            "run": run.run_id, "input": run.input, "scope": run.execution_scope.model_dump(mode="json") if run.execution_scope else None,
            "basis": basis.model_dump(mode="json"), "plan": plan, "graph": graph,
            "bindings": run.execution_state.get("taskBindings"),
            "steps": [s.model_dump(mode="json") for s in run.steps],
            "nodeCommits": self.node_commits(run),
            "runtimeRevision": None if self.initial else run.runtime_revision,
            "state": {k: v for k, v in run.execution_state.items() if k != "planningLoop"},
            "status": "preparing" if self.initial and run.status in {WorkflowStatus.PENDING, WorkflowStatus.PLANNING} else run.status.value,
            "catalog": [d.model_dump(mode="json") for d in
                        (catalog_snapshot if catalog_snapshot is not None else self.runtime.capability_catalog).available()],
            "identityPlan": latest.model_dump(mode="json") if latest is not None else None,
        }
        if run.review_mode != 'auto':
            context['reviewMode'] = run.review_mode
        return FrozenPlanningSources(missionId=run.mission_id, missionRevision=row[0],
            sourceKind="initial" if self.initial else "runtime",
            observationId=None if self.initial else current.get("observationId"),
            observationFingerprint=None if self.initial else fingerprint_observation(current),
            planVersion=None if self.initial else plan["planVersion"],
            graphVersion=None if self.initial else graph["version"],
            strategyFingerprint=fingerprint(context))

    def node_commits(self, run):
        if not run.steps:
            return []  # Initial L1/L2 worker has no executable nodes or receipts.
        return sorted(self.runtime.execution_value_store.list_node_commits(run_id=run.run_id),
                      key=lambda receipt: str(receipt.get("commitId", "")))

    def get_proposal_payload(self, request):
        return self.payload

    def get_source_provenance(self, request):
        if self.initial:
            if self.legacy_initial_sources:
                return None
            if self.initial_provenance is None:
                raise ValueError("initial acceptance has no frozen source capture")
            return InitialPlanningSourceProvenance.model_validate_json(self.initial_provenance.model_dump_json(by_alias=True))
        from runtime.graph_revision import planning_inputs, source_provenance
        run = self.run()
        workflow, catalog, profiles = planning_inputs(self, run)
        return source_provenance(self, run=run, inputs=(workflow,
            getattr(self, "_validated_catalog", None) or catalog, profiles))

    def validate_proposal(self, request):
        try:
            return self._validate_proposal(request)
        except (ValueError, KeyError, TopologyCompileError):
            return PlanningCommitRejection(code=Code.INVALID_PROPOSAL, reason="candidate failed deterministic semantic validation")

    def _validate_proposal(self, request):
        def reject(code, reason):
            return PlanningCommitRejection(code=code, reason=reason)
        run = self.run()
        basis = run_intent_basis(run)
        if not self.initial and run.review_mode == 'human_in_loop':
            return reject(Code.CONTROL_BARRIER_BLOCKED,
                          'human review policy revisions require a fresh explicitly accepted Run')
        if not run.execution_state.get("planningCommitRequired"):
            return reject(Code.INVALID_PROPOSAL, "Run requires an explicit durable acceptance fence")
        if run.execution_scope is None:
            return reject(Code.AUTHORITY_DENIED, "acceptance requires frozen capability scope")
        if (basis is None or basis.source_type != "SEMANTIC"
                or request.sources.mission_revision != basis.source_revision):
            return reject(Code.STALE_MISSION, "proposal does not bind the frozen Run basis")
        if self.runtime._run_cancellation_requested(run.run_id) or run.status in {
                WorkflowStatus.CANCELLED, WorkflowStatus.COMPLETED, WorkflowStatus.SUPERSEDED}:
            return reject(Code.AUTHORITY_DENIED, "Run is no longer available for acceptance")
        if self.payload.mission_id != run.mission_id or content_fingerprint(self.payload) != request.proposal_fingerprint:
            return reject(Code.INVALID_PROPOSAL, "candidate identity mismatch")
        catalog = getattr(self, "validation_catalog", None)
        if self.initial and self.initial_provenance is not None:
            catalog = CapabilityCatalog(d.model_copy(deep=True) for d in self.initial_provenance.validation_catalog)
        if catalog is None:
            catalog = freeze_capability_catalog(self.runtime.capability_catalog)
        self._validated_catalog = catalog
        if RuntimePlanningCommitProvider.get_current_sources(self, run.mission_id, catalog_snapshot=catalog) != request.sources:
            return reject(Code.STALE_STRATEGY, "semantic validation inputs do not match frozen sources")
        if len(self.payload.model_dump_json(by_alias=True)) > 300_000:
            return reject(Code.INVALID_PROPOSAL, "candidate content exceeds acceptance bounds")
        if run.active_step_ids or any(s.status.value in {"running", "retrying"} for s in run.steps):
            return reject(Code.CONTROL_BARRIER_BLOCKED, "active work cannot be revised")
        review = run.execution_state.get("reviewPayload")
        if (any(s.status.value == "waiting_review" for s in run.steps)
                or run.execution_state.get("controlFrames")
                or (review is not None and (not isinstance(review, dict) or review.get("subjectType") != "planner"))):
            return reject(Code.CONTROL_BARRIER_BLOCKED, "unresolved node or control review blocks acceptance")
        if self.initial:
            if (request.proposal_type != "initial_plan" or not isinstance(self.payload, TaskPlan)
                    or run.acg_blueprint or run.steps or run.execution_state.get("taskPlan")
                    or not run.execution_state.get("planningDeferred")
                    or run.status not in {WorkflowStatus.PENDING, WorkflowStatus.PLANNING}):
                return reject(Code.INVALID_PROPOSAL, "initial acceptance requires an unmaterialized Run")
            next_plan = self.payload
        else:
            try:
                fingerprint_observation((run.execution_state.get("planningLoop") or {}).get("current") or {}, run)
            except (ValueError, KeyError):
                return reject(Code.STALE_OBSERVATION, "observation does not match this Run boundary")
            if request.proposal_type != "plan_revision" or not isinstance(self.payload, TaskPlanPatch):
                return reject(Code.INVALID_PROPOSAL, "unsupported revision candidate")
            graph = run.acg_blueprint or {}
            if any(n.get("nodeType") == "control" for n in graph.get("nodes", ())):
                return reject(Code.CONTROL_BARRIER_BLOCKED, "control graph requires later safe-cut support")
            current = TaskPlan.model_validate(run.execution_state["taskPlan"])
            blueprint = RuntimeBlueprintSpec.model_validate(graph)
            package = load_compiled_acg_package(run.execution_state["compiledACGPackage"])
            if (package.blueprint_id != blueprint.graph_id or package.blueprint_version != blueprint.version
                    or package.blueprint_hash != stable_checksum(blueprint.model_dump(by_alias=True, mode="json"))
                    or package.run_id not in {None, run.run_id}
                    or run.execution_state.get("taskPlanVersion") != current.plan_version):
                return reject(Code.INVALID_PROPOSAL, "formal planning sources are inconsistent")
            bindings = run.execution_state.get("taskBindings", ())
            bound_steps = [b["acgNodeId"] for b in bindings]
            bound_tasks = [b["planNodeKey"] for b in bindings]
            if (len(set(bound_steps)) != len(bound_steps) or len(set(bound_tasks)) != len(bound_tasks)
                    or set(bound_steps) != {s.step_id for s in run.steps}
                    or not set(bound_tasks) <= {n.key for n in current.nodes}
                    or not {n.key for n in current.nodes if n.capability_requirements} <= set(bound_tasks)):
                return reject(Code.INVALID_PROPOSAL, "formal task bindings are inconsistent")
            if len(current.nodes) + len(self.payload.add_nodes) > 512 or len(self.payload.relations) > 1024:
                return reject(Code.INVALID_PROPOSAL, "revision input exceeds acceptance bounds")
            protected = {b["planNodeKey"] for b in run.execution_state.get("taskBindings", ())
                if any(s.step_id == b["acgNodeId"] and (s.status.value != "pending" or s.output
                       or s.resolved_input or s.started_at or s.completed_at or s.attempt > 0
                       or s.step_id in run.completed_step_ids
                       or (run.execution_state.get("outputRefs") or {}).get(s.step_id))
                       for s in run.steps)}
            receipts = self.node_commits(run)
            protected.update(b["planNodeKey"] for b in run.execution_state.get("taskBindings", ())
                if any(str(r.get("commitId", "")).startswith(f"commit:{run.run_id}:{b['acgNodeId']}:")
                       or r.get("commitId") == f"single-step-retry:{run.run_id}:{b['acgNodeId']}"
                       for r in receipts))
            protected = with_semantic_ancestors(current, protected)
            touched = set(self.payload.retire_keys) | set(self.payload.replace_keys)
            touched |= {r.source_key for r in self.payload.remove_relations} | {r.target_key for r in self.payload.remove_relations}
            touched |= {r.target_key for r in self.payload.relations}
            if touched & protected:
                return reject(Code.INVALID_PROPOSAL, "started or settled work cannot be changed")
            if self.payload.base_plan_version != current.plan_version:
                return reject(Code.STALE_PLAN, "patch bases on another formal plan")
            next_plan = apply_task_plan_patch(current, self.payload, catalog)
            # The compiler may infer capability/terminal edges absent from the
            # raw patch. Its validated result must preserve settled predecessors.
            prior_incoming = {r for r in current.relations if r.target_key in protected}
            next_incoming = {r for r in next_plan.relations if r.target_key in protected}
            prior_nodes = {n.key: n for n in current.nodes if n.key in protected}
            next_nodes = {n.key: n for n in next_plan.nodes if n.key in protected}
            if prior_incoming != next_incoming or prior_nodes != next_nodes:
                return reject(Code.INVALID_PROPOSAL, "compiled candidate changes started or settled work")
            by_key = {n.key: n for n in current.nodes}
            for node in self.payload.add_nodes:
                prior = by_key.get(node.key)
                if prior and (not set(prior.acceptance_criteria) <= set(node.acceptance_criteria)
                        or not set(prior.source_refs) <= set(node.source_refs)
                        or not set(prior.capability_requirements) <= set(node.capability_requirements)
                        or not {fingerprint(c) for c in prior.constraints} <= {fingerprint(c) for c in node.constraints}):
                    return reject(Code.INVALID_PROPOSAL, "replacement weakens existing task obligations")
        if len(next_plan.nodes) > 256 or len(next_plan.relations) > 1024:
            return reject(Code.INVALID_PROPOSAL, "candidate exceeds acceptance bounds")
        if next_plan.control_policies:
            return reject(Code.CONTROL_BARRIER_BLOCKED, "control policies require later safe-cut support")
        validated = validate_task_plan_for_execution(capability_catalog=catalog,
            mission_id=run.mission_id, plan_version=next_plan.plan_version, nodes=next_plan.nodes,
            relations=next_plan.relations, expected_artifacts=next_plan.expected_artifacts,
            control_policies=next_plan.control_policies, relation_origin=EdgeOrigin.PLAN_PATCH,
            metadata=next_plan.metadata) if self.initial else next_plan
        if set(request.requested_scope) != {n.key for n in validated.nodes}:
            return reject(Code.DEPENDENCY_NOT_CLOSED, "this phase accepts complete semantic candidates only")
        from runtime.human_review_policy import validate_review_policy
        try:
            validate_review_policy(validated, run.review_mode)
        except ValueError as exc:
            return reject(Code.INVALID_PROPOSAL, str(exc))
        if validated.metadata.get("missionIntentBasisRef") != basis.reference():
            return reject(Code.INVALID_PROPOSAL, "candidate changed frozen basis reference")
        for node in validated.nodes:
            if node.workset:
                node.workset.validate_sources(run.input.get("materialRefs") or ())
            if run.execution_scope and not set(node.capability_requirements) <= set(run.execution_scope.capability_ids):
                return reject(Code.AUTHORITY_DENIED, "candidate exceeds frozen capability scope")
        obligations = {c.constraint_id: c.text for c in basis.constraints}
        changed = validated.nodes if self.initial else self.payload.add_nodes
        for node in changed:
            for identifier, text in obligations.items():
                if not any(c.get("constraintId") == identifier and (c.get("value") == text or c.get("text") == text)
                           for c in node.constraints):
                    return reject(Code.INVALID_PROPOSAL, "candidate omits a frozen Mission constraint")
        return None


def fingerprint_observation(current, run=None):
    from contracts.runtime_planning import RuntimePlanningObservation
    observed = RuntimePlanningObservation.model_validate(current["observation"])
    if current.get("observationId") != observed.fingerprint():
        raise ValueError("persisted observation fingerprint mismatch")
    if run is None:
        return observed.fingerprint()
    if (observed.run_id != run.run_id or observed.mission_id != run.mission_id
            or observed.plan_version != run.execution_state["taskPlan"]["planVersion"]
            or observed.graph_version != run.acg_blueprint["version"]
            or observed.graph_id != run.acg_blueprint["graphId"]):
        raise ValueError("observation belongs to a different planning boundary")
    bindings = {b["acgNodeId"]: b["planNodeKey"] for b in run.execution_state.get("taskBindings", ())}
    steps = {s.step_id: s for s in run.steps}
    if len(observed.steps) != len(steps) or len({s.step_id for s in observed.steps}) != len(steps):
        raise ValueError("observation must cover each Run step exactly once")
    for step in observed.steps:
        if (step.step_id not in steps or step.task_key != bindings.get(step.step_id)
                or step.status != steps[step.step_id].status.value):
            raise ValueError("observation step binding or state is stale")
    return observed.fingerprint()


class RuntimePlanningCommitAuthority:
    def __init__(self, *, runtime, store):
        if getattr(runtime.workflow_store, "db_path", None) is None or store.db_path != runtime.workflow_store.db_path.resolve():
            raise ValueError("planning ledger must share the Workflow SQLite database")
        self.runtime = runtime
        self.store = store

    def _provider(self, run_id, payload, initial):
        principal = self.runtime.semantic_principal_provider() if self.runtime.semantic_principal_provider else None
        return RuntimePlanningCommitProvider(self, run_id, payload, initial, principal)

    def accept_graph_revision(self, run_id, source_commit_id, *, idempotency_key):
        from runtime.graph_revision import accept_graph_revision
        return accept_graph_revision(self, run_id, source_commit_id, idempotency_key)

    def _request(self, provider, payload, proposal_id, key, captured_sources=None, expected=None):
        sources = captured_sources or provider.get_current_sources(payload.mission_id)
        run = provider.run()
        basis = run_intent_basis(run)
        # Sources in a request describe the frozen basis, not a silently adopted new Mission.
        sources = sources.model_copy(update={"mission_revision": basis.source_revision})
        if isinstance(payload, TaskPlan):
            scope = tuple(n.key for n in payload.nodes)
        else:
            keys = {n["key"] for n in run.execution_state["taskPlan"]["nodes"]} - set(payload.retire_keys)
            scope = tuple(keys | {n.key for n in payload.add_nodes})
        parent = self.store.latest(run.mission_id)
        return PlanningCommitRequest(proposalId=self.proposal_identity(provider.run_id, proposal_id),
            proposalType="initial_plan" if provider.initial else "plan_revision",
            proposalFingerprint=content_fingerprint(payload), sources=sources, requestedScope=scope,
            idempotencyKey=key, expectedCommitmentRevision=expected if expected is not None else parent.commitment_revision if parent else 0)

    @staticmethod
    def proposal_identity(run_id, proposal_id):
        return "runtime-candidate:" + fingerprint({"run": run_id, "proposal": proposal_id})

    @staticmethod
    def replay_request(record, key, fingerprint=None, proposal_id=None):
        return PlanningCommitRequest(proposalId=proposal_id or record.proposal_id, proposalType=record.proposal_type,
            proposalFingerprint=fingerprint or record.proposal_fingerprint, sources=record.sources,
            requestedScope=record.requested_scope, idempotencyKey=key,
            expectedCommitmentRevision=record.expected_commitment_revision)

    def accept_patch_locked(self, run_id, patch, *, proposal_id, idempotency_key, graph_id=None, graph_version=None):
        """Called with Runtime Run lock held; no nested RunLock acquisition."""
        patch = TaskPlanPatch.model_validate(patch.model_dump(mode="json", by_alias=True))
        provider = self._provider(run_id, patch, False)
        service = PlanningCommitService(current_state_provider=provider, store=self.store)
        if provider.authorize() is not True:
            return PlanningCommitRejection(code=Code.AUTHORITY_DENIED, reason="planning acceptance not authorized")
        run = provider.run()
        if graph_id is not None and graph_id != run.acg_blueprint["graphId"]:
            return PlanningCommitRejection(code=Code.STALE_GRAPH, reason="semantic request graph identity changed")
        existing = self.store.get_by_idempotency_key(idempotency_key)
        if existing:
            if graph_version is not None and graph_version != existing.sources.graph_version:
                return PlanningCommitRejection(code=Code.STALE_GRAPH, reason="idempotent semantic request graph version changed")
            return service.accept(self.replay_request(existing, idempotency_key, content_fingerprint(patch),
                self.proposal_identity(run_id, proposal_id)))
        if (graph_id is not None and graph_id != run.acg_blueprint["graphId"]
                or graph_version is not None and graph_version != run.acg_blueprint["version"]):
            return PlanningCommitRejection(code=Code.STALE_GRAPH, reason="semantic request graph changed")
        return service.accept(self._request(provider, patch, proposal_id, idempotency_key))

    def accept_initial(self, run_id):
        try:
            return self._accept_initial(run_id)
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, TaskDecompositionError) and "INITIAL_CONTROL_GRAPH_UNSUPPORTED" in str(exc):
                return PlanningCommitRejection(code=Code.INVALID_PROPOSAL, reason=(
                    "INITIAL_CONTROL_GRAPH_UNSUPPORTED: planner still proposed a control loop after bounded repair; "
                    "initial planning requires a forward-only DAG preserving verification obligations"))
            return PlanningCommitRejection(code=Code.STALE_STRATEGY, reason="initial compilation sources unavailable or inconsistent")

    def validate_initial_sources(self, commit_id):
        """Read-only preflight for future materialization, never an execution grant."""
        try:
            if self.runtime.planning_commit_authority is not self:
                return PlanningCommitRejection(code=Code.AUTHORITY_DENIED, reason="initial source authority unavailable")
            record = self.store.get(commit_id)
            if (record is None or record.proposal_type != "initial_plan"
                    or not isinstance(record.source_provenance, InitialPlanningSourceProvenance)):
                return PlanningCommitRejection(code=Code.INVALID_PROPOSAL, reason="versioned initial sources required")
            provider = self._provider(record.source_provenance.source_run_id, record.proposal_payload, True)
            provider.initial_provenance = record.source_provenance
            if provider.authorize() is not True:
                return PlanningCommitRejection(code=Code.AUTHORITY_DENIED, reason="initial sources not authorized")
            if self.store.latest(record.mission_id) != record:
                return PlanningCommitRejection(code=Code.STALE_COMMITMENT, reason="initial acceptance head changed")
            return PlanningCommitService(current_state_provider=provider, store=self.store).validate_sources(record.sources)
        except (ValueError, KeyError, TypeError):
            return PlanningCommitRejection(code=Code.INVALID_PROPOSAL, reason="invalid initial source evidence")

    def _accept_initial(self, run_id):
        """Semantic planning happens outside Run lock and database write transaction."""
        key = "initial-planning:" + run_id
        with self.runtime.run_lock_manager.lock_for(run_id):
            existing = self.store.get_by_idempotency_key(key)
            if existing:
                provider = self._provider(run_id, existing.proposal_payload, True)
                provider.legacy_initial_sources = existing.source_provenance is None
                provider.initial_provenance = existing.source_provenance
                service = PlanningCommitService(current_state_provider=provider, store=self.store)
                problem = service.validate_sources(existing.sources)
                return problem or service.accept(self.replay_request(existing, key))
            provider = self._provider(run_id, None, True)
            run = provider.run()
            if provider.authorize() is not True:
                return PlanningCommitRejection(code=Code.AUTHORITY_DENIED, reason="initial planning acceptance not authorized")
            if not run.execution_state.get("planningCommitRequired"):
                return PlanningCommitRejection(code=Code.INVALID_PROPOSAL, reason="initial Run requires an acceptance fence")
            captured = provider.get_current_sources(run.mission_id)
            origin = provider.capture_initial_provenance()
            if initial_strategy_fingerprint(origin.runtime_fingerprint, origin) != captured.strategy_fingerprint:
                return PlanningCommitRejection(code=Code.STALE_STRATEGY, reason="initial sources changed while capturing")
            basis = run_intent_basis(run)
            if basis.source_revision != captured.mission_revision:
                return PlanningCommitRejection(code=Code.STALE_MISSION, reason="initial proposal bases on an older Mission")
            parent = self.store.latest(run.mission_id)
            expected = parent.commitment_revision if parent else 0
        engine = self.runtime._planning_engine_for_run(run)
        workflow = origin.workflow.model_copy(deep=True)
        # L1/L2 consumes a private catalog; the post-planning source fence still
        # compares the current registries and Identity with this captured origin.
        catalog = CapabilityCatalog(d.model_copy(deep=True) for d in origin.catalog)
        engine.semantic_planner.capability_catalog = catalog
        engine.semantic_planner.task_decomposer.capability_catalog = catalog
        engine.intent_parser.capability_catalog = catalog
        profile = None
        if workflow.planning_nodes:
            plan = engine.semantic_planner.plan_template(mission_id=run.mission_id, workflow=workflow,
                strategy="initial_commit_candidate")
        else:
            data = planner_input(basis, run.input)
            if self.runtime.attachment_context_builder is not None:
                data = self.runtime.attachment_context_builder.enrich(data)
                data = planner_input(basis, data)
            deadline = monotonic() + engine._planning_total_timeout_seconds()
            profile = engine.intent_parser.parse(intent=basis.objective, domain=workflow.domain,
                task_type=workflow.intent, task_input=data, use_llm=not bool(run.input.get("deterministicIntent")),
                declared_capabilities=list(workflow.required_capabilities or ()), planning_deadline=deadline, run_id=run_id)
            plan = engine.semantic_planner.plan_profile(mission_id=run.mission_id, profile=profile,
                strategy="initial_commit_candidate", task_input=data,
                existing_semantic_tasks=self.runtime._existing_semantic_task_catalog(run.mission_id),
                use_llm=not bool(run.input.get("deterministicIntent")), planning_deadline=deadline, run_id=run_id)
        # Server-owned immutable basis binds the candidate, including template planning.
        nodes = tuple(n.model_copy(deep=True, update={"constraints": [*n.constraints,
            *[dict(type="mission_constraint", value=c.text, constraintId=c.constraint_id,
                   sourceRefs=list(c.source_refs)) for c in basis.constraints
              if not any(x.get("constraintId") == c.constraint_id for x in n.constraints)]]}) for n in plan.nodes)
        plan = plan.model_copy(deep=True, update={"nodes": nodes,
            "metadata": {**plan.metadata, "missionIntentBasisRef": basis.reference()}})
        from runtime.human_review_policy import bind_review_policy
        plan = bind_review_policy(plan, run.review_mode)
        resolve = getattr(self.runtime.identity_lifecycle, "resolve_task_plan_snapshot", None)
        if callable(resolve):
            plan = resolve(plan)
        if profile is not None:
            # Keep the actual L1 lowering input, rather than asking a model to
            # recreate complexity/entropy/evidence choices at materialization.
            origin = origin.model_copy(deep=True, update={"semantic_profile": profile.model_copy(deep=True)})
            origin = InitialPlanningSourceProvenance.model_validate({
                **origin.model_dump(mode="json", by_alias=True), "staticFingerprint": origin.content_fingerprint()})
            captured = captured.model_copy(update={"strategy_fingerprint":
                initial_strategy_fingerprint(origin.runtime_fingerprint, origin)})
        with self.runtime.run_lock_manager.lock_for(run_id):
            provider = self._provider(run_id, plan, True)
            provider.initial_provenance = origin
            request = self._request(provider, plan, key, key, captured, expected)
            return PlanningCommitService(current_state_provider=provider, store=self.store).accept(request)

    def get_commit(self, commit_id):
        record = self.store.get(commit_id)
        if record is None:
            return None
        principal = self.runtime.semantic_principal_provider() if self.runtime.semantic_principal_provider else None
        if principal is None or self.runtime.mission_semantic_service is None:
            raise PermissionError("planning commitment read not authorized")
        self.runtime.mission_semantic_service.require_read_access(principal, record.mission_id)
        if self.runtime.workflow_store.get_mission(record.mission_id).record_state != MissionRecordState.ACTIVE:
            raise ValueError("planning commitment Mission unavailable")
        return record
