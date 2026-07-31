"""Core-owned bootstrap definition and deterministic native execution capability."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from agentos.adapters.model_adapter import StructuredGenerationError
from agentos.agents.base import AgentOutput, AgentProfile, AgentRunContext, BaseAgent
from agentos.core.data_contracts import (
    ContextContractError,
    apply_contract_defaults,
    validate_contract_payload,
)
from agentos.core.models.types import WorkflowDefinition, WorkflowDefinitionType, utc_now
from agentos.core.native_prompt import (
    NATIVE_CAPABILITY_PROMPT_VERSION,
    NativeCapabilityPromptBuilder,
)
from agentos.core.planning.native_capabilities import NATIVE_CAPABILITY_IDS


NATIVE_ACG_WORKFLOW_ID = "native_acg_runtime_v1"
NATIVE_AGENT_NAME = "native_general_agent"
# Backward-compatible export derived from the native Catalog contribution.
NATIVE_CAPABILITIES = NATIVE_CAPABILITY_IDS


class NativeGeneralAgent(BaseAgent):
    """Small offline-safe Agent that executes the native bootstrap capabilities."""

    def __init__(self) -> None:
        super().__init__(
            AgentProfile(
                agentName=NATIVE_AGENT_NAME,
                domain="general",
                capabilities=list(NATIVE_CAPABILITY_IDS),
                allowedTools=[
                    "knowledge_search",
                    "current_datetime",
                ],
                description="Executes domain-neutral understanding, analysis, and artifact delivery.",
            )
        )
        self.prompt_builder = NativeCapabilityPromptBuilder()

    async def run(self, context: AgentRunContext) -> AgentOutput:
        objective = str(
            context.task.input.get("userIntent")
            or context.task.input.get("intent")
            or context.task.title
        ).strip()
        upstream = self._upstream_data(context)
        capability = (context.step.capability or "").strip()

        task_summary = str(upstream.get("task_summary") or objective)
        if capability == "information_retrieval":
            if context.tool_runtime is None:
                raise RuntimeError("read-only tool runtime is not configured")
            result = await context.tool_runtime.execute(
                "knowledge_search",
                {"query": task_summary[:500], "top_k": 5},
            )
            try:
                envelope = json.loads(result.text)
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("local knowledge search returned an invalid payload") from exc
            if not envelope.get("ok"):
                raise RuntimeError(
                    "local knowledge search failed: "
                    f"{envelope.get('error') or 'unknown error'}"
                )
            sources = [item.public_dict() for item in result.sources]
            evidence_refs = [item.citation_id for item in result.sources]
            retrieved_information = [
                str(item.get("snippet") or item.get("content") or "").strip()
                for item in ((envelope.get("data") or {}).get("results") or [])
                if isinstance(item, dict)
                and str(item.get("snippet") or item.get("content") or "").strip()
            ]
            if not evidence_refs:
                citation_id = "src_task_input_" + hashlib.sha256(
                    task_summary.encode("utf-8")
                ).hexdigest()[:16]
                sources = [{
                    "citationId": citation_id,
                    "title": "User-provided task facts (offline ACG)",
                    "filename": None,
                    "url": None,
                    "content": task_summary[:4000],
                    "provider": "task-input",
                    "retrievedAt": utc_now().isoformat(),
                }]
                evidence_refs = [citation_id]
                retrieved_information = [task_summary]
            return AgentOutput(
                output={
                    "retrieved_information": retrieved_information,
                    "sources": sources,
                    "evidence_refs": evidence_refs,
                    "retrieval_mode": (
                        "local_knowledge" if result.sources else "task_input_only"
                    ),
                },
                summary=f"Prepared {len(evidence_refs)} offline evidence source(s).",
                sources=sources,
                toolExecutions=[item.public_dict() for item in result.tool_executions],
                evidenceRefs=evidence_refs,
            )
        if capability == "evidence_analysis" and not upstream.get("evidence_refs"):
            raise RuntimeError("evidence_analysis requires upstream evidence references")

        descriptor = context.capability_descriptor
        if descriptor is None:
            raise StructuredGenerationError(
                "CAPABILITY_DESCRIPTOR_UNAVAILABLE",
                f"Capability descriptor is unavailable: {capability or '<empty>'}",
            )
        runtime = context.model_runtime
        if runtime is None or not runtime.is_available():
            raise StructuredGenerationError(
                "MODEL_UNAVAILABLE",
                "No production model is configured for native ACG execution.",
            )

        output_schema = dict(context.step.output_spec or descriptor.output_contract)
        generation_schema = self._generation_schema(capability, output_schema)
        pack = context.context_pack
        source_data = getattr(pack, "source_data", {}) if pack is not None else {}
        evidence_refs = list(getattr(pack, "evidence_refs", []) or []) if pack is not None else []
        prompt_method = (
            self.prompt_builder.build_artifact
            if capability == "artifact_generation"
            else self.prompt_builder.build
        )
        prompt = prompt_method(
            capability_descriptor=descriptor,
            step_goal=context.step.name,
            task_title=context.task.title,
            task_input=dict(context.task.input),
            context_data=upstream,
            source_data=dict(source_data) if isinstance(source_data, dict) else {},
            evidence_refs=evidence_refs,
            output_schema=generation_schema,
        )
        thinking_mode = str(context.task.input.get("thinkingMode") or "disabled")
        output_thinking_mode = thinking_mode
        timeout_seconds = 180.0 if capability == "artifact_generation" else 120.0
        max_output_tokens = 8192 if capability == "artifact_generation" else 4096
        invocations: list[dict[str, Any]] = []
        repair_used = False
        thinking_fallback_reason: str | None = None
        try:
            generated = await runtime.generate_json(
                prompt=prompt,
                schema=generation_schema,
                thinking_mode=thinking_mode,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
                prompt_version=NATIVE_CAPABILITY_PROMPT_VERSION,
            )
        except StructuredGenerationError as exc:
            thinking_enabled = thinking_mode.strip().lower() not in {
                "",
                "disabled",
                "false",
                "none",
                "off",
            }
            if exc.code == "MODEL_EMPTY_RESPONSE" and thinking_enabled:
                thinking_fallback_reason = exc.code
                output_thinking_mode = "disabled"
                generated = await runtime.generate_json(
                    prompt=prompt,
                    schema=generation_schema,
                    thinking_mode=output_thinking_mode,
                    timeout_seconds=timeout_seconds,
                    max_output_tokens=max_output_tokens,
                    prompt_version=(
                        f"{NATIVE_CAPABILITY_PROMPT_VERSION}.thinking-finalization1"
                    ),
                )
            elif exc.code != "MODEL_OUTPUT_INVALID_JSON":
                raise
            else:
                repair_used = True
                generated = await runtime.generate_json(
                    prompt=self.prompt_builder.build_json_repair(
                        original_prompt=prompt,
                        validation_error=str(exc),
                    ),
                    schema=generation_schema,
                    thinking_mode=output_thinking_mode,
                    timeout_seconds=timeout_seconds,
                    max_output_tokens=max_output_tokens,
                    prompt_version=f"{NATIVE_CAPABILITY_PROMPT_VERSION}.json-repair1",
                )
        generation_audit = generated.audit_record()
        if thinking_fallback_reason:
            generation_audit["usage"].update(
                {
                    "thinkingFallback": True,
                    "thinkingFallbackReason": thinking_fallback_reason,
                    "requestedThinkingMode": thinking_mode,
                    "effectiveThinkingMode": output_thinking_mode,
                }
            )
        invocations.append(generation_audit)
        output = apply_contract_defaults(dict(generated.data), generation_schema)
        if capability == "artifact_generation":
            output = self._normalize_artifact_output(context, output)
        try:
            validate_contract_payload(
                output,
                output_schema,
                step_id=context.step.step_id,
                direction="output",
            )
        except ContextContractError as exc:
            if repair_used:
                raise StructuredGenerationError(
                    "OUTPUT_CONTRACT_VIOLATION",
                    str(exc),
                ) from exc
            repair_used = True
            repaired = await runtime.generate_json(
                prompt=self.prompt_builder.build_repair(
                    original_prompt=prompt,
                    invalid_data=output,
                    validation_error=str(exc),
                ),
                schema=generation_schema,
                thinking_mode=output_thinking_mode,
                timeout_seconds=timeout_seconds,
                max_output_tokens=max_output_tokens,
                prompt_version=f"{NATIVE_CAPABILITY_PROMPT_VERSION}.repair1",
            )
            invocations.append(repaired.audit_record())
            output = apply_contract_defaults(dict(repaired.data), generation_schema)
            if capability == "artifact_generation":
                output = self._normalize_artifact_output(context, output)
            try:
                validate_contract_payload(
                    output,
                    output_schema,
                    step_id=context.step.step_id,
                    direction="output",
                )
            except ContextContractError as repair_exc:
                raise StructuredGenerationError(
                    "OUTPUT_CONTRACT_VIOLATION",
                    str(repair_exc),
                ) from repair_exc

        return AgentOutput(
            output=output,
            summary=f"Native capability completed: {capability}.",
            modelInvocations=invocations,
        )

    @staticmethod
    def _generation_schema(
        capability: str,
        output_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the semantic contract owned by the model.

        Runtime output remains governed by ``output_schema``.  Final Markdown and
        the Artifact envelope are deterministic projections, so asking the model
        to reproduce them would duplicate the deliverable and waste its bounded
        completion budget.
        """

        schema = deepcopy(output_schema)
        if capability != "artifact_generation":
            return schema
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return schema
        semantic_fields = {"deliverable", "verification"}
        schema["properties"] = {
            name: value
            for name, value in properties.items()
            if name in semantic_fields
        }
        schema["required"] = [
            name
            for name in schema.get("required", [])
            if name in semantic_fields
        ]
        return schema

    @classmethod
    def _normalize_artifact_output(
        cls,
        context: AgentRunContext,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(output)
        deliverable = normalized.get("deliverable")
        if not isinstance(deliverable, dict):
            deliverable = {
                "title": context.task.title,
                "executiveSummary": str(deliverable or ""),
                "sections": [],
                "calculations": [],
                "assumptions": [],
                "openQuestions": [],
                "sourceRefs": [],
            }
            normalized["deliverable"] = deliverable
        final_answer = cls._render_artifact_markdown(
            deliverable,
            normalized.get("verification"),
        )
        normalized["final_answer"] = final_answer
        artifact_id = "artifact_" + hashlib.sha256(
            f"{context.run.run_id}:{context.step.step_id}:{context.step.attempt}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        normalized["artifact"] = {
            "artifactId": artifact_id,
            "type": "report",
            "title": str(deliverable.get("title") or context.task.title),
            "mediaType": "text/markdown",
            "content": final_answer,
            "structuredData": deliverable,
        }
        return normalized

    @staticmethod
    def _render_artifact_markdown(
        deliverable: dict[str, Any],
        verification: Any,
    ) -> str:
        """Render one user-facing artifact from the structured semantic result."""

        def text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, str):
                return value.strip()
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

        title = text(deliverable.get("title")) or "Workflow deliverable"
        executive_summary = text(deliverable.get("executiveSummary"))
        language_sample = title + executive_summary
        chinese = any("\u4e00" <= character <= "\u9fff" for character in language_sample)
        labels = {
            "calculations": "计算与依据" if chinese else "Calculations and basis",
            "formula": "公式" if chinese else "Formula",
            "inputs": "输入" if chinese else "Inputs",
            "result": "结果" if chinese else "Result",
            "assumptions": "假设" if chinese else "Assumptions",
            "questions": "待确认事项" if chinese else "Open questions",
            "sources": "来源引用" if chinese else "Source references",
            "verification": "验收核对" if chinese else "Verification",
            "status": "状态" if chinese else "Status",
            "gaps": "未解决缺口" if chinese else "Unresolved gaps",
        }
        lines = [f"# {title}"]
        if executive_summary:
            lines.extend(["", executive_summary])

        for section in deliverable.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_title = text(section.get("title"))
            content = text(section.get("content"))
            if section_title:
                lines.extend(["", f"## {section_title}"])
            if content:
                lines.extend(["", content])

        calculations = deliverable.get("calculations") or []
        if calculations:
            lines.extend(["", f"## {labels['calculations']}"])
            for calculation in calculations:
                if not isinstance(calculation, dict):
                    continue
                name = text(calculation.get("name"))
                if name:
                    lines.extend(["", f"### {name}"])
                for key in ("formula", "inputs", "result", "assumptions"):
                    value = calculation.get(key)
                    if value in (None, "", []):
                        continue
                    rendered = ", ".join(text(item) for item in value) if isinstance(value, list) else text(value)
                    lines.append(f"- **{labels[key]}**: {rendered}")

        for key, label in (
            ("assumptions", labels["assumptions"]),
            ("openQuestions", labels["questions"]),
            ("sourceRefs", labels["sources"]),
        ):
            values = deliverable.get(key) or []
            if values:
                lines.extend(["", f"## {label}"])
                lines.extend(f"- {text(item)}" for item in values)

        if isinstance(verification, dict):
            lines.extend(["", f"## {labels['verification']}"])
            status = text(verification.get("status"))
            if status:
                lines.append(f"- **{labels['status']}**: {status}")
            for check in verification.get("checks") or []:
                if not isinstance(check, dict):
                    continue
                criterion = text(check.get("criterion"))
                result = text(check.get("result"))
                evidence = text(check.get("evidence"))
                rendered = " — ".join(item for item in (criterion, result, evidence) if item)
                if rendered:
                    lines.append(f"- {rendered}")
            gaps = verification.get("unresolvedGaps") or []
            if gaps:
                lines.append(f"- **{labels['gaps']}**: " + "; ".join(text(item) for item in gaps))

        return "\n".join(lines).strip()

    @staticmethod
    def _upstream_data(context: AgentRunContext) -> dict[str, Any]:
        pack = context.context_pack
        data = getattr(pack, "data", None) if pack is not None else None
        return dict(data) if isinstance(data, dict) else {}


def native_bootstrap_definition() -> WorkflowDefinition:
    """Return the empty ACG definition that enters the existing PlanningEngine."""

    return WorkflowDefinition(
        workflowId=NATIVE_ACG_WORKFLOW_ID,
        name="知弈OS原生 ACG 运行时",
        domain="general",
        intent="general",
        runtimeEngine="acg",
        definitionType=WorkflowDefinitionType.NATIVE_BOOTSTRAP,
        description="Core-owned planner bootstrap for native domain-neutral tasks.",
        steps=[],
    )


def register_native_runtime(*, agent_registry, workflow_registry) -> None:
    """Register Core definitions before any application Pack is discovered."""

    agent_registry.register(NativeGeneralAgent())
    workflow_registry.register(native_bootstrap_definition())


__all__ = [
    "NATIVE_ACG_WORKFLOW_ID",
    "NATIVE_AGENT_NAME",
    "NATIVE_CAPABILITIES",
    "NativeGeneralAgent",
    "native_bootstrap_definition",
    "register_native_runtime",
]
