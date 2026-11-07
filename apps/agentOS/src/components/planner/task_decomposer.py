"""Versioned semantic task decomposition without introducing another runtime."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from collections.abc import Mapping
from typing import Any, Callable
from adapters.prompt_runtime import planner_prompt_metadata, schema_hash, serialize_planning_request

from contracts.planning import (
    PlannedTask,
    SemanticTaskRelationType,
    TaskPlan,
    TaskPlanRelation,
    VerificationLoopPolicy,
    WorksetSpec,
)
from contracts.artifacts import (
    FINAL_SYNTHESIS_LOGICAL_ROLE,
    FINAL_SYNTHESIS_ROLES,
    canonicalize_final_synthesis_nodes,
)
from components.planner.topology import (
    REPAIR_PATCH_SCHEMA, EdgeOrigin, TaskPlanTopologyCompiler, TopologyCompileError,
    apply_repair_patch, conflict_context, is_model_repair_eligible,
    validate_task_plan_for_execution,
    failed_topology_audit, successful_topology_audit,
)
from support.acg.capabilities import CapabilityCatalog
from support.acg.semantic_profile import TaskSemanticProfile

from .complexity import (
    PLANNING_BUDGETS, PLANNING_MODEL_TIMEOUT_SECONDS, call_planning_model,
    transport_error_code,
)
from .intent_analyzer import IntentLLM


TASK_DECOMPOSITION_PROMPT_VERSION = "task-decomposition.v8"
INITIAL_DAG_CONTRACT = (
    "INITIAL DAG CONTRACT: this Run's formal initial graph materializer accepts a DAG only. "
    "controlPolicies MUST be []. Do not create verification_loop, backward edges or control nodes. "
    "Preserve all requested checks, correction requirements and acceptance criteria. "
    "Represent a bounded check/correction/recheck sequence as distinct forward-dependent tasks, "
    "with explicit limits and a final unresolved-issues report when checks still fail. "
    "Never silently remove a user requirement or claim an unbounded loop is supported."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "parentKey": {"type": ["string", "null"]},
                    "title": {"type": "string"},
                    "objective": {"type": "string"},
                    "capabilityId": {"type": "string"},
                    "constraints": {"type": "array", "items": {"type": "object"}},
                    "acceptanceCriteria": {"type": "array", "items": {"type": "string"}},
                    "sourceRefs": {"type": "array", "items": {"type": "string"}},
                    "decompositionRationale": {"type": "string"},
                    "logicalRole": {"type": "string"},
                    "workset": {
                        "type": ["object", "null"],
                        "properties": {
                            "sourceManifestRefs": {"type": "array", "items": {"type": "string"}, "description": "Only existing material_manifest refs from planningRequest.sourceRegistry. Never constraint refs, expected_artifact refs, task keys or future outputs. Omit workset when no registered material exists."},
                            "unitKind": {"type": "string", "enum": ["chunk", "section", "item"]},
                            "cursorStrategy": {"type": "string"},
                            "packingPolicy": {"type": "string", "enum": ["api_capacity"]},
                            "parallelismPolicy": {"type": "string"},
                            "estimatedUnitCount": {"type": ["integer", "null"]},
                        },
                        "required": ["sourceManifestRefs"],
                    },
                },
                "required": [
                    "key", "title", "objective", "capabilityId",
                    "acceptanceCriteria", "sourceRefs", "decompositionRationale",
                ],
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sourceKey": {
                        "type": "string",
                        "description": "For depends_on, the prerequisite task executed first.",
                    },
                    "targetKey": {
                        "type": "string",
                        "description": "For depends_on, the dependent task executed afterward.",
                    },
                    "relationType": {"type": "string", "enum": ["depends_on", "parent"]},
                },
                "required": ["sourceKey", "targetKey", "relationType"],
            },
        },
        "controlPolicies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["verification_loop"]},
                    "bodyEntryKey": {"type": "string"},
                    "bodyExitKey": {"type": "string"},
                    "conditionSourceKey": {"type": "string"},
                    "statusPointer": {"type": "string"},
                    "repeatValues": {"type": "array", "items": {"type": "string"}},
                    "maxRevisions": {"type": "integer", "minimum": 0, "maximum": 8},
                    "onExhausted": {"type": "string", "enum": ["human_review", "fail"]},
                },
                "required": [
                    "type", "bodyEntryKey", "bodyExitKey", "conditionSourceKey",
                    "statusPointer", "repeatValues", "maxRevisions", "onExhausted",
                ],
            },
        },
        "budgetRationale": {"type": "string"},
    },
    "required": ["tasks", "relations"],
}


class TaskDecompositionError(ValueError):
    def __init__(self, message: str, *, cause_code: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.cause_code = cause_code
        self.metadata = dict(metadata or {})


class TaskDecomposer:
    def __init__(
        self,
        capability_catalog: CapabilityCatalog,
        llm: IntentLLM | None,
        model_timeout_seconds: float | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.capability_catalog = capability_catalog
        self.llm = llm
        self.model_timeout_seconds = float(
            model_timeout_seconds or PLANNING_MODEL_TIMEOUT_SECONDS
        )
        if self.model_timeout_seconds <= 0:
            raise ValueError("model_timeout_seconds must be positive")
        self.last_audit: dict[str, Any] = {}
        self.progress_callback = progress_callback

    def _publish_draft(
        self,
        *,
        stage: str,
        outline: list[dict[str, Any]],
        detailed_tasks: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
    ) -> None:
        """Publish a bounded, validated semantic graph preview, never hidden reasoning."""
        if not self.progress_callback:
            return
        detailed_by_key = {
            str(item.get("key") or ""): item
            for item in (detailed_tasks or [])
            if isinstance(item, dict)
        }
        nodes = []
        for item in outline[:100]:
            key = str(item.get("key") or "")
            detail = detailed_by_key.get(key)
            nodes.append({
                "key": key,
                "title": str(item.get("title") or key)[:200],
                "capabilityId": str(item.get("capabilityId") or "")[:120],
                "status": "detailed" if detail is not None else "outlined",
                # decompositionRationale is an explicit answer field, not the
                # provider's private chain-of-thought.
                "rationale": str((detail or {}).get("decompositionRationale") or "")[:500],
            })
        safe_edges = [
            {
                "sourceKey": str(item.get("sourceKey") or "")[:160],
                "targetKey": str(item.get("targetKey") or "")[:160],
                "relationType": str(item.get("relationType") or "depends_on")[:40],
            }
            for item in (relations or [])[:300]
            if isinstance(item, dict)
        ]
        self.progress_callback({
            "eventType": "planner.draft.updated",
            "stage": stage,
            "nodes": nodes,
            "edges": safe_edges,
            "persistTrace": False,
        })

    def _call_llm(
        self,
        *,
        stage: str,
        prompt: str,
        schema: dict,
        call_key: str | None = None,
        planning_deadline: float | None = None,
        run_id: str | None = None,
        **kwargs,
    ) -> Any:
        """带超时预算声明的模型调用：单点超时自动重试一次并留审计。

        瞬态读超时不应判死整条规划链（2026-09-01 run_1a25f0d4ad89 根因），
        但也不得无限放大延迟：同一调用点最多两次尝试，持续超时按既有失败
        路径上抛。
        """
        return call_planning_model(
            self.llm, stage=stage, prompt=prompt, schema=schema,
            audit=self.last_audit, model_timeout_seconds=self.model_timeout_seconds,
            progress_callback=self.progress_callback, call_key=call_key,
            planning_deadline=planning_deadline, run_id=run_id, **kwargs,
        )

    def decompose(
        self,
        *,
        mission_id: str,
        profile: TaskSemanticProfile,
        strategy: str,
        task_input: Mapping[str, Any] | None,
        use_llm: bool,
        reasoning_effort: str | None = None,
        existing_semantic_tasks: tuple[Mapping[str, Any], ...] = (),
        planning_deadline: float | None = None,
        run_id: str | None = None,
    ) -> TaskPlan:
        planning_schema = deepcopy(_SCHEMA)
        if strategy == "initial_commit_candidate":
            planning_schema["properties"]["controlPolicies"]["maxItems"] = 0
        self.last_audit = {
            "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION,
            **planner_prompt_metadata(),
            "schemaHash": schema_hash(planning_schema),
            "modelId": str(getattr(self.llm, "model", None) or "unreported"),
            "modelVersion": str(getattr(self.llm, "version", None) or "unreported"),
            "mode": "model" if use_llm and self.llm is not None else "deterministic",
        }
        if use_llm and self.llm is not None:
            prompt = self.build_prompt(
                profile=profile,
                task_input=task_input,
                existing_semantic_tasks=existing_semantic_tasks,
            )
            if strategy == "initial_commit_candidate":
                prompt += "\n" + INITIAL_DAG_CONTRACT
            if (task_input or {}).get("_effectiveCapabilityProfile") == "full":
                return self._decompose_staged(
                    mission_id=mission_id,
                    profile=profile,
                    strategy=strategy,
                    task_input=task_input,
                    existing_semantic_tasks=existing_semantic_tasks,
                    prompt=prompt,
                    reasoning_effort=reasoning_effort,
                    planning_deadline=planning_deadline,
                    run_id=run_id,
                )
            first: Any = None
            try:
                first = self._call_llm(
                    stage="decompose",
                    prompt=prompt,
                    schema=planning_schema,
                    reasoning_effort=reasoning_effort,
                    prompt_version=TASK_DECOMPOSITION_PROMPT_VERSION,
                    call_key="decompose",
                    planning_deadline=planning_deadline,
                    run_id=run_id,
                )
                self._capture_model_audit(first)
                return self._to_plan(
                    mission_id,
                    profile,
                    strategy,
                    first,
                    task_input=task_input,
                    existing_semantic_tasks=existing_semantic_tasks,
                )
            except Exception as first_error:
                if transport_error_code(first_error):
                    self.last_audit["mode"] = "failed"
                    self.last_audit["error"] = type(first_error).__name__
                    raise TaskDecompositionError(
                        f"TASK_PLAN_TRANSPORT_FAILED: {transport_error_code(first_error)}",
                        cause_code=transport_error_code(first_error),
                        metadata=dict(self.last_audit.get("lastTransportError") or {}),
                    ) from first_error
                try:
                    missing_refs = self._coverage_gap_refs(first_error)
                    if isinstance(first_error, TopologyCompileError):
                        if not is_model_repair_eligible(first_error.conflict) or first is None:
                            raise
                        raw = deepcopy(first.get("data", first))
                        structured_conflict = conflict_context(first_error.conflict)
                        repair_patch = self._call_llm(
                            stage="relations.repair",
                            prompt=(
                                "Patch only the model relation/control proposal using this compiler conflict.\n"
                                + f"Frozen Tasks: {json.dumps(raw.get('tasks', []), ensure_ascii=False)}\n"
                                + f"Current model relations: {json.dumps(raw.get('relations', []), ensure_ascii=False)}\n"
                                + f"Current control policies: {json.dumps(raw.get('controlPolicies', []), ensure_ascii=False)}\n"
                                + f"Structured conflict: {json.dumps(structured_conflict, ensure_ascii=False)}\n"
                                + "Return patch operations only. Never change frozen tasks, capability requirements, "
                                + "source identities, or catalog edges. Use originalRelationIndex."
                            ),
                            schema=REPAIR_PATCH_SCHEMA, reasoning_effort=reasoning_effort,
                            prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.relations.cycle-repair1",
                            call_key="relations.cycle-repair", planning_deadline=planning_deadline,
                            run_id=run_id,
                        )
                        patch_payload = repair_patch.get("data", repair_patch)
                        relations, policies = apply_repair_patch(
                            relations=list(raw.get("relations", [])),
                            control_policies=list(raw.get("controlPolicies", [])),
                            patch=patch_payload,
                            task_keys={str(item.get("key")) for item in raw.get("tasks", [])},
                        )
                        raw["relations"] = relations
                        raw["controlPolicies"] = policies
                        self.last_audit["topology"] = {
                            "compile1Conflict": structured_conflict, "repairPatch": patch_payload,
                            "repairAttempts": 1,
                        }
                        repaired = raw
                        repair_version = f"{TASK_DECOMPOSITION_PROMPT_VERSION}.relations.cycle-repair1"
                    elif missing_refs and first is not None:
                        repaired = self._repair_source_ref_coverage(
                            raw=first,
                            profile=profile,
                            missing_refs=missing_refs,
                            reasoning_effort=reasoning_effort,
                            planning_deadline=planning_deadline,
                            run_id=run_id,
                        )
                        repair_version = f"{TASK_DECOMPOSITION_PROMPT_VERSION}.repair1.coverage"
                    else:
                        invalid_plan = json.dumps(first, ensure_ascii=False, default=str)
                        repaired = self._call_llm(
                            stage="repair",
                            prompt=prompt
                            + "\nThe previous result failed TaskPlan schema validation. "
                            + "Repair it once and return the complete JSON again. "
                            + f"Validation detail: {first_error}\n"
                            + f"Previous invalid TaskPlan JSON: {invalid_plan}",
                            schema=planning_schema,
                            reasoning_effort=reasoning_effort,
                            prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.repair1",
                            call_key="repair",
                            planning_deadline=planning_deadline,
                            run_id=run_id,
                        )
                        repair_version = f"{TASK_DECOMPOSITION_PROMPT_VERSION}.repair1"
                    self.last_audit["promptVersion"] = repair_version
                    self._capture_model_audit(repaired)
                    return self._to_plan(
                        mission_id,
                        profile,
                        strategy,
                        repaired,
                        task_input=task_input,
                        existing_semantic_tasks=existing_semantic_tasks,
                    )
                except Exception as repair_error:
                    self.last_audit["mode"] = "failed"
                    self.last_audit["error"] = type(repair_error).__name__
                    raise TaskDecompositionError(
                        "TASK_PLAN_VALIDATION_FAILED after one repair: "
                        f"{repair_error}",
                        metadata={
                            **({"topologyCompilation": self.last_audit["topologyCompilation"]}
                               if "topologyCompilation" in self.last_audit else {}),
                            "repairAttempts": 1,
                        },
                    ) from repair_error
        return self._fallback(
            mission_id=mission_id,
            profile=profile,
            strategy=strategy,
            reason="model decomposition disabled or unavailable",
            existing_semantic_tasks=existing_semantic_tasks,
            task_input=task_input,
        )

    def _decompose_staged(
        self,
        *,
        mission_id: str,
        profile: TaskSemanticProfile,
        strategy: str,
        task_input: Mapping[str, Any] | None,
        existing_semantic_tasks: tuple[Mapping[str, Any], ...],
        prompt: str,
        reasoning_effort: str | None,
        planning_deadline: float | None,
        run_id: str | None,
    ) -> TaskPlan:
        """Build a large TaskPlan through bounded JSON units.

        Stable semantic keys are fixed by the outline. Detail failures retry only
        their five-task batch and relation failures retry only the relation unit.
        """
        task_item_schema = deepcopy(_SCHEMA["properties"]["tasks"]["items"])
        outline_schema = {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "title": {"type": "string"},
                            "capabilityId": {"type": "string"},
                            "logicalRole": {"type": "string"},
                            "sourceRefs": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["key", "title", "capabilityId", "logicalRole", "sourceRefs"],
                    },
                }
            },
            "required": ["tasks"],
        }
        self.last_audit.update({"mode": "model_staged", "stages": []})
        try:
            outline_prompt = prompt + "\nSTAGE OUTLINE: return only stable task identities, titles, primary capabilities, roles and sourceRefs. Do not return relations or verbose objectives."
            outline_result = self._call_llm(
                stage="outline",
                prompt=outline_prompt,
                schema=outline_schema,
                reasoning_effort=reasoning_effort,
                prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.outline",
                call_key="outline",
                planning_deadline=planning_deadline,
                run_id=run_id,
            )
            try:
                outline, keys = self._validated_outline_tasks(outline_result)
            except TaskDecompositionError as outline_error:
                outline_result = self._call_llm(
                    stage="outline.repair",
                    prompt=(
                        outline_prompt
                        + "\nRepair the outline once. It must contain at least one task and every task "
                        + "must have a unique non-empty key. Return the complete outline JSON again. "
                        + f"Validation detail: {outline_error}\n"
                        + f"Previous invalid outline JSON: {json.dumps(outline_result, ensure_ascii=False, default=str)}"
                    ),
                    schema=outline_schema,
                    reasoning_effort=reasoning_effort,
                    prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.outline.repair1",
                    call_key="outline.repair",
                    planning_deadline=planning_deadline,
                    run_id=run_id,
                )
                outline, keys = self._validated_outline_tasks(outline_result)
            self.last_audit["stages"].append({"stage": "outline", "taskCount": len(keys)})
            self._publish_draft(stage="outline", outline=outline)

            detailed_tasks: list[dict[str, Any]] = []
            for offset in range(0, len(outline), 5):
                batch = outline[offset:offset + 5]
                detail_index = offset // 5 + 1
                batch_keys = [str(item["key"]) for item in batch]
                detail_schema = {
                    "type": "object",
                    "properties": {
                        "tasks": {
                            "type": "array",
                            "minItems": len(batch),
                            "maxItems": len(batch),
                            "items": task_item_schema,
                        }
                    },
                    "required": ["tasks"],
                }
                detail_prompt = (
                    "STAGE DETAIL: expand exactly this outline batch into complete TaskPlan task objects. "
                    "Preserve every key and capabilityId exactly; return no other tasks and no relations. "
                    "Every task needs a business objective, acceptance criteria, source refs and rationale.\n"
                    f"Mission planning context: {prompt}\n"
                    f"Frozen outline batch: {json.dumps(batch, ensure_ascii=False)}"
                )
                detail_repaired = False
                try:
                    detail_result = self._call_llm(
                        stage="detail",
                        prompt=detail_prompt,
                        schema=detail_schema,
                        reasoning_effort=reasoning_effort,
                        prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.detail",
                        call_key=f"detail:{detail_index}",
                        planning_deadline=planning_deadline,
                        run_id=run_id,
                    )
                except Exception as exc:
                    if transport_error_code(exc):
                        raise
                    detail_repaired = True
                    detail_result = self._call_llm(
                        stage="detail.repair",
                        prompt=detail_prompt + f"\nRepair this batch once. Previous error: {exc}",
                        schema=detail_schema,
                        reasoning_effort=reasoning_effort,
                        prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.detail.repair1",
                        call_key=f"detail:{detail_index}.repair",
                        planning_deadline=planning_deadline,
                        run_id=run_id,
                    )
                try:
                    normalized_rows = self._validated_detail_tasks(detail_result, batch)
                    self._validate_workset_sources(normalized_rows, task_input)
                except TaskDecompositionError as detail_error:
                    if detail_repaired:
                        raise
                    detail_result = self._call_llm(
                        stage="detail.repair",
                        prompt=(
                            detail_prompt
                            + "\nRepair this batch once. Every task must preserve its frozen identity and "
                            + "include a non-empty business objective and acceptance criteria. "
                            + f"Validation detail: {detail_error}\n"
                            + f"Previous invalid detail JSON: {json.dumps(detail_result, ensure_ascii=False, default=str)}"
                        ),
                        schema=detail_schema,
                        reasoning_effort=reasoning_effort,
                        prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.detail.repair1",
                        call_key=f"detail:{detail_index}.repair",
                        planning_deadline=planning_deadline,
                        run_id=run_id,
                    )
                    normalized_rows = self._validated_detail_tasks(detail_result, batch)
                    self._validate_workset_sources(normalized_rows, task_input)
                detailed_tasks.extend(normalized_rows)
                self.last_audit["stages"].append({"stage": "detail", "keys": batch_keys})
                self._publish_draft(
                    stage="detail",
                    outline=outline,
                    detailed_tasks=detailed_tasks,
                )

            relation_schema = {
                "type": "object",
                "properties": {
                    "relations": deepcopy(_SCHEMA["properties"]["relations"]),
                    "controlPolicies": deepcopy(_SCHEMA["properties"]["controlPolicies"]),
                },
                "required": ["relations", "controlPolicies"],
            }
            if strategy == "initial_commit_candidate":
                relation_schema["properties"]["controlPolicies"]["maxItems"] = 0
            compact = [
                {
                    "key": item["key"],
                    "capabilityId": item["capabilityId"],
                    "logicalRole": item.get("logicalRole", "task"),
                    "objective": item.get("objective", ""),
                }
                for item in detailed_tasks
            ]
            relation_prompt = (
                "STAGE RELATIONS: create the acyclic prerequisite-to-dependent topology for these frozen tasks. "
                + (INITIAL_DAG_CONTRACT + "\n" if strategy == "initial_commit_candidate" else
                   "Add a verification_loop only when a refinement-to-verification region is present; use maxRevisions=2.\n")
                + f"Tasks: {json.dumps(compact, ensure_ascii=False)}"
            )
            try:
                relation_result = self._call_llm(
                    stage="relations",
                    prompt=relation_prompt,
                    schema=relation_schema,
                    reasoning_effort=reasoning_effort,
                    prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.relations",
                    call_key="relations",
                    planning_deadline=planning_deadline,
                    run_id=run_id,
                )
            except Exception as exc:
                if transport_error_code(exc):
                    raise
                relation_result = self._call_llm(
                    stage="relations.repair",
                    prompt=relation_prompt + f"\nRepair the relation unit once. Previous error: {exc}",
                    schema=relation_schema,
                    reasoning_effort=reasoning_effort,
                    prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.relations.repair1",
                    call_key="relations.repair",
                    planning_deadline=planning_deadline,
                    run_id=run_id,
                )
            relation_payload = relation_result.get("data", relation_result)
            combined = {
                "tasks": detailed_tasks,
                "relations": relation_payload.get("relations", []),
                "controlPolicies": relation_payload.get("controlPolicies", []),
            }
            self.last_audit["stages"].append({"stage": "relations"})
            try:
                plan = self._to_plan(
                    mission_id, profile, strategy, combined,
                    task_input=task_input,
                    existing_semantic_tasks=existing_semantic_tasks,
                )
            except Exception as exc:
                missing_refs = self._coverage_gap_refs(exc)
                if strategy == "initial_commit_candidate" and str(exc).startswith("INITIAL_CONTROL_GRAPH_UNSUPPORTED"):
                    repaired = self._call_llm(
                        stage="relations.repair",
                        prompt=relation_prompt + "\nRepair only this relation unit once. Keep frozen tasks unchanged. "
                            + f"Validation detail: {exc}\nPrevious relations: {json.dumps(relation_payload, ensure_ascii=False)}",
                        schema=relation_schema, reasoning_effort=reasoning_effort,
                        prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.relations.initial-dag-repair1",
                        call_key="relations.initial-dag-repair", planning_deadline=planning_deadline, run_id=run_id)
                    relation_payload = repaired.get("data", repaired)
                    combined = {"tasks": detailed_tasks, "relations": relation_payload.get("relations", []),
                                "controlPolicies": relation_payload.get("controlPolicies", [])}
                elif missing_refs:
                    combined = self._repair_source_ref_coverage(
                        raw=combined,
                        profile=profile,
                        missing_refs=missing_refs,
                        reasoning_effort=reasoning_effort,
                        planning_deadline=planning_deadline,
                        run_id=run_id,
                    )
                elif isinstance(exc, TopologyCompileError) and is_model_repair_eligible(exc.conflict):
                    structured_conflict = conflict_context(exc.conflict)
                    repair_patch = self._call_llm(
                        stage="relations.repair",
                        prompt=(
                            "Patch the model relation/control proposal using the complete compiler conflict.\n"
                            + f"Frozen Tasks: {json.dumps(compact, ensure_ascii=False)}\n"
                            + f"Current model relations: {json.dumps(combined['relations'], ensure_ascii=False)}\n"
                            + f"Current control policies: {json.dumps(combined['controlPolicies'], ensure_ascii=False)}\n"
                            + f"Structured conflict: {json.dumps(structured_conflict, ensure_ascii=False)}\n"
                            + "Return patch operations only. You may change model relations and controlPolicies. "
                            + "Never remove a capability requirement/catalog edge, change frozen task keys or "
                            + "capabilities, or change source/material identities. Use originalRelationIndex to "
                            + "remove or replace model relations. Express feedback with add_verification_loop."
                        ),
                        schema=REPAIR_PATCH_SCHEMA,
                        reasoning_effort=reasoning_effort,
                        prompt_version=f"{TASK_DECOMPOSITION_PROMPT_VERSION}.relations.cycle-repair1",
                        call_key="relations.cycle-repair",
                        planning_deadline=planning_deadline,
                        run_id=run_id,
                    )
                    patch_payload = repair_patch.get("data", repair_patch)
                    patched_relations, patched_policies = apply_repair_patch(
                        relations=list(combined["relations"]),
                        control_policies=list(combined["controlPolicies"]),
                        patch=patch_payload,
                        task_keys={str(item["key"]) for item in detailed_tasks},
                    )
                    combined = {
                        "tasks": detailed_tasks,
                        "relations": patched_relations,
                        "controlPolicies": patched_policies,
                    }
                    relation_payload = combined
                    self.last_audit["topology"] = {
                        "compile1Conflict": structured_conflict,
                        "repairPatch": patch_payload,
                        "repairAttempts": 1,
                    }
                    self.last_audit["stages"].append(
                        {"stage": "relations.cycle-repair"}
                    )
                else:
                    raise
                plan = self._to_plan(
                    mission_id, profile, strategy, combined,
                    task_input=task_input,
                    existing_semantic_tasks=existing_semantic_tasks,
                )
                if "topology" in self.last_audit:
                    self.last_audit["topology"]["compile2Result"] = "valid"
            self._publish_draft(
                stage="relations",
                outline=outline,
                detailed_tasks=detailed_tasks,
                relations=list(relation_payload.get("relations", [])),
            )
            self._capture_model_audit(outline_result)
            return plan
        except Exception as exc:
            self.last_audit["mode"] = "failed"
            self.last_audit["error"] = type(exc).__name__
            if isinstance(exc, TopologyCompileError):
                self.last_audit["topology"] = {
                    **dict(self.last_audit.get("topology") or {}),
                    "finalConflict": conflict_context(exc.conflict),
                    "repairAttempts": int(
                        (self.last_audit.get("topology") or {}).get("repairAttempts", 0)
                    ),
                }
            cause_code = transport_error_code(exc)
            raise TaskDecompositionError(
                f"TASK_PLAN_STAGED_FAILED: {exc}",
                cause_code=cause_code,
                metadata={
                    **dict(self.last_audit.get("lastTransportError") or {}),
                    **({"topology": self.last_audit["topology"]} if "topology" in self.last_audit else {}),
                    **({"topologyCompilation": self.last_audit["topologyCompilation"]}
                       if "topologyCompilation" in self.last_audit else {}),
                },
            ) from exc

    @staticmethod
    def _coverage_gap_refs(error: Exception) -> tuple[str, ...]:
        prefix = "TaskPlan coverage gap for source refs:"
        detail = str(error)
        if not isinstance(error, TaskDecompositionError) or not detail.startswith(prefix):
            return ()
        return tuple(
            ref.strip()
            for ref in detail[len(prefix):].split(",")
            if ref.strip()
        )

    def _repair_source_ref_coverage(
        self,
        *,
        raw: Any,
        profile: TaskSemanticProfile,
        missing_refs: tuple[str, ...],
        reasoning_effort: str | None = None,
        planning_deadline: float | None = None,
        run_id: str | None = None,
    ) -> Any:
        """Repair provenance annotations without rewriting valid task semantics/topology."""
        payload = raw.get("data", raw) if isinstance(raw, dict) else {}
        tasks = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(tasks, list) or not tasks:
            raise TaskDecompositionError("coverage repair requires the original task list")
        task_keys = tuple(
            str(item.get("key") or "").strip()
            for item in tasks
            if isinstance(item, dict) and str(item.get("key") or "").strip()
        )
        if not task_keys:
            raise TaskDecompositionError("coverage repair requires stable task keys")

        source_registry = {
            item["ref"]: item["text"]
            for item in self._source_registry(profile)
        }
        missing_registry = [
            {"ref": ref, "text": source_registry[ref]}
            for ref in missing_refs
            if ref in source_registry
        ]
        if len(missing_registry) != len(missing_refs):
            raise TaskDecompositionError("coverage repair contains unknown source refs")

        schema = {
            "type": "object",
            "properties": {
                "assignments": {
                    "type": "array",
                    "minItems": len(missing_refs),
                    "maxItems": len(missing_refs),
                    "items": {
                        "type": "object",
                        "properties": {
                            "sourceRef": {"type": "string", "enum": list(missing_refs)},
                            "taskKey": {"type": "string", "enum": list(task_keys)},
                            "rationale": {"type": "string"},
                        },
                        "required": ["sourceRef", "taskKey", "rationale"],
                    },
                },
            },
            "required": ["assignments"],
        }
        task_catalog = [
            {
                "key": str(item.get("key") or ""),
                "title": str(item.get("title") or ""),
                "objective": str(item.get("objective") or ""),
                "acceptanceCriteria": item.get("acceptanceCriteria") or [],
                "sourceRefs": item.get("sourceRefs") or [],
            }
            for item in tasks
            if isinstance(item, dict)
        ]
        repair_version = f"{TASK_DECOMPOSITION_PROMPT_VERSION}.repair1.coverage"
        self.last_audit["promptVersion"] = repair_version
        assignment_result = self._call_llm(
            stage="repair_coverage",
            prompt="Repair only the missing TaskPlan source-reference annotations. "
            "Do not create, delete, rename or rewrite tasks and do not change relations. "
            "Assign every missing sourceRef exactly once to the existing task whose objective "
            "and acceptance criteria will produce or verify that requirement. Return JSON only.\n"
            f"Missing source registry entries: {json.dumps(missing_registry, ensure_ascii=False)}\n"
            f"Existing tasks: {json.dumps(task_catalog, ensure_ascii=False)}",
            schema=schema,
            reasoning_effort=reasoning_effort,
            prompt_version=repair_version,
            call_key="repair_coverage",
            planning_deadline=planning_deadline,
            run_id=run_id,
        )
        self._capture_model_audit(assignment_result)
        assignment_payload = (
            assignment_result.get("data", assignment_result)
            if isinstance(assignment_result, dict)
            else {}
        )
        assignments = (
            assignment_payload.get("assignments")
            if isinstance(assignment_payload, dict)
            else None
        )
        if not isinstance(assignments, list):
            raise TaskDecompositionError("coverage repair returned no assignments")

        assigned_refs: list[str] = []
        assignments_by_task: dict[str, list[str]] = {}
        for item in assignments:
            if not isinstance(item, dict):
                raise TaskDecompositionError("coverage repair assignment must be an object")
            source_ref = str(item.get("sourceRef") or "").strip()
            task_key = str(item.get("taskKey") or "").strip()
            if source_ref not in missing_refs or task_key not in task_keys:
                raise TaskDecompositionError("coverage repair returned an unknown ref or task key")
            assigned_refs.append(source_ref)
            assignments_by_task.setdefault(task_key, []).append(source_ref)
        if len(assigned_refs) != len(set(assigned_refs)) or set(assigned_refs) != set(missing_refs):
            raise TaskDecompositionError(
                "coverage repair must assign every missing source ref exactly once"
            )

        repaired = deepcopy(raw)
        repaired_payload = repaired.get("data", repaired)
        for item in repaired_payload["tasks"]:
            task_key = str(item.get("key") or "").strip()
            additions = assignments_by_task.get(task_key, [])
            if additions:
                item["sourceRefs"] = list(dict.fromkeys([
                    *(str(ref) for ref in item.get("sourceRefs", []) if str(ref)),
                    *additions,
                ]))
        return repaired

    def _capture_model_audit(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        if result.get("model"):
            self.last_audit["modelId"] = str(result["model"])
        if result.get("modelVersion"):
            self.last_audit["modelVersion"] = str(result["modelVersion"])
        if result.get("provider"):
            self.last_audit["provider"] = str(result["provider"])

    def build_prompt(
        self,
        *,
        profile: TaskSemanticProfile,
        task_input: Mapping[str, Any] | None,
        existing_semantic_tasks: tuple[Mapping[str, Any], ...] = (),
    ) -> str:
        level = profile.estimated_complexity
        catalog = []
        visible_capabilities = self.capability_catalog.expand_dependencies(
            profile.required_capabilities
        )
        for capability_id in visible_capabilities:
            item = self.capability_catalog.get(capability_id)
            catalog.append({
                "capabilityId": item.capability_id,
                "purpose": item.prompt_profile.purpose,
                "whenToUse": item.prompt_profile.when_to_use,
                "whenNotToUse": item.prompt_profile.when_not_to_use,
                "decompositionHints": item.prompt_profile.decomposition_hints,
                "qualityCriteria": item.prompt_profile.quality_criteria,
                "dependsOn": list(item.depends_on),
                "optionalDependencies": list(item.optional_dependencies),
                "outputFields": list(item.output_contract.get("properties", {})),
            })
        material_refs = tuple(
            str(item) for item in ((task_input or {}).get("materialRefs") or []) if str(item)
        )
        contract = {
            "objective": (task_input or {}).get("objective") or profile.primary_goal,
            "constraints": (task_input or {}).get("constraints") or profile.key_constraints,
            "expectedArtifacts": (task_input or {}).get("expectedArtifacts") or profile.expected_artifacts,
            **({"taskAcceptance": task_input["taskAcceptance"]} if (task_input or {}).get("taskAcceptance") else {}),
            "verificationRequirements": profile.verification_requirements,
            "sourceRegistry": [
                *self._source_registry(profile),
                *(
                    {"ref": item, "kind": "material_manifest", "text": "immutable content manifest"}
                    for item in material_refs
                ),
            ],
            "materials": {
                key: value
                for key in ("materials", "sourceMaterials", "attachmentContext", "materialText", "contractText")
                if (value := (task_input or {}).get(key)) not in (None, "", [], {})
            },
        }
        return serialize_planning_request({
            "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION,
            "operation": "task_decomposition",
            "planningRequest": contract,
            "semanticProfile": profile.model_dump(by_alias=True, mode="json"),
            "capabilityCatalog": catalog,
            "existingSemanticTasks": list(existing_semantic_tasks),
        })

    @staticmethod
    def _budget_metadata(profile: TaskSemanticProfile, node_count: int) -> dict[str, Any]:
        """记录档位预算三元组：只做审计观测，不在生成侧拦截。"""
        budget_lo, budget_hi = PLANNING_BUDGETS[profile.estimated_complexity]
        lo, hi = int(budget_lo), int(budget_hi)
        return {
            "budgetRange": [lo, hi],
            "actualTaskCount": int(node_count),
            "withinBudget": bool(lo <= node_count <= hi),
        }

    @staticmethod
    def _source_registry(profile: TaskSemanticProfile) -> list[dict[str, str]]:
        return [
            *(
                {"ref": f"constraint:{index}", "kind": "constraint", "text": str(value)}
                for index, value in enumerate(profile.key_constraints, start=1)
            ),
            *(
                {"ref": f"artifact:{index}", "kind": "expected_artifact", "text": str(value)}
                for index, value in enumerate(profile.expected_artifacts, start=1)
            ),
        ]

    def _to_plan(
        self,
        mission_id: str,
        profile: TaskSemanticProfile,
        strategy: str,
        raw: Any,
        task_input: Mapping[str, Any] | None = None,
        existing_semantic_tasks: tuple[Mapping[str, Any], ...] = (),
    ) -> TaskPlan:
        payload = raw.get("data", raw) if isinstance(raw, dict) else {}
        if strategy == "initial_commit_candidate" and isinstance(payload, dict) and payload.get("controlPolicies"):
            raise TaskDecompositionError(
                "INITIAL_CONTROL_GRAPH_UNSUPPORTED: formal initial graphs require controlPolicies=[]. "
                "Preserve verification/correction obligations with a bounded forward-only task sequence.")
        tasks = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(tasks, list) or not tasks:
            raise TaskDecompositionError("decomposer returned no tasks")
        self._validate_workset_sources(tasks, task_input)
        nodes: list[PlannedTask] = []
        key_map: dict[str, str] = {}
        raw_parent_keys: list[str | None] = []
        used_keys: set[str] = set()
        for item in tasks:
            capability = str(item.get("capabilityId") or "").strip().lower()
            self.capability_catalog.get(capability)
            objective = str(item.get("objective") or "").strip()
            if not objective or re.match(r"^(complete|完成)\s*\S*$", objective, re.IGNORECASE):
                raise TaskDecompositionError(f"task {item.get('key')} has no business objective")
            criteria = tuple(str(value).strip() for value in item.get("acceptanceCriteria", []) if str(value).strip())
            if not criteria:
                raise TaskDecompositionError(f"task {item.get('key')} has empty acceptance criteria")
            raw_key = str(item.get("key") or "").strip()
            key = self._resolve_semantic_task_key(
                raw_key=raw_key,
                capability=capability,
                logical_role=str(item.get("logicalRole") or "task").strip(),
                existing_semantic_tasks=existing_semantic_tasks,
                used_keys=used_keys,
            )
            if raw_key in key_map:
                raise TaskDecompositionError(f"duplicate semantic task key: {raw_key}")
            key_map[raw_key] = key
            used_keys.add(key)
            raw_parent_keys.append(item.get("parentKey"))
            nodes.append(PlannedTask(
                key=key,
                parentKey=None,
                title=str(item.get("title") or objective[:60]).strip(),
                objective=objective,
                constraints=self._normalize_constraints(item.get("constraints")),
                capabilityRequirements=(capability,),
                acceptanceCriteria=criteria,
                sourceRefs=tuple(str(value) for value in item.get("sourceRefs", []) if str(value)),
                decompositionRationale=str(item.get("decompositionRationale") or ""),
                logicalRole=str(item.get("logicalRole") or "task"),
                producedArtifacts=tuple(
                    str(value).strip()
                    for value in item.get("producedArtifacts", [])
                    if str(value).strip()
                ),
                workset=self._normalize_workset_spec(item.get("workset")),
                metadata={"plannerStrategy": strategy, "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION},
            ))
        nodes = [
            node.model_copy(update={
                "parent_key": key_map.get(raw_parent, raw_parent) if raw_parent else None,
            })
            for node, raw_parent in zip(nodes, raw_parent_keys)
        ]
        material_refs = tuple(
            str(item) for item in ((task_input or {}).get("materialRefs") or []) if str(item)
        )
        if material_refs and not any(node.workset is not None for node in nodes):
            preferred = next(
                (
                    index for index, node in enumerate(nodes)
                    if node.capability_requirements[0] in {
                        "information_extraction", "task_understanding", "analysis", "evidence_analysis"
                    }
                ),
                0,
            )
            nodes[preferred] = nodes[preferred].model_copy(
                update={
                    "workset": WorksetSpec(sourceManifestRefs=material_refs),
                    "source_refs": tuple(dict.fromkeys((*nodes[preferred].source_refs, *material_refs))),
                }
            )
        self._complete_missing_capability_tasks(nodes, profile, strategy)
        raw_relations = [
                TaskPlanRelation(
                    sourceKey=key_map.get(str(item.get("sourceKey") or "").strip(), str(item.get("sourceKey") or "").strip()),
                    targetKey=key_map.get(str(item.get("targetKey") or "").strip(), str(item.get("targetKey") or "").strip()),
                    relationType=item.get("relationType"),
                )
                for item in payload.get("relations", [])
            ]
        nodes = canonicalize_final_synthesis_nodes(nodes, raw_relations)
        nodes = self._ensure_expected_artifact_producer(
            nodes=nodes,
            relations=raw_relations,
            profile=profile,
            strategy=strategy,
        )
        control_policies = tuple(
            VerificationLoopPolicy.model_validate({
                **item,
                "bodyEntryKey": key_map.get(
                    str(item.get("bodyEntryKey") or "").strip(),
                    str(item.get("bodyEntryKey") or "").strip(),
                ),
                "bodyExitKey": key_map.get(
                    str(item.get("bodyExitKey") or "").strip(),
                    str(item.get("bodyExitKey") or "").strip(),
                ),
                "conditionSourceKey": key_map.get(
                    str(item.get("conditionSourceKey") or "").strip(),
                    str(item.get("conditionSourceKey") or "").strip(),
                ),
            })
            for item in payload.get("controlPolicies", [])
            if isinstance(item, dict)
        )
        try:
            compile_result = TaskPlanTopologyCompiler(self.capability_catalog).compile(
                nodes=nodes, raw_relations=raw_relations, control_policies=control_policies
            )
        except TopologyCompileError as exc:
            audit = failed_topology_audit(
                error=exc, nodes=nodes, relations=raw_relations,
                control_policies=control_policies, catalog=self.capability_catalog,
                producer_kind="dynamic", catalog_source="injected",
                capability_coverage_mode="complete",
                repair_attempts=int((self.last_audit.get("topology") or {}).get("repairAttempts", 0)),
            )
            exc.audit = audit
            self.last_audit["topologyCompilation"] = audit
            raise
        self.last_audit["topologyCompilation"] = successful_topology_audit(
            result=compile_result, nodes=nodes, catalog=self.capability_catalog,
            producer_kind="dynamic", catalog_source="injected",
            capability_coverage_mode="complete",
            repair_attempts=int((self.last_audit.get("topology") or {}).get("repairAttempts", 0)),
            repair_operation_types=[
                str(item.get("op"))
                for item in ((self.last_audit.get("topology") or {}).get("repairPatch", {}).get("operations", []))
                if isinstance(item, Mapping) and item.get("op")
            ],
        )
        plan = TaskPlan(
            missionId=mission_id,
            nodes=tuple(nodes),
            relations=compile_result.task_plan_relations,
            controlPolicies=compile_result.control_policies,
            expectedArtifacts=tuple(profile.expected_artifacts),
            metadata={
                "strategy": strategy,
                "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION,
                "complexityBand": profile.estimated_complexity.value,
                "planningBudget": self._budget_metadata(profile, len(nodes)),
                "degraded": False,
            },
        )
        self._validate_coverage(plan, profile)
        return plan

    @staticmethod
    def _validate_workset_sources(tasks, task_input) -> None:
        allowed = set((task_input or {}).get("materialRefs") or ())
        for task in tasks:
            try:
                spec = TaskDecomposer._normalize_workset_spec(task.get("workset"))
                if spec is not None:
                    spec.validate_sources(allowed)
            except ValueError as exc:
                raise TaskDecompositionError(f"task {task.get('key')}: {exc}") from exc

    @staticmethod
    def _normalize_workset_spec(raw: Any) -> WorksetSpec | None:
        if not isinstance(raw, Mapping):
            return None
        source_refs = raw.get("sourceManifestRefs")
        if not isinstance(source_refs, (list, tuple)):
            legacy_manifest_id = str(raw.get("manifestId") or "").strip()
            source_refs = [legacy_manifest_id] if legacy_manifest_id else []
        canonical: dict[str, Any] = {
            "sourceManifestRefs": [str(value) for value in source_refs if str(value).strip()],
        }
        for key in (
            "unitKind", "cursorStrategy", "packingPolicy",
            "parallelismPolicy", "estimatedUnitCount",
        ):
            if key in raw:
                canonical[key] = raw[key]
        if "cursorStrategy" not in canonical and str(raw.get("consumeMode") or "").strip() == "cursor":
            canonical["cursorStrategy"] = "sequence"
        return WorksetSpec.model_validate(canonical)

    @staticmethod
    def _validated_outline_tasks(raw: Any) -> tuple[list[dict[str, Any]], list[str]]:
        payload = raw.get("data", raw) if isinstance(raw, dict) else None
        outline = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(outline, list) or not outline:
            raise TaskDecompositionError("staged outline returned no tasks")
        keys = [str(item.get("key") or "").strip() for item in outline if isinstance(item, dict)]
        if len(keys) != len(outline) or not all(keys) or len(keys) != len(set(keys)):
            raise TaskDecompositionError("staged outline contains empty or duplicate task keys")
        return outline, keys

    @staticmethod
    def _validated_detail_tasks(raw: Any, frozen_batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = raw.get("data", raw) if isinstance(raw, dict) else None
        rows = payload.get("tasks") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != len(frozen_batch):
            raise TaskDecompositionError("staged detail batch changed frozen task count")
        rows_by_key = {
            str(item.get("key") or ""): item
            for item in rows
            if isinstance(item, dict) and str(item.get("key") or "")
        }
        normalized_rows: list[dict[str, Any]] = []
        for index, frozen in enumerate(frozen_batch):
            frozen_key = str(frozen.get("key") or "")
            row = rows_by_key.get(frozen_key, rows[index])
            if not isinstance(row, dict):
                raise TaskDecompositionError("staged detail batch contains a non-object task")
            normalized = dict(row)
            # Identity fields belong exclusively to the frozen outline. Detail
            # units contribute content and may not rename or rebind tasks.
            normalized["key"] = frozen_key
            normalized["capabilityId"] = frozen.get("capabilityId")
            normalized["logicalRole"] = frozen.get("logicalRole") or "task"
            if not isinstance(normalized.get("sourceRefs"), list):
                normalized["sourceRefs"] = list(frozen.get("sourceRefs") or [])
            if not str(normalized.get("capabilityId") or "").strip():
                raise TaskDecompositionError(f"staged detail task {frozen_key!r} has no capabilityId")
            objective = str(normalized.get("objective") or "").strip()
            if not objective or re.match(r"^(complete|瀹屾垚)\s*\S*$", objective, re.IGNORECASE):
                raise TaskDecompositionError(f"staged detail task {frozen_key!r} has no business objective")
            criteria = [str(value).strip() for value in normalized.get("acceptanceCriteria", []) if str(value).strip()]
            if not criteria:
                raise TaskDecompositionError(f"staged detail task {frozen_key!r} has empty acceptance criteria")
            normalized_rows.append(normalized)
        return normalized_rows

    @staticmethod
    def _resolve_semantic_task_key(
        *,
        raw_key: str,
        capability: str,
        logical_role: str,
        existing_semantic_tasks: tuple[Mapping[str, Any], ...],
        used_keys: set[str],
    ) -> str:
        """Resolve unstable ordinal model keys without hashing semantic content.

        A descriptive model key remains authoritative when it is already in the catalog.
        Otherwise an existing key is reused only when its role/capability match is
        unambiguous; ordinal placeholders fall back to a deterministic logical-role/
        capability key without hashing semantic content.
        """
        if not raw_key:
            raise TaskDecompositionError("task has no semantic logical key")
        if raw_key in {str(item.get("key") or "").strip() for item in existing_semantic_tasks}:
            return raw_key
        matches = [
            str(item.get("key") or "").strip()
            for item in existing_semantic_tasks
            if str(item.get("capabilityId") or item.get("capability") or "").strip().lower() == capability
            and str(item.get("logicalRole") or item.get("logical_role") or "task").strip().lower() == (logical_role or "task").lower()
        ]
        matches = [item for item in matches if item and item not in used_keys]
        if len(matches) == 1:
            return matches[0]
        ordinal = re.fullmatch(r"(?:task|step|node)[\s_:/-]*\d+(?:[\s_:/-].*)?", raw_key.lower())
        if ordinal:
            role = re.sub(r"[^a-z0-9]+", "_", (logical_role or "task").lower()).strip("_") or "task"
            capability_slug = re.sub(r"[^a-z0-9]+", "_", capability.lower()).strip("_") or "capability"
            base = f"{role}:{capability_slug}"
            candidate = base
            suffix = 2
            while candidate in used_keys:
                candidate = f"{base}:{suffix}"
                suffix += 1
            return candidate
        return raw_key

    @staticmethod
    def _normalize_constraints(value: Any) -> list[dict[str, Any]]:
        """Normalize model shorthand at the L1 contract boundary."""
        if value in (None, "", []):
            return []
        if not isinstance(value, list):
            raise TaskDecompositionError("task constraints must be an array")
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(dict(item))
            elif isinstance(item, str) and item.strip():
                normalized.append({"type": "task_constraint", "value": item.strip()})
            else:
                raise TaskDecompositionError("task constraint must be an object or non-empty string")
        return normalized

    def _ensure_expected_artifact_producer(
        self,
        *,
        nodes: list[PlannedTask],
        relations: list[TaskPlanRelation],
        profile: TaskSemanticProfile,
        strategy: str,
    ) -> list[PlannedTask]:
        """Keep the Mission deliverable contract explicit in the semantic plan.

        ``artifact_generation`` is the existing terminal completion capability.
        This helper only makes that existing mechanism cover a declared
        deliverable when the model omitted the producer; it does not inspect or
        rewrite domain answers.
        """
        expected = tuple(
            str(item).strip() for item in profile.expected_artifacts if str(item).strip()
        )
        if not expected:
            return nodes

        artifact_nodes = [
            node for node in nodes
            if node.capability_requirements
            and node.capability_requirements[0] == "artifact_generation"
        ]
        outgoing = {
            relation.source_key
            for relation in relations
            if relation.relation_type == SemanticTaskRelationType.DEPENDS_ON
        }
        terminal_artifact_nodes = [
            node for node in artifact_nodes if node.key not in outgoing
        ]
        if not terminal_artifact_nodes:
            descriptor = self.capability_catalog.get("artifact_generation")
            used_keys = {node.key for node in nodes}
            key = "required:artifact_generation:final"
            suffix = 2
            while key in used_keys:
                key = f"required:artifact_generation:final:{suffix}"
                suffix += 1
            nodes.append(PlannedTask(
                key=key,
                title=descriptor.display_name,
                objective=(
                    "Synthesize every declared Mission deliverable into the final output."
                ),
                capabilityRequirements=("artifact_generation",),
                acceptanceCriteria=(
                    "Every declared Mission deliverable is present in the final output.",
                ),
                sourceRefs=tuple(
                    f"artifact:{index}" for index, _ in enumerate(expected, start=1)
                ),
                producedArtifacts=expected,
                decompositionRationale=(
                    "Existing terminal completion mechanism materialized the missing "
                    "declared deliverable producer."
                ),
                logicalRole=FINAL_SYNTHESIS_LOGICAL_ROLE,
                metadata={
                    "plannerStrategy": strategy,
                    "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION,
                },
            ))
            terminal_artifact_nodes = [nodes[-1]]

        final_key = terminal_artifact_nodes[-1].key
        return [
            node.model_copy(update={
                "logical_role": FINAL_SYNTHESIS_LOGICAL_ROLE,
                "produced_artifacts": expected,
            })
            if node.key == final_key
            else node.model_copy(update={"logical_role": "supporting_artifact"})
            if node.capability_requirements
            and node.capability_requirements[0] == "artifact_generation"
            and node.logical_role in {FINAL_SYNTHESIS_LOGICAL_ROLE, *FINAL_SYNTHESIS_ROLES}
            else node
            for node in nodes
        ]

    def _complete_missing_capability_tasks(
        self,
        nodes: list[PlannedTask],
        profile: TaskSemanticProfile,
        strategy: str,
    ) -> None:
        """Materialize catalog-required capabilities without adding domain logic."""
        present = {node.capability_requirements[0] for node in nodes}
        used_keys = {node.key for node in nodes}
        # The model may omit an indirect prerequisite even when the intent
        # profile lists only the requested leaf capabilities.  Materialize the
        # catalog's full required-dependency closure here so the subsequent
        # topology pass never has to invent a domain-specific fallback.
        requested_capabilities = list(profile.required_capabilities)
        if profile.expected_artifacts and "artifact_generation" not in requested_capabilities:
            requested_capabilities.append("artifact_generation")
        required_capabilities = self.capability_catalog.expand_dependencies(
            requested_capabilities
        )
        for capability in required_capabilities:
            if capability in present:
                continue
            descriptor = self.capability_catalog.get(capability)
            base_key = f"required:{capability}"
            key = base_key
            suffix = 2
            while key in used_keys:
                key = f"{base_key}:{suffix}"
                suffix += 1
            nodes.append(PlannedTask(
                key=key,
                title=descriptor.display_name,
                objective=(
                    f"Apply {descriptor.display_name} as a required prerequisite for: "
                    f"{profile.primary_goal}"
                ),
                capabilityRequirements=(capability,),
                acceptanceCriteria=(
                    descriptor.prompt_profile.quality_criteria[0]
                    if descriptor.prompt_profile.quality_criteria
                    else "The capability output satisfies its declared contract.",
                ),
                producedArtifacts=(
                    tuple(profile.expected_artifacts)
                    if capability == "artifact_generation"
                    else ()
                ),
                decompositionRationale="Capability catalog required this missing prerequisite.",
                logicalRole=(
                    FINAL_SYNTHESIS_LOGICAL_ROLE
                    if capability == "artifact_generation"
                    else "prerequisite"
                ),
                metadata={
                    "plannerStrategy": strategy,
                    "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION,
                },
            ))
            present.add(capability)
            used_keys.add(key)

    @staticmethod
    def _validate_coverage(plan: TaskPlan, profile: TaskSemanticProfile) -> None:
        searchable_plan = plan.model_dump(by_alias=True)
        # The contract itself and the explicit producer declaration are not
        # evidence that a planner task covered the requested source registry
        # item.  Keep coverage-repair behavior independent from the new
        # terminal-deliverable invariant.
        searchable_plan.pop("expectedArtifacts", None)
        for node in searchable_plan.get("nodes", []):
            if isinstance(node, dict):
                node.pop("producedArtifacts", None)
        searchable = json.dumps(searchable_plan, ensure_ascii=False).lower()
        cited_refs = {
            str(ref).strip().lower()
            for node in plan.nodes
            for ref in node.source_refs
            if str(ref).strip()
        }
        required = [
            *(
                (f"constraint:{index}", str(value))
                for index, value in enumerate(profile.key_constraints, start=1)
            ),
            *(
                (f"artifact:{index}", str(value))
                for index, value in enumerate(profile.expected_artifacts, start=1)
            ),
        ]
        missing_refs = [
            ref
            for ref, text in required
            if ref not in cited_refs and text.lower() not in searchable
        ]
        if missing_refs:
            raise TaskDecompositionError(
                "TaskPlan coverage gap for source refs: " + ", ".join(missing_refs)
            )

    def _fallback(
        self,
        *,
        mission_id: str,
        profile: TaskSemanticProfile,
        strategy: str,
        reason: str,
        existing_semantic_tasks: tuple[Mapping[str, Any], ...] = (),
        task_input: Mapping[str, Any] | None = None,
    ) -> TaskPlan:
        capabilities = list(dict.fromkeys(profile.required_capabilities))
        if profile.expected_artifacts and "artifact_generation" not in capabilities:
            capabilities.append("artifact_generation")
        nodes: list[PlannedTask] = []
        selected = set(capabilities)
        used_keys: set[str] = set()
        for index, capability in enumerate(capabilities, start=1):
            descriptor = self.capability_catalog.get(capability)
            key = self._resolve_semantic_task_key(
                raw_key=f"task-{index}",
                capability=capability,
                logical_role=descriptor.planning_stage,
                existing_semantic_tasks=existing_semantic_tasks,
                used_keys=used_keys,
            )
            used_keys.add(key)
            nodes.append(PlannedTask(
                key=key,
                title=descriptor.display_name,
                objective=f"Use {descriptor.display_name} to advance the mission goal: {profile.primary_goal}",
                constraints=[{"type": "mission_constraint", "value": item} for item in profile.key_constraints],
                capabilityRequirements=(capability,),
                acceptanceCriteria=(
                    descriptor.prompt_profile.quality_criteria[0]
                    if descriptor.prompt_profile.quality_criteria
                    else "Output satisfies the declared capability contract.",
                ),
                sourceRefs=tuple(profile.expected_artifacts),
                producedArtifacts=(
                    tuple(profile.expected_artifacts)
                    if capability == "artifact_generation"
                    else ()
                ),
                decompositionRationale="Explicit degraded deterministic plan after v2 decomposition failure.",
                logicalRole=(
                    FINAL_SYNTHESIS_LOGICAL_ROLE
                    if capability == "artifact_generation"
                    else descriptor.planning_stage
                ),
                metadata={"plannerStrategy": strategy, "degraded": True, "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION},
            ))
        keys = {node.capability_requirements[0]: node.key for node in nodes}
        material_refs = tuple(
            str(item) for item in ((task_input or {}).get("materialRefs") or []) if str(item)
        )
        if material_refs and nodes:
            preferred = next(
                (
                    index for index, node in enumerate(nodes)
                    if node.capability_requirements[0] in {
                        "information_extraction", "task_understanding", "analysis", "evidence_analysis"
                    }
                ),
                0,
            )
            nodes[preferred] = nodes[preferred].model_copy(update={
                "workset": WorksetSpec(sourceManifestRefs=material_refs),
                "source_refs": tuple(dict.fromkeys((*nodes[preferred].source_refs, *material_refs))),
            })
        relations = tuple(
            TaskPlanRelation(sourceKey=keys[dependency], targetKey=keys[capability], relationType=SemanticTaskRelationType.DEPENDS_ON)
            for capability in capabilities
            for dependency in (
                *self.capability_catalog.get(capability).depends_on,
                *self.capability_catalog.get(capability).optional_dependencies,
            )
            if dependency in selected
        )
        return validate_task_plan_for_execution(
            capability_catalog=self.capability_catalog,
            mission_id=mission_id,
            nodes=nodes,
            relations=relations,
            expected_artifacts=tuple(profile.expected_artifacts),
            relation_origin=EdgeOrigin.FALLBACK_GENERATED,
            producer_kind="fallback",
            audit_sink=lambda audit: self.last_audit.__setitem__("topologyCompilation", audit),
            metadata={
                "strategy": strategy,
                "promptVersion": TASK_DECOMPOSITION_PROMPT_VERSION,
                "complexityBand": profile.estimated_complexity.value,
                "planningBudget": self._budget_metadata(profile, len(nodes)),
                "degraded": True,
                "degradationReason": reason[:1000],
            },
        )


__all__ = [
    "PLANNING_MODEL_TIMEOUT_SECONDS",
    "TASK_DECOMPOSITION_PROMPT_VERSION",
    "TaskDecomposer",
    "TaskDecompositionError",
]
