"""RuntimeGraph-authoritative ACG scheduler with snapshot execution barriers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from agentos.core.acg import (
    ACGBlueprint,
    AgentNode,
    ControlNode,
    ControlType,
    EdgeType,
    StepNode,
    validate_blueprint,
)
from agentos.core.communication import (
    ContextAssembler,
    ContextContractError,
    ProvenanceLedger,
    validate_contract_payload,
)
from agentos.core.conditions import ConditionEvaluationError, ConditionEvaluator
from agentos.core.execution.fault_injection import FaultInjector, InjectedFault
from agentos.core.execution.package import StepExecutionOutcome, StepExecutionPackage
from agentos.core.execution.projection import refresh_run_execution_projection
from agentos.core.execution.step_wrapper import StepExecutionTimer, input_summary, output_summary
from agentos.core.models.types import (
    AgentTask,
    StepStatus,
    TraceEventType,
    WorkflowRun,
    WorkflowStatus,
    utc_now,
)
from agentos.core.recovery.errors import PatchConflictError, PatchValidationError
from agentos.core.recovery.policy import EventPolicyAction
from agentos.core.runtime_graph import (
    RuntimeAttempt,
    RuntimeEvent,
    RuntimeEventStatus,
    RuntimeGraph,
    RuntimeNode,
)
from agentos.memory.workflow_memory import WorkflowMemory

if TYPE_CHECKING:
    from agentos.core.runtime import WorkflowRuntime


class ACGExecutor:
    """Schedule RuntimeGraph ready nodes and atomically commit detached outcomes."""

    def __init__(self, runtime: "WorkflowRuntime", *, max_parallelism: int = 4):
        self.runtime = runtime
        self.max_parallelism = max(1, max_parallelism)
        self.fault_injector = FaultInjector()

    async def run(self, *, task: AgentTask, run: WorkflowRun, workflow, blueprint: ACGBlueprint) -> WorkflowRun:
        validate_blueprint(blueprint)
        self.fault_injector = FaultInjector.from_config(task.input.get("faultInjection"))
        async with self.runtime.run_lock_manager.lock_for(run.run_id):
            latest = self.runtime.workflow_store.get_run(run.run_id)
            candidate = latest.model_copy(deep=True)
            candidate.acg_blueprint = blueprint.model_dump(by_alias=True, mode="json")
            candidate.execution_state = {
                **candidate.execution_state,
                "scheduleRound": int(candidate.execution_state.get("scheduleRound", 0)),
                "faultInjectionTriggered": 0,
            }
            source_materials = [
                item for item in (candidate.input.get("sourceMaterials") or []) if isinstance(item, dict)
            ]
            if source_materials:
                ledger = ProvenanceLedger.from_graph(
                    candidate.provenance,
                    run_id=candidate.run_id,
                    task_id=candidate.task_id,
                )
                if ledger.latest_production("__task_input__") is None:
                    contract_text = str(candidate.input.get("contractText") or "")
                    ledger.record_production(
                        "__task_input__",
                        {"contractText": contract_text, "sourceMaterials": source_materials},
                        max(1, len(contract_text) // 4),
                        agent_name="material_ingest",
                        evidence_refs=[
                            str(item.get("uri") or f"material://{item.get('materialId')}")
                            for item in source_materials
                            if item.get("materialId")
                        ],
                    )
                    first_step = next(
                        (node for node in blueprint.nodes if isinstance(node, StepNode)),
                        None,
                    )
                    if first_step is not None:
                        ledger.record_consumption(
                            first_step.node_id,
                            ["__task_input__"],
                            ["contractText", "sourceMaterials"],
                            consumer_agent_name=first_step.agent_name,
                            fields_by_producer={"__task_input__": ["contractText", "sourceMaterials"]},
                            data={"contractText": contract_text, "sourceMaterials": source_materials},
                            tokens_delivered=max(1, len(contract_text) // 4),
                            tokens_available=max(1, len(contract_text) // 4),
                        )
                    candidate.provenance = ledger.to_graph()
            self.runtime._transition_run_if_needed(candidate, WorkflowStatus.RUNNING)
            self.runtime.task_manager.mark_running(task)
            self.runtime.trace_store.append(
                run=candidate,
                event_type=TraceEventType.RUN_STARTED,
                observation=f"ACG execution started: {blueprint.graph_id}",
                payload={"graphId": blueprint.graph_id, "nodeCount": blueprint.node_count,
                         "edgeCount": blueprint.edge_count, "engine": "acg"},
            )
            self.runtime.workflow_store.save_run(candidate)
        return await self._drive(task=task, run=candidate, workflow=workflow, blueprint=blueprint)

    async def resume(self, *, task: AgentTask, run: WorkflowRun, workflow, blueprint: ACGBlueprint) -> WorkflowRun:
        validate_blueprint(blueprint)
        self.fault_injector = FaultInjector.from_config(task.input.get("faultInjection"))
        self.fault_injector.restore_triggered_count(
            int(run.execution_state.get("faultInjectionTriggered", 0))
        )
        return await self._drive(task=task, run=run, workflow=workflow, blueprint=blueprint)

    async def _drive(self, *, task, run, workflow, blueprint: ACGBlueprint) -> WorkflowRun:
        """Reload, schedule, execute snapshots, and commit at a batch barrier."""

        run_id = run.run_id  # only identity is retained; every round reloads authority
        while True:
            packages = await self._schedule_batch(task, workflow, run_id)
            if packages is None:
                return self.runtime.workflow_store.get_run(run_id)
            if not packages:
                return self.runtime.workflow_store.get_run(run_id)
            outcomes = await asyncio.gather(
                *(self._execute_package(task, workflow, package) for package in packages)
            )
            should_continue = await self._commit_batch(task, outcomes)
            if not should_continue:
                return self.runtime.workflow_store.get_run(packages[0].run_id)

    async def _schedule_batch(self, task, workflow, run_id: str) -> list[StepExecutionPackage] | None:
        del workflow
        async with self.runtime.run_lock_manager.lock_for(run_id):
            latest = self.runtime.workflow_store.get_run(run_id)
            graph = latest.runtime_graph
            if graph is None:
                raise RuntimeError("RUNTIME_GRAPH_MISSING")
            if latest.status == WorkflowStatus.CANCELLED:
                return None
            candidate = latest.model_copy(deep=True)
            graph = candidate.runtime_graph
            assert graph is not None
            graph.resolve_ready_control_nodes()
            candidate, event_patch = self._apply_next_pending_event(candidate)
            if event_patch is None and not any(
                node.status == StepStatus.FAILED for node in candidate.runtime_graph.nodes
            ):
                try:
                    candidate, _ = self._apply_next_ready_condition(candidate)
                except (ConditionEvaluationError, PatchValidationError, PatchConflictError) as exc:
                    self.runtime._transition_run_if_needed(candidate, WorkflowStatus.FAILED)
                    self.runtime.task_manager.mark_failed(task)
                    candidate.error = getattr(exc, "code", "CONDITION_EVALUATION_FAILED")
                    self.runtime.trace_store.append(
                        run=candidate,
                        event_type=TraceEventType.RUN_FAILED,
                        observation=str(exc),
                        payload={
                            "errorCode": candidate.error,
                            "graphVersion": candidate.runtime_graph.graph_version,
                        },
                    )
                    self.runtime.workflow_store.save_run(candidate)
                    return None
            graph = candidate.runtime_graph
            assert graph is not None
            refresh_run_execution_projection(candidate)

            if graph.has_waiting_review():
                self.runtime._transition_run_if_needed(candidate, WorkflowStatus.WAITING_REVIEW)
                self.runtime.workflow_store.save_run(candidate)
                return None
            ready = graph.ready_set()
            if not ready:
                if graph.all_steps_completed():
                    refresh_run_execution_projection(candidate)
                    self.runtime._complete_run(task, candidate)
                    self.runtime.workflow_store.save_run(candidate)
                    return None
                if graph.has_running_nodes():
                    return None
                failed = [node for node in graph.nodes if node.status == StepStatus.FAILED]
                if failed:
                    self.runtime._transition_run_if_needed(candidate, WorkflowStatus.FAILED)
                    self.runtime.task_manager.mark_failed(task)
                    candidate.error = failed[0].error or "runtime node failed"
                else:
                    self.runtime._transition_run_if_needed(candidate, WorkflowStatus.FAILED)
                    self.runtime.task_manager.mark_failed(task)
                    candidate.error = "RUNTIME_GRAPH_DEADLOCK"
                    self.runtime.trace_store.append(
                        run=candidate,
                        event_type=TraceEventType.RUN_FAILED,
                        observation="Runtime graph has no ready, running, or review node",
                        payload={"errorCode": "RUNTIME_GRAPH_DEADLOCK", "graphVersion": graph.graph_version},
                    )
                self.runtime.workflow_store.save_run(candidate)
                return None

            selected = self._select_batch(graph, ready)
            schedule_round = int(candidate.execution_state.get("scheduleRound", 0)) + 1
            candidate.execution_state["scheduleRound"] = schedule_round
            packages: list[StepExecutionPackage] = []
            for node in selected:
                self.runtime.runtime_controller.transition_node_state(node, StepStatus.RUNNING)
                binding = dict(node.current_binding or {})
                binding_id = str(
                    binding.get("bindingId")
                    or binding.get("assignedAgentId")
                    or binding.get("agentName")
                    or node.node_id
                )
                attempt = RuntimeAttempt(
                    attemptNumber=len(node.attempts) + 1,
                    graphVersion=graph.graph_version,
                    bindingId=binding_id,
                    agentName=str(binding.get("agentName") or node.spec.get("agentName") or ""),
                    modelName=str(binding.get("modelName") or ""),
                    status=StepStatus.RUNNING,
                )
                node.attempts.append(attempt)
                self.runtime.trace_store.append(
                    run=candidate,
                    event_type=TraceEventType.STEP_SCHEDULED,
                    step_id=node.node_id,
                    agent_name=attempt.agent_name,
                    observation=f"Step scheduled (ready set size={len(ready)})",
                    payload=self._correlation(graph, node, attempt, scheduled=graph.graph_version)
                    | {"readySet": [item.node_id for item in ready],
                       "batch": [item.node_id for item in selected],
                       "batchId": f"batch_{schedule_round:04d}"},
                )
                self.runtime.trace_store.append(
                    run=candidate,
                    event_type=TraceEventType.STEP_STARTED,
                    step_id=node.node_id,
                    agent_name=attempt.agent_name,
                    observation=f"Step started: {node.spec.get('name') or node.node_id}",
                    payload=self._correlation(graph, node, attempt, scheduled=graph.graph_version)
                    | {"inputSummary": input_summary(node.spec.get("inputSpec") or {})},
                )
            refresh_run_execution_projection(candidate)
            candidate.updated_at = utc_now()
            self.runtime.workflow_store.save_run(candidate)

            graph = candidate.runtime_graph
            assert graph is not None
            for node in selected:
                persisted = graph.get_node(node.node_id)
                attempt = persisted.attempts[-1]
                packages.append(self._make_package(candidate, task, persisted, attempt))
            return packages

    def _make_package(self, run, task, node: RuntimeNode, attempt: RuntimeAttempt) -> StepExecutionPackage:
        graph = run.runtime_graph
        assert graph is not None
        source_ids = self._data_sources(graph, node.node_id)
        spec = node.spec.get("inputSpec") or {}
        if not isinstance(spec.get("from"), dict) and not isinstance(spec.get("fields"), list):
            source_ids = [
                item.node_id for item in graph.nodes
                if item.node_id != node.node_id and item.status == StepStatus.COMPLETED and item.output
            ]
        upstream = {source_id: dict(graph.get_node(source_id).output) for source_id in source_ids}
        return StepExecutionPackage(
            runId=run.run_id,
            taskId=task.task_id,
            graphId=graph.graph_id,
            graphVersion=graph.graph_version,
            runtimeNodeId=node.node_id,
            attemptId=attempt.attempt_id,
            attemptNumber=attempt.attempt_number,
            binding=dict(node.current_binding or {}),
            nodeSpec=dict(node.spec),
            runInput=dict(run.input),
            upstreamOutputs=upstream,
            contextMetadata={"objective": ACGBlueprint.model_validate(run.acg_blueprint).objective},
            timeout=int(node.spec.get("timeout") or 0),
            runSnapshot=run.model_dump(by_alias=True, mode="json"),
        )

    async def _execute_package(self, task, workflow, package: StepExecutionPackage) -> StepExecutionOutcome:
        """Perform remote work against a private snapshot and return a detached outcome."""

        started_at = utc_now()
        local_run = WorkflowRun.model_validate(package.run_snapshot)
        graph = local_run.runtime_graph
        assert graph is not None
        node = graph.get_node(package.runtime_node_id)
        step_node = StepNode.model_validate(package.node_spec)
        step = local_run.get_step(package.runtime_node_id)
        binding_id = str(
            package.binding.get("bindingId")
            or package.binding.get("assignedAgentId")
            or package.binding.get("agentName")
            or node.node_id
        )
        ledger = ProvenanceLedger(run_id=package.run_id, task_id=package.task_id)
        assembler = ContextAssembler(ledger)
        resolved: dict[str, Any] = {}
        pack = None
        timer = StepExecutionTimer()
        try:
            if package.upstream_outputs:
                pack = assembler.assemble(
                    run_id=package.run_id,
                    task_id=package.task_id,
                    runtime_graph=graph,
                    step_node=step_node,
                    objective=str(package.context_metadata.get("objective") or ""),
                    upstream_outputs=package.upstream_outputs,
                    consumer_agent_name=step.agent_name,
                    attempt=package.attempt_number,
                    attempt_id=package.attempt_id,
                    binding_id=binding_id,
                )
                resolved = dict(pack.data)
                step.resolved_input = resolved
            memory = WorkflowMemory.from_context_pack(local_run, pack) if pack else WorkflowMemory(
                run_id=package.run_id, task_input=dict(package.run_input), observations={}
            )
            self.fault_injector.fire(package.runtime_node_id)
            dispatch = self.runtime.orchestrator.dispatch_agent(
                task=task, run=local_run, workflow=workflow, step=step, memory=memory, context_pack=pack
            )
            result, _ = await asyncio.wait_for(dispatch, timeout=package.timeout) if package.timeout > 0 else await dispatch
            output = dict(result.output)
            tool_executions = [
                dict(item) for item in result.tool_executions if isinstance(item, dict)
            ]
            model_invocations = [
                dict(item) for item in result.model_invocations if isinstance(item, dict)
            ]
            evidence_refs = list(dict.fromkeys(result.evidence_refs))
            runtime_signals = [
                dict(item)
                for item in (output.get("runtimeSignals") or [])
                if isinstance(item, dict)
            ]
            validate_contract_payload(output, step_node.output_spec, step_id=node.node_id, direction="output")
            status = StepStatus.WAITING_REVIEW if step.requires_review and local_run.review_mode != "auto" else StepStatus.COMPLETED
            events = [
                {"eventType": TraceEventType.DATA_PRODUCED, "observation": f"Data produced by {node.node_id}",
                 "payload": {"fields": sorted(output), "attempt": package.attempt_number}},
                {"eventType": TraceEventType.AGENT_CALLED, "observation": result.summary or f"Agent completed: {step.agent_name}",
                 "payload": output, "durationMs": timer.elapsed_ms()},
                {"eventType": TraceEventType.REVIEW_REQUIRED if status == StepStatus.WAITING_REVIEW else TraceEventType.STEP_SUCCEEDED,
                 "observation": f"Review required for step: {node.node_id}" if status == StepStatus.WAITING_REVIEW else f"Step succeeded: {step.name}",
                 "payload": output if status == StepStatus.WAITING_REVIEW else {"outputSummary": output_summary(output)},
                 "durationMs": timer.elapsed_ms()},
            ]
            tool_events = [
                {
                    "eventType": TraceEventType.TOOL_CALLED,
                    "observation": (
                        f"Read-only tool {item.get('toolName') or 'unknown'} "
                        f"{item.get('status') or 'completed'}"
                    ),
                    "payload": {
                        "callId": item.get("callId"),
                        "toolName": item.get("toolName"),
                        "status": item.get("status"),
                        "sourceRefs": list(item.get("sourceRefs") or []),
                        "errorCode": item.get("errorCode"),
                    },
                    "durationMs": int(item.get("durationMs") or 0),
                }
                for item in tool_executions
            ]
            model_events = [
                {
                    "eventType": TraceEventType.MODEL_CALLED,
                    "observation": "Structured model generation completed",
                    "payload": {
                        "provider": item.get("provider"),
                        "model": item.get("model"),
                        "promptVersion": item.get("promptVersion"),
                        "usage": dict(item.get("usage") or {}),
                    },
                    "durationMs": int(item.get("latencyMs") or 0),
                }
                for item in model_invocations
            ]
            events[0:0] = [*tool_events, *model_events]
            if pack is not None:
                events.insert(0, {"eventType": TraceEventType.DATA_CONSUMED,
                    "observation": f"Context assembled: {pack.tokens_delivered}/{pack.tokens_available} tokens (saved {pack.saving_ratio:.1%})",
                    "payload": pack.model_dump(by_alias=True, mode="json")})
            return self._outcome(package, status, started_at, output=output, resolved=resolved,
                                 events=events, provenance={
                                     "pack": pack.model_dump(by_alias=True, mode="json") if pack else None,
                                     "evidenceRefs": evidence_refs,
                                     "toolExecutions": tool_executions,
                                     "modelInvocations": model_invocations,
                                 },
                                 runtime_signals=runtime_signals)
        except Exception as exc:
            recoverable = isinstance(exc, InjectedFault) or package.attempt_number <= int(step_node.retry_limit)
            event_type = TraceEventType.CONTRACT_VIOLATION if isinstance(exc, ContextContractError) else TraceEventType.STEP_FAILED
            error_code = self._exception_code(exc)
            return self._outcome(package, StepStatus.RETRYING if recoverable else StepStatus.FAILED,
                                 started_at, error=str(exc), resolved=resolved, recoverable=recoverable,
                                 events=[{"eventType": event_type, "observation": str(exc),
                                          "payload": {"recoverable": recoverable, "attempt": package.attempt_number,
                                                      "errorCode": error_code, "errorType": type(exc).__name__}}],
                                 error_type=type(exc).__name__,
                                 error_code=error_code,
                                 error_direction=str(getattr(exc, "direction", None) or ""))

    async def _commit_batch(self, task, outcomes: list[StepExecutionOutcome]) -> bool:
        """Merge all accepted outcomes into one copy and persist once."""

        if not outcomes:
            return False
        run_id = outcomes[0].run_id
        async with self.runtime.run_lock_manager.lock_for(run_id):
            latest = self.runtime.workflow_store.get_run(run_id)
            candidate = latest.model_copy(deep=True)
            graph = candidate.runtime_graph
            assert graph is not None
            ledger = ProvenanceLedger.from_graph(candidate.provenance, run_id=run_id, task_id=task.task_id)
            accepted = False
            accepted_node_ids: set[str] = set()
            waiting_review = False
            fatal = False
            checkpoint_step_ids: list[str] = []
            for outcome in outcomes:
                node = graph.get_node(outcome.runtime_node_id)
                attempt = node.attempts[-1] if node.attempts else None
                if candidate.status == WorkflowStatus.CANCELLED:
                    self._late_outcome_trace(candidate, graph, node, outcome, "run cancelled")
                    continue
                if outcome.scheduled_graph_version != graph.graph_version or attempt is None or attempt.attempt_id != outcome.attempt_id or node.status != StepStatus.RUNNING:
                    self._late_outcome_trace(candidate, graph, node, outcome, "stale attempt")
                    continue
                accepted = True
                accepted_node_ids.add(node.node_id)
                attempt.resolved_input = dict(outcome.resolved_input)
                attempt.output = dict(outcome.output)
                attempt.error = outcome.error
                attempt.ended_at = outcome.ended_at
                attempt.status = StepStatus.FAILED if outcome.status == StepStatus.RETRYING else outcome.status
                model_invocations = [
                    dict(item)
                    for item in (outcome.provenance_events.get("modelInvocations") or [])
                    if isinstance(item, dict)
                ]
                if model_invocations:
                    attempt.model_name = str(model_invocations[-1].get("model") or attempt.model_name)
                    attempt.trace_context["modelInvocations"] = model_invocations
                node.error = outcome.error

                runtime_events = self.runtime.runtime_event_classifier.classify(
                    outcome, node, graph
                )
                structural_event = False
                blocked_reapplication = False
                for runtime_event in runtime_events:
                    persisted_event = graph.runtime_event_by_id(runtime_event.event_id)
                    if persisted_event is None:
                        graph.runtime_events.append(runtime_event)
                        persisted_event = runtime_event
                        self.runtime.trace_store.append(
                            run=candidate,
                            event_type=TraceEventType.RUNTIME_EVENT_CLASSIFIED,
                            step_id=node.node_id,
                            agent_name=attempt.agent_name,
                            observation=(
                                f"Runtime event classified: {runtime_event.event_type.value}"
                            ),
                            payload=self._runtime_event_trace_payload(runtime_event),
                        )
                    if persisted_event.event_id not in attempt.runtime_event_ids:
                        attempt.runtime_event_ids.append(persisted_event.event_id)
                    decision = self.runtime.runtime_event_policy.decide(
                        persisted_event, graph
                    )
                    if decision.action == EventPolicyAction.PROPOSE_PATCH:
                        structural_event = True
                        if persisted_event.event_id not in graph.pending_runtime_event_ids:
                            graph.pending_runtime_event_ids.append(persisted_event.event_id)
                    elif decision.action == EventPolicyAction.REQUEST_HUMAN:
                        blocked_reapplication = True
                        persisted_event.status = RuntimeEventStatus.REJECTED
                        persisted_event.status_reason = decision.reason
                        self.runtime.trace_store.append(
                            run=candidate,
                            event_type=TraceEventType.RUNTIME_RECIPE_REAPPLICATION_BLOCKED,
                            step_id=node.node_id,
                            observation=decision.reason,
                            payload=self._runtime_event_trace_payload(persisted_event)
                            | {"recipeId": decision.recipe_id},
                        )
                    else:
                        persisted_event.status = RuntimeEventStatus.IGNORED
                        persisted_event.status_reason = decision.reason
                        self.runtime.trace_store.append(
                            run=candidate,
                            event_type=TraceEventType.RUNTIME_EVENT_IGNORED,
                            step_id=node.node_id,
                            observation=decision.reason,
                            payload=self._runtime_event_trace_payload(persisted_event),
                        )

                if structural_event:
                    attempt.logical_completion_accepted = False
                    node.output = {}
                    node.error = outcome.error
                    self.runtime.runtime_controller.transition_node_state(
                        node, StepStatus.RETRYING
                    )
                elif blocked_reapplication:
                    attempt.logical_completion_accepted = False
                    node.output = {}
                    node.error = "RECIPE_REAPPLICATION_BLOCKED"
                    self.runtime.runtime_controller.transition_node_state(
                        node, StepStatus.FAILED
                    )
                    fatal = True
                elif outcome.output:
                    node.output = dict(outcome.output)
                    node.output_version += 1
                    self._record_degraded_output(candidate, node, attempt, outcome.output)
                    self.runtime.runtime_controller.transition_node_state(node, outcome.status)
                else:
                    self.runtime.runtime_controller.transition_node_state(node, outcome.status)
                outcome_trace_ids: list[str] = []
                for event in outcome.trace_events:
                    trace_event = self.runtime.trace_store.append(
                        run=candidate, event_type=event["eventType"], step_id=node.node_id,
                        agent_name=attempt.agent_name, observation=event.get("observation", ""),
                        payload=dict(event.get("payload") or {}) | self._correlation(graph, node, attempt, scheduled=outcome.scheduled_graph_version),
                        duration_ms=int(event.get("durationMs") or 0),
                    )
                    outcome_trace_ids.append(trace_event.event_id)
                if outcome_trace_ids:
                    for runtime_event in runtime_events:
                        persisted_event = graph.runtime_event_by_id(runtime_event.event_id)
                        if persisted_event is not None and persisted_event.source_trace_event_id is None:
                            persisted_event.source_trace_event_id = outcome_trace_ids[-1]
                pack = outcome.provenance_events.get("pack")
                if pack:
                    source_ids = list(pack.get("sourceStepIds") or [])
                    ledger.record_consumption(
                        node.node_id,
                        source_ids,
                        list((pack.get("data") or {}).keys()),
                        consumer_agent_name=attempt.agent_name,
                        attempt=attempt.attempt_number,
                        data=dict(pack.get("data") or {}),
                        tokens_delivered=int(pack.get("tokensDelivered") or 0),
                        tokens_available=int(pack.get("tokensAvailable") or 0),
                        saving_ratio=float(pack.get("savingRatio") or 0.0),
                        contract_status=str(pack.get("contractStatus") or "valid"),
                    )
                    edge_ids = [
                        edge.edge_id
                        for edge in graph.effective_edges(EdgeType.COMMUNICATION)
                        if edge.target_id == node.node_id and edge.source_id in source_ids
                    ]
                    ledger.record_interaction(
                        edge_ids=edge_ids,
                        producer_step_ids=source_ids,
                        consumer_step_id=node.node_id,
                        producer_agent_names=[
                            str((graph.get_node(source_id).current_binding or {}).get("agentName") or "")
                            for source_id in source_ids
                        ],
                        consumer_agent_name=attempt.agent_name,
                        fields_by_producer={
                            source_id: list((pack.get("sourceData") or {}).get(source_id, {}).keys())
                            for source_id in source_ids
                        },
                        tokens_delivered=int(pack.get("tokensDelivered") or 0),
                        tokens_available=int(pack.get("tokensAvailable") or 0),
                        saving_ratio=float(pack.get("savingRatio") or 0.0),
                        evidence_refs=list(pack.get("evidenceRefs") or []),
                        contract_status=str(pack.get("contractStatus") or "valid"),
                        data=dict(pack.get("data") or {}),
                    )
                if outcome.output:
                    ledger.record_production(
                        node.node_id,
                        dict(outcome.output),
                        0,
                        agent_name=attempt.agent_name,
                        attempt=attempt.attempt_number,
                        evidence_refs=list(outcome.provenance_events.get("evidenceRefs") or []),
                    )
                if structural_event:
                    candidate.recovery_count += 1
                elif outcome.status == StepStatus.WAITING_REVIEW:
                    waiting_review = True
                elif outcome.status == StepStatus.RETRYING:
                    candidate.recovery_count += 1
                    self.runtime.trace_store.append(
                        run=candidate, event_type=TraceEventType.RUN_RECOVERED, step_id=node.node_id,
                        agent_name=attempt.agent_name, observation=f"Automatic retry scheduled for {node.node_id}",
                        payload=self._correlation(graph, node, attempt, scheduled=outcome.scheduled_graph_version)
                        | {"strategy": "local_replan" if self.fault_injector.triggered_count else "retry"},
                    )
                elif outcome.status == StepStatus.FAILED:
                    fatal = True
            applied_patch = None
            if accepted:
                candidate.provenance = ledger.to_graph()
                candidate.execution_state["faultInjectionTriggered"] = self.fault_injector.triggered_count
                candidate, applied_patch = self._apply_next_pending_event(candidate)
                graph = candidate.runtime_graph
                assert graph is not None
                refresh_run_execution_projection(candidate)
                candidate.output = self.runtime.orchestrator.compose_final_output(candidate)
            candidate.updated_at = utc_now()
            waiting_review = graph.has_waiting_review()
            fatal = any(node.status == StepStatus.FAILED for node in graph.nodes)
            if fatal:
                self.runtime._transition_run_if_needed(candidate, WorkflowStatus.FAILED)
                self.runtime.task_manager.mark_failed(task)
                candidate.error = next((node.error for node in graph.nodes if node.status == StepStatus.FAILED), "step failed")
            elif waiting_review:
                self.runtime._transition_run_if_needed(candidate, WorkflowStatus.WAITING_REVIEW)
                self.runtime.task_manager.mark_waiting_review(task)
            elif accepted:
                self.runtime._transition_run_if_needed(candidate, WorkflowStatus.RUNNING)
                self.runtime.task_manager.mark_running(task)
            for outcome in outcomes:
                if outcome.runtime_node_id in accepted_node_ids and outcome.status in {
                    StepStatus.COMPLETED,
                    StepStatus.WAITING_REVIEW,
                    StepStatus.RETRYING,
                }:
                    if applied_patch is not None and outcome.runtime_node_id == (
                        applied_patch.target_node_id or applied_patch.runtime_node_id
                    ):
                        continue
                    try:
                        candidate.get_step(outcome.runtime_node_id)
                    except KeyError:
                        pass
                    else:
                        checkpoint_step_ids.append(outcome.runtime_node_id)
            if checkpoint_step_ids:
                self.runtime._create_checkpoint(
                    candidate,
                    candidate.get_step(checkpoint_step_ids[0]),
                    step_ids=checkpoint_step_ids,
                )
            self.runtime.workflow_store.save_run(candidate)
            return accepted and not waiting_review and not fatal and candidate.status != WorkflowStatus.CANCELLED

    def _apply_next_pending_event(self, loaded_run):
        """Apply at most one structural event to a caller-owned run copy.

        The caller must hold the shared run lock.  This method never saves; the
        surrounding schedule or batch barrier persists execution facts, event
        state, patch audit, checkpoint, and the new graph in one ``save_run``.
        """

        candidate = loaded_run
        while True:
            graph = candidate.runtime_graph
            assert graph is not None
            pending = [
                event
                for event_id in graph.pending_runtime_event_ids
                if (event := graph.runtime_event_by_id(event_id)) is not None
                and event.status == RuntimeEventStatus.PENDING
            ]
            if not pending:
                return candidate, None
            pending.sort(
                key=lambda event: (
                    -self.runtime.runtime_event_policy.decide(event, graph).priority,
                    event.created_at,
                    event.event_id,
                )
            )
            event = pending[0]
            decision = self.runtime.runtime_event_policy.decide(event, graph)
            if decision.action != EventPolicyAction.PROPOSE_PATCH:
                graph.pending_runtime_event_ids = [
                    event_id
                    for event_id in graph.pending_runtime_event_ids
                    if event_id != event.event_id
                ]
                event.status = (
                    RuntimeEventStatus.REJECTED
                    if decision.action in {EventPolicyAction.REQUEST_HUMAN, EventPolicyAction.FAIL}
                    else RuntimeEventStatus.IGNORED
                )
                event.status_reason = decision.reason
                trace_type = (
                    TraceEventType.RUNTIME_RECIPE_REAPPLICATION_BLOCKED
                    if decision.reason == "RECIPE_REAPPLICATION_BLOCKED"
                    else TraceEventType.RUNTIME_EVENT_IGNORED
                )
                self.runtime.trace_store.append(
                    run=candidate,
                    event_type=trace_type,
                    step_id=event.runtime_node_id,
                    observation=decision.reason,
                    payload=self._runtime_event_trace_payload(event)
                    | {"recipeId": decision.recipe_id},
                )
                if event.status == RuntimeEventStatus.REJECTED:
                    target = graph.get_node(event.target_node_id)
                    if target.status == StepStatus.RETRYING:
                        target.error = decision.reason
                        self.runtime.runtime_controller.transition_node_state(
                            target, StepStatus.FAILED
                        )
                continue

            proposal = None
            patch = None
            try:
                self.runtime.trace_store.append(
                    run=candidate,
                    event_type=TraceEventType.RUNTIME_RECIPE_SELECTED,
                    step_id=event.runtime_node_id,
                    observation=f"Selected runtime recovery recipe {decision.recipe_id}",
                    payload=self._runtime_event_trace_payload(event)
                    | {
                        "recipeId": decision.recipe_id,
                        "recipeVersion": decision.recipe_version,
                        "baseGraphVersion": graph.graph_version,
                    },
                )
                proposal = self.runtime.proposal_factory.propose(
                    event,
                    decision,
                    graph,
                    self.runtime.recovery_recipe_registry,
                    self.runtime.candidate_resolver,
                    domain=candidate.domain,
                    allowed_agent_ids=(
                        candidate.execution_scope.agent_ids
                        if candidate.execution_scope is not None
                        else None
                    ),
                )
                self.runtime.trace_store.append(
                    run=candidate,
                    event_type=TraceEventType.GRAPH_CHANGE_PROPOSED,
                    step_id=event.runtime_node_id,
                    observation=f"Proposed runtime graph change {proposal.proposal_id}",
                    payload=self._runtime_event_trace_payload(event)
                    | {
                        "proposalId": proposal.proposal_id,
                        "recipeId": proposal.recipe_id,
                        "baseGraphVersion": proposal.base_graph_version,
                        "targetNodeId": proposal.target_node_id,
                    },
                )
                patch = self.runtime.patch_compiler.compile(proposal, graph)
                candidate, result = self.runtime.runtime_controller.apply_patch_to_candidate(
                    candidate, patch
                )
                if not result.applied:
                    return candidate, None
                applied_graph = candidate.runtime_graph
                assert applied_graph is not None
                applied_event = applied_graph.runtime_event_by_id(event.event_id)
                assert applied_event is not None
                applied_event.status = RuntimeEventStatus.PROCESSED
                applied_event.status_reason = "PATCH_APPLIED"
                applied_graph.pending_runtime_event_ids = [
                    event_id
                    for event_id in applied_graph.pending_runtime_event_ids
                    if event_id != event.event_id
                ]
                applied_graph.event_to_patch[event.event_id] = patch.patch_id
                self.runtime.runtime_controller.create_patch_checkpoint(candidate, patch)
                return candidate, patch
            except (KeyError, ValueError, PatchValidationError, PatchConflictError) as exc:
                graph = candidate.runtime_graph
                assert graph is not None
                rejected = graph.runtime_event_by_id(event.event_id)
                assert rejected is not None
                rejected.status = RuntimeEventStatus.REJECTED
                rejected.status_reason = getattr(exc, "code", type(exc).__name__)
                graph.pending_runtime_event_ids = [
                    event_id
                    for event_id in graph.pending_runtime_event_ids
                    if event_id != event.event_id
                ]
                target = graph.get_node(rejected.target_node_id)
                if target.status == StepStatus.RETRYING:
                    target.error = rejected.status_reason
                    self.runtime.runtime_controller.transition_node_state(
                        target, StepStatus.FAILED
                    )
                self.runtime.trace_store.append(
                    run=candidate,
                    event_type=TraceEventType.GRAPH_PATCH_REJECTED,
                    step_id=rejected.runtime_node_id,
                    observation=str(exc),
                    payload=self._runtime_event_trace_payload(rejected)
                    | {
                        "proposalId": proposal.proposal_id if proposal else None,
                        "patchId": patch.patch_id if patch else None,
                        "recipeId": decision.recipe_id,
                        "baseGraphVersion": graph.graph_version,
                        "targetNodeId": rejected.target_node_id,
                        "errorCode": rejected.status_reason,
                    },
                )
                return candidate, None

    def _apply_next_ready_condition(self, candidate):
        """Evaluate and apply at most one ready IF patch inside the scheduler barrier."""

        graph = candidate.runtime_graph
        assert graph is not None
        for runtime_node in graph.nodes:
            if runtime_node.node_type.value != "control" or runtime_node.status != StepStatus.PENDING:
                continue
            control = ControlNode.model_validate(runtime_node.spec)
            if control.control_type != ControlType.IF:
                continue
            if graph.branch_decision_for(control.node_id) is not None:
                continue
            dependencies = graph.dependency_sources(control.node_id)
            if not dependencies or not all(
                graph.get_node(node_id).status == StepStatus.COMPLETED
                for node_id in dependencies
            ):
                continue
            assert control.condition_spec is not None and control.join_node_id is not None
            source = graph.get_node(control.condition_spec.source_node_id)
            if source.status != StepStatus.COMPLETED:
                continue
            evaluation = ConditionEvaluator().evaluate(
                control.condition_spec,
                source.output,
                graph,
                control_node_id=control.node_id,
                join_node_id=control.join_node_id,
                branch_edge_ids=control.branch_edge_ids,
            )
            proposal = self.runtime.proposal_factory.propose_conditional(evaluation, graph)
            self.runtime.trace_store.append(
                run=candidate,
                event_type=TraceEventType.GRAPH_CHANGE_PROPOSED,
                step_id=source.node_id,
                observation=f"Proposed conditional branch {proposal.proposal_id}",
                payload={
                    "proposalId": proposal.proposal_id,
                    "controlNodeId": control.node_id,
                    "sourceNodeId": source.node_id,
                    "selectedEdgeIds": evaluation.selected_edge_ids,
                    "terminatedEdgeIds": evaluation.terminated_edge_ids,
                    "baseGraphVersion": graph.graph_version,
                },
            )
            patch = self.runtime.patch_compiler.compile(proposal, graph)
            candidate, result = self.runtime.runtime_controller.apply_patch_to_candidate(
                candidate, patch
            )
            if result.applied:
                self.runtime.runtime_controller.create_patch_checkpoint(candidate, patch)
            return candidate, patch if result.applied else None
        return candidate, None

    @staticmethod
    def _runtime_event_trace_payload(event: RuntimeEvent) -> dict[str, Any]:
        return {
            "eventId": event.event_id,
            "runtimeNodeId": event.runtime_node_id,
            "targetNodeId": event.target_node_id,
            "attemptId": event.attempt_id,
            "bindingId": event.binding_id,
            "baseGraphVersion": event.graph_version,
            "reasonCode": event.reason_code,
        }

    def _select_batch(self, graph: RuntimeGraph, ready: list[RuntimeNode]) -> list[RuntimeNode]:
        selected: list[RuntimeNode] = []
        counts: dict[str, int] = {}
        blueprint = graph.to_blueprint()
        for node in ready:
            edges = blueprint.incoming(node.node_id, EdgeType.EXECUTION)
            key = edges[0].source_id if edges else f"step::{node.node_id}"
            limit = 1
            if edges:
                agent = blueprint.get_node(key)
                if isinstance(agent, AgentNode):
                    limit = max(1, agent.max_concurrency)
            if counts.get(key, 0) >= limit:
                continue
            selected.append(node)
            counts[key] = counts.get(key, 0) + 1
            if len(selected) >= self.max_parallelism:
                break
        return selected

    @staticmethod
    def _data_sources(graph: RuntimeGraph, node_id: str) -> list[str]:
        communication = [edge.source_id for edge in graph.effective_edges(EdgeType.COMMUNICATION) if edge.target_id == node_id]
        return list(dict.fromkeys(communication or graph.dependency_sources(node_id)))

    @staticmethod
    def _correlation(graph, node, attempt, *, scheduled: int) -> dict[str, Any]:
        binding = node.current_binding or {}
        return {"graphVersion": graph.graph_version, "runtimeNodeId": node.node_id,
                "attemptId": attempt.attempt_id, "bindingId": attempt.binding_id,
                "bindingSource": binding.get("source", "native"),
                "pluginId": binding.get("pluginId"),
                "pluginVersion": binding.get("pluginVersion"),
                "bindingContributionId": binding.get("contributionId"),
                "scheduledGraphVersion": scheduled, "attempt": attempt.attempt_number}

    @staticmethod
    def _exception_code(exc: Exception) -> str:
        return str(getattr(exc, "code", None) or type(exc).__name__)

    @staticmethod
    def _outcome(package, status, started_at, *, output=None, error=None, resolved=None,
                 events=None, provenance=None, recoverable=False, runtime_signals=None,
                 error_type="", error_code="", error_direction="") -> StepExecutionOutcome:
        return StepExecutionOutcome(
            runId=package.run_id, graphId=package.graph_id,
            scheduledGraphVersion=package.graph_version, runtimeNodeId=package.runtime_node_id,
            attemptId=package.attempt_id, status=status, output=output or {}, error=error,
            resolvedInput=resolved or {}, startedAt=started_at, endedAt=utc_now(),
            traceEvents=events or [], provenanceEvents=provenance or {}, recoverable=recoverable,
            runtimeSignals=runtime_signals or [], errorType=str(error_type or ""),
            errorCode=str(error_code or error_type or "UNKNOWN_ERROR"),
            errorDirection=error_direction,
        )

    def _late_outcome_trace(self, run, graph, node, outcome, reason: str) -> None:
        self.runtime.trace_store.append(
            run=run, event_type=TraceEventType.STEP_FAILED, step_id=node.node_id,
            observation=f"Ignored late execution outcome: {reason}",
            payload={"ignored": True, "reason": reason, "attemptId": outcome.attempt_id,
                     "graphVersion": graph.graph_version, "scheduledGraphVersion": outcome.scheduled_graph_version},
        )

    def _record_degraded_output(self, run, node, attempt, output: dict[str, Any]) -> None:
        llm = output.get("_llm")
        if not isinstance(llm, dict) or llm.get("success") is not False:
            return
        degraded = run.execution_state.setdefault("degradedSteps", [])
        marker = {"stepId": node.node_id, "attempt": attempt.attempt_number}
        if any(
            isinstance(item, dict)
            and item.get("stepId") == marker["stepId"]
            and item.get("attempt") == marker["attempt"]
            for item in degraded
        ):
            return
        detail = {
            **marker,
            "source": str(llm.get("source") or "fallback"),
            "error": str(llm.get("error") or "model output degraded")[:240],
        }
        degraded.append(detail)
        run.recovery_count += 1
        self.runtime.trace_store.append(
            run=run,
            event_type=TraceEventType.RUN_RECOVERED,
            step_id=node.node_id,
            agent_name=attempt.agent_name,
            observation=f"Step used a degraded fallback: {node.spec.get('name') or node.node_id}",
            payload=detail | self._correlation(run.runtime_graph, node, attempt, scheduled=attempt.graph_version),
        )

    def provenance_graph(self) -> dict:
        """Compatibility accessor; persisted provenance is scoped to each run."""

        return {}


__all__ = ["ACGExecutor"]
