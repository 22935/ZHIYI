"""Compile an ACG blueprint into one immutable, exhaustive execution package."""

from __future__ import annotations

from contracts import stable_checksum
from contracts.compiled_acg import (
    BindingManifest,
    BindingRule,
    CommunicationManifestSpec,
    CommunicationMode,
    CommunicationRuleSpec,
    CompiledACGPackage,
    CompiledEdge,
    CompiledNodeKind,
    CompiledNodeSpec,
    ConditionalControlSpec,
    ConsensusControlSpec,
    ControlManifest,
    ControlRule,
    EvidenceManifest,
    EvidenceRule,
    LoopControlSpec,
    MemoryManifest,
    MemoryRule,
    ParallelControlSpec,
    SkillManifest,
    SkillRule,
)
from components.communicator.manifest import CommunicationManifest, CommunicationRule
from components.executor.graph import ACGConditionalRoute, ACGExecutionGraph, ACGNodeSpec
from support.acg.schema import (
    ACGBlueprint,
    ControlNode,
    ControlType,
    EdgeType,
    NodeType,
    StepNode,
)
from support.acg.planning import (
    AgentBindingSpec,
    CommunicationSpec,
    EvidenceSpec,
    MemoryAccessSpec,
    SkillRequirementSpec,
)
from support.acg.validation import validate_blueprint


class UnsupportedCommunicationModeError(ValueError):
    """The blueprint requests a communication mode unavailable to this compiler."""


class IncompleteACGCompilationError(ValueError):
    """A declared ACG semantic cannot be represented by the compiled package."""


class ACGGraphCompiler:
    """The only Blueprint-to-runtime compilation boundary."""

    package_version = 4
    supported_communication_modes = {mode.value for mode in CommunicationMode}

    def compile_package(
        self,
        blueprint: ACGBlueprint,
        *,
        run_id: str | None = None,
    ) -> CompiledACGPackage:
        """Validate and lower every node and edge into immutable manifests."""
        validate_blueprint(blueprint)
        self._assert_enum_coverage()
        steps = {
            node.node_id: node
            for node in blueprint.step_nodes()
            if str(node.metadata.get("lifecycleStatus", "active")).lower() != "retired"
        }
        node_specs = tuple(
            CompiledNodeSpec(
                nodeId=node.node_id,
                kind=(
                    CompiledNodeKind.STEP
                    if isinstance(node, StepNode)
                    else CompiledNodeKind.CONTROL
                ),
                communicationMode=(
                    self._communication_mode(node)
                    if isinstance(node, StepNode)
                    else CommunicationMode.STRICT_CONTRACT
                ),
                reviewRequired=(node.review_required if isinstance(node, StepNode) else False),
                controlType=(node.control_type.value if isinstance(node, ControlNode) else None),
            )
            for node in blueprint.nodes
            if isinstance(node, (StepNode, ControlNode))
            and str(node.metadata.get("lifecycleStatus", "active")).lower() != "retired"
        )
        executable_ids = {node.node_id for node in node_specs}
        compiled_edges = tuple(
            CompiledEdge(
                edgeId=edge.edge_id,
                sourceId=edge.source_id,
                targetId=edge.target_id,
                edgeType=edge.edge_type.value,
            )
            for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY)
            if edge.source_id in executable_ids and edge.target_id in executable_ids
        )

        binding_manifest = self._compile_bindings(blueprint.resource_plan.bindings, steps)
        skill_manifest = self._compile_skills(blueprint.resource_plan.skills, steps)
        memory_manifest = self._compile_memory(blueprint.resource_plan.memory, steps)
        evidence_manifest = self._compile_evidence(blueprint.resource_plan.evidence, steps)
        communication_manifest = self._compile_communication(
            blueprint, blueprint.resource_plan.communication, steps, run_id=run_id
        )
        control_manifest = self._compile_controls(blueprint, node_specs)

        blueprint_payload = blueprint.model_dump(by_alias=True, mode="json")
        blueprint_hash = stable_checksum(blueprint_payload)
        package_payload = {
            "packageVersion": self.package_version,
            "runId": run_id,
            "blueprintId": blueprint.graph_id,
            "blueprintVersion": blueprint.version,
            "blueprintHash": blueprint_hash,
            "nodes": node_specs,
            "edges": compiled_edges,
            "controlManifest": control_manifest,
            "bindingManifest": binding_manifest,
            "skillManifest": skill_manifest,
            "memoryManifest": memory_manifest,
            "evidenceManifest": evidence_manifest,
            "communicationManifest": communication_manifest,
        }
        checksum = stable_checksum(package_payload)
        package = CompiledACGPackage(
            packageId=f"acgpkg:{blueprint.graph_id}:{blueprint.version}:{checksum[:16]}",
            checksum=checksum,
            **package_payload,
        )
        return package

    def compile(
        self,
        blueprint: ACGBlueprint,
        *,
        run_id: str | None = None,
        package: CompiledACGPackage | None = None,
    ) -> ACGExecutionGraph:
        """Build the runtime graph view exclusively from a compiled package."""
        compiled = package or self.compile_package(blueprint, run_id=run_id)
        if compiled.blueprint_id != blueprint.graph_id or compiled.blueprint_version != blueprint.version:
            raise IncompleteACGCompilationError("compiled package does not belong to blueprint")
        expected_hash = stable_checksum(blueprint.model_dump(by_alias=True, mode="json"))
        if compiled.blueprint_hash != expected_hash:
            raise IncompleteACGCompilationError("compiled package blueprint hash mismatch")

        controls = {rule.control_id: rule for rule in compiled.control_manifest.rules}
        node_specs: dict[str, ACGNodeSpec] = {}
        for node in compiled.nodes:
            control = controls.get(node.node_id)
            condition = None
            if control is not None and control.condition is not None:
                condition = ACGConditionalRoute(
                    source_step_id=control.condition.source_step_id,
                    json_pointer=control.condition.json_pointer,
                    operator=control.condition.operator,
                    targets_by_case=dict(control.condition.targets_by_case),
                    default_target=control.condition.default_target,
                    # The package's blueprint hash above authenticates this
                    # existing declaration. Keep it as local scheduling metadata;
                    # no persisted package/schema migration is introduced.
                    join_node_id=blueprint.get_node(node.node_id).join_node_id,
                )
            node_specs[node.node_id] = ACGNodeSpec(
                node_id=node.node_id,
                kind=node.kind.value,
                communication_mode=node.communication_mode.value,
                review_required=node.review_required,
                condition=condition,
                control_type=node.control_type,
            )
        dependency_edges = tuple(
            (edge.source_id, edge.target_id)
            for edge in compiled.edges
            if edge.edge_type == EdgeType.DEPENDENCY.value
        )
        return ACGExecutionGraph(
            nodes=tuple(node.node_id for node in compiled.nodes),
            edges=dependency_edges,
            node_specs=node_specs,
            communication_manifest=self._runtime_communication_manifest(
                compiled.communication_manifest
            ),
            compiled_package=compiled,
        )

    @staticmethod
    def _assert_enum_coverage() -> None:
        handled_nodes = {
            NodeType.STEP, NodeType.CONTROL,
        }
        handled_edges = {
            EdgeType.DEPENDENCY,
        }
        handled_controls = {
            ControlType.IF, ControlType.LOOP,
            ControlType.PARALLEL, ControlType.CONSENSUS,
        }
        if handled_nodes != set(NodeType) or handled_edges != set(EdgeType) or handled_controls != set(ControlType):
            raise IncompleteACGCompilationError("ACG enum contains an unhandled semantic")

    @staticmethod
    def _communication_mode(step: StepNode) -> CommunicationMode:
        raw = str(step.metadata.get("communicationMode", "STRICT_CONTRACT")).upper()
        try:
            mode = CommunicationMode(raw)
        except ValueError as exc:
            raise UnsupportedCommunicationModeError(f"unsupported communication mode: {raw}") from exc
        if mode is CommunicationMode.EVENT and isinstance(step.input_spec.get("from"), dict):
            raise ValueError(f"EVENT step {step.node_id} cannot declare inputSpec.from fields")
        return mode

    @staticmethod
    def _compile_bindings(bindings: tuple[AgentBindingSpec, ...], steps):
        explicit = {step_id: [] for step_id in steps}
        for binding in bindings:
            if binding.step_id in explicit:
                explicit[binding.step_id].append(binding)
        rules: list[BindingRule] = []
        for step_id, step in steps.items():
            agents = explicit[step_id]
            capabilities = {str(step.capability)} if step.capability else set()
            if not capabilities:
                for agent in agents:
                    capabilities.update(str(item) for item in agent.required_capabilities)
            if not capabilities:
                capabilities.add(
                    f"agent:{agents[0].planned_agent_id.lower()}" if len(agents) == 1 else "general"
                )
            rules.append(BindingRule(
                stepId=step_id,
                agentNodeIds=tuple(agent.planned_agent_id for agent in agents),
                requiredCapabilities=tuple(sorted(capabilities)),
                allowedResourceIds=(),
                maxConcurrency=min((agent.max_concurrency for agent in agents), default=1),
            ))
        return BindingManifest(rules=tuple(rules))

    @staticmethod
    def _compile_skills(skills: tuple[SkillRequirementSpec, ...], steps):
        rules: list[SkillRule] = []
        for spec in skills:
            if spec.step_id in steps:
                rules.append(SkillRule(
                    stepId=spec.step_id, skillNodeId=spec.skill_id,
                    toolName=spec.tool_name, version=spec.version,
                    inputSpec=spec.input_spec, outputSpec=spec.output_spec,
                ))
        return SkillManifest(rules=tuple(rules))

    @staticmethod
    def _compile_memory(memory: tuple[MemoryAccessSpec, ...], steps):
        rules: list[MemoryRule] = []
        for spec in memory:
            if spec.step_id in steps:
                rules.append(MemoryRule(
                    stepId=spec.step_id, memoryNodeId=spec.memory_id,
                    access=spec.access, memoryType=spec.memory_type,
                    storageType=spec.storage_type,
                    retentionPolicy=spec.retention_policy, schema=spec.schema_,
                ))
        return MemoryManifest(rules=tuple(rules))

    @staticmethod
    def _compile_evidence(evidence: tuple[EvidenceSpec, ...], steps):
        rules: list[EvidenceRule] = []
        for spec in evidence:
            if spec.producer_step_id in steps:
                rules.append(EvidenceRule(
                    stepId=spec.producer_step_id, evidenceNodeId=spec.evidence_id,
                    access="produce", evidenceType=spec.evidence_type,
                    source=spec.source, schema=spec.schema_,
                ))
            for consumer in spec.consumer_step_ids:
                if consumer in steps:
                    rules.append(EvidenceRule(
                        stepId=consumer, evidenceNodeId=spec.evidence_id,
                        access="consume", evidenceType=spec.evidence_type,
                        source=spec.source, schema=spec.schema_,
                    ))
        return EvidenceManifest(rules=tuple(rules))

    def _compile_communication(
        self,
        blueprint,
        communication: tuple[CommunicationSpec, ...],
        steps,
        *,
        run_id,
    ):
        metadata = blueprint.metadata if isinstance(blueprint.metadata, dict) else {}
        run_budget = self._budget(metadata.get("communicationBudget"), "communication budget")
        topology: dict[tuple[str, str], list[str] | None] = {
            (edge.source_id, edge.target_id): None
            for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY)
            if edge.source_id in steps and edge.target_id in steps
        }
        communication_by_pair = {
            (spec.producer_step_id, spec.consumer_step_id): spec
            for spec in communication
        }
        for pair, spec in communication_by_pair.items():
            topology[pair] = list(spec.allowed_fields)
        rules: list[CommunicationRuleSpec] = []
        step_budgets: dict[str, int] = {}
        channel_budgets: dict[str, int] = {}
        incoming_sources: dict[str, tuple[str, ...]] = {}
        for source_id, target_id in topology:
            incoming_sources.setdefault(target_id, tuple())
            incoming_sources[target_id] = tuple(dict.fromkeys(
                (*incoming_sources[target_id], source_id)
            ))
        for (source_id, target_id), edge_fields in topology.items():
            source, target = steps[source_id], steps[target_id]
            from_map = target.input_spec.get("from") if isinstance(target.input_spec, dict) else None
            declared = edge_fields or (
                from_map.get(source_id, []) if isinstance(from_map, dict) else []
            )
            if not isinstance(declared, list):
                raise ValueError(f"communication fields for {source_id}->{target_id} must be a list")
            if not declared:
                properties = source.output_spec.get("properties", {}) if isinstance(source.output_spec, dict) else {}
                declared = list(properties) if isinstance(properties, dict) else []
            target_metadata = target.metadata if isinstance(target.metadata, dict) else {}
            explicit_step_budget = self._budget(
                target_metadata.get("communicationBudget"),
                f"communication budget for {target_id}",
            )
            planned = communication_by_pair.get((source_id, target_id))
            max_tokens = planned.max_tokens if planned and planned.max_tokens is not None else explicit_step_budget
            channel = planned.channel if planned is not None else f"{source_id}:{target_id}"
            mode = self._communication_mode(target)
            if planned is not None:
                try:
                    mode = CommunicationMode(planned.mode)
                except ValueError as exc:
                    raise UnsupportedCommunicationModeError(
                        f"unsupported communication mode: {planned.mode}"
                    ) from exc
            participants: tuple[str, ...] = ()
            max_rounds = None
            quorum = None
            if planned is not None:
                participants = tuple(planned.participant_step_ids)
                max_rounds = planned.max_rounds
                quorum = planned.quorum
            if mode is CommunicationMode.DEBATE:
                raw_participants = target_metadata.get("debateParticipants")
                if raw_participants is None:
                    raw_participants = incoming_sources.get(target_id, ())
                if not isinstance(raw_participants, (list, tuple)):
                    raise ValueError(f"DEBATE step {target_id} participants must be a list")
                participants = tuple(dict.fromkeys(str(item) for item in raw_participants if str(item)))
                try:
                    max_rounds = int(target_metadata["debateMaxRounds"])
                    quorum = int(target_metadata["debateQuorum"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"DEBATE step {target_id} requires debateMaxRounds and debateQuorum"
                    ) from exc
            rules.append(CommunicationRuleSpec(
                producerStepId=source_id, consumerStepId=target_id,
                mode=mode, allowedFields=tuple(str(item) for item in declared),
                channel=channel, maxTokens=max_tokens,
                schemaHash=(planned.schema_hash if planned and planned.schema_hash else stable_checksum(source.output_spec)),
                backlogLimit=(planned.backlog_limit if planned else int(target_metadata.get("communicationBacklogLimit", 1000))),
                partition=(planned.partition if planned else (str(target_metadata["blackboardPartition"]) if target_metadata.get("blackboardPartition") else None)),
                maxRounds=max_rounds,
                quorum=quorum,
                participantStepIds=participants,
            ))
            # 显式预算是该节点跨所有入站通道的总上限；未显式配置时，每条已冻结
            # 通道取得一个默认额度，节点总上限由这些通道额度之和推导。否则多源
            # fan-in 会在第二条合法通道上把“单通道默认值”误当成“节点总预算”。
            if explicit_step_budget is not None:
                step_budgets[target_id] = explicit_step_budget
                channel_budgets[channel] = explicit_step_budget
        return CommunicationManifestSpec(
            runId=run_id, rules=tuple(rules), runBudget=run_budget,
            stepBudgets=step_budgets, channelBudgets=channel_budgets,
        )

    @staticmethod
    def _budget(value, label):
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(f"{label} must be a non-negative integer")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a non-negative integer") from exc
        if result < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return result

    def _compile_controls(self, blueprint, node_specs):
        executable = {node.node_id for node in node_specs}
        dependencies = [
            edge for edge in blueprint.edges_of_type(EdgeType.DEPENDENCY)
            if edge.source_id in executable and edge.target_id in executable
        ]
        predecessors = {node_id: set() for node_id in executable}
        successors = {node_id: set() for node_id in executable}
        for edge in dependencies:
            predecessors[edge.target_id].add(edge.source_id)
            successors[edge.source_id].add(edge.target_id)
        controls = [
            node for node in blueprint.nodes
            if isinstance(node, ControlNode)
            and str(node.metadata.get("lifecycleStatus", "active")).lower() != "retired"
        ]
        entry_ids = tuple(sorted(node_id for node_id in executable if not predecessors[node_id]))
        exit_ids = tuple(sorted(node_id for node_id in executable if not successors[node_id]))
        rules: list[ControlRule] = []
        for control in controls:
            condition = self._compiled_condition(blueprint, control)
            loop = None
            parallel = None
            consensus = None
            if control.control_type is ControlType.LOOP:
                if control.loop_spec is None:
                    raise IncompleteACGCompilationError(f"LOOP {control.node_id} requires loopSpec")
                loop = LoopControlSpec(
                    bodyEntryId=control.loop_spec.body_entry_id,
                    bodyExitId=control.loop_spec.body_exit_id,
                    condition=self._condition_from_spec(blueprint, control.loop_spec.condition),
                    maxIterations=control.loop_spec.max_iterations,
                    onLimit=control.loop_spec.on_limit,
                )
            elif control.control_type is ControlType.PARALLEL:
                spec = control.parallel_spec
                if spec is None:
                    raise IncompleteACGCompilationError(f"PARALLEL {control.node_id} requires parallelSpec")
                parallel = ParallelControlSpec(
                    branchEntryIds=tuple(spec.branch_entry_ids), joinNodeId=spec.join_node_id
                )
            elif control.control_type is ControlType.CONSENSUS:
                spec = control.consensus_spec
                if spec is not None:
                    consensus = ConsensusControlSpec(
                        participantStepIds=tuple(spec.participant_step_ids), quorum=spec.quorum,
                        strategy=spec.strategy, timeoutSeconds=spec.timeout_seconds,
                        onUnresolved=spec.on_unresolved,
                    )
            rules.append(ControlRule(
                controlId=control.node_id, controlType=control.control_type.value,
                condition=condition, loop=loop, parallel=parallel, consensus=consensus,
            ))
        return ControlManifest(entryNodeIds=entry_ids, exitNodeIds=exit_ids, rules=tuple(rules))

    def _compiled_condition(self, blueprint, control):
        if control.control_type is not ControlType.IF:
            return None
        if control.condition_spec is None:
            raise IncompleteACGCompilationError(f"IF {control.node_id} requires conditionSpec")
        return self._condition_from_spec(blueprint, control.condition_spec)

    @staticmethod
    def _condition_from_spec(blueprint, spec):
        edges = {edge.edge_id: edge for edge in blueprint.edges}
        try:
            targets = {case: edges[edge_id].target_id for case, edge_id in spec.cases.items()}
            default = edges[spec.default_edge_id].target_id if spec.default_edge_id else None
        except KeyError as exc:
            raise IncompleteACGCompilationError("control condition references an unknown edge") from exc
        return ConditionalControlSpec(
            sourceStepId=spec.source_node_id, jsonPointer=spec.json_pointer,
            operator=spec.operator.value, targetsByCase=targets, defaultTarget=default,
        )

    @staticmethod
    def _runtime_communication_manifest(spec):
        if not spec.run_id:
            return None
        return CommunicationManifest(
            run_id=spec.run_id,
            rules=tuple(CommunicationRule(
                producer_step_id=rule.producer_step_id,
                consumer_step_id=rule.consumer_step_id,
                allowed_fields=tuple(rule.allowed_fields),
                channel=rule.channel,
                max_tokens=rule.max_tokens,
            ) for rule in spec.rules),
            run_budget=spec.run_budget,
            step_budgets=spec.step_budgets,
            channel_budgets=spec.channel_budgets,
        )


__all__ = [
    "ACGGraphCompiler", "IncompleteACGCompilationError", "UnsupportedCommunicationModeError",
]
