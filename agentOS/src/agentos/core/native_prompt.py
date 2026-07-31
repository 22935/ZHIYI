"""Domain-neutral prompt construction for native ACG capability execution."""

from __future__ import annotations

import json
from typing import Any


NATIVE_CAPABILITY_PROMPT_VERSION = "native-capability.v1"


class NativeCapabilityPromptBuilder:
    """Build one capability prompt from normalized runtime facts only."""

    def build(
        self,
        *,
        capability_descriptor,
        step_goal: str,
        task_title: str,
        task_input: dict[str, Any],
        context_data: dict[str, Any],
        source_data: dict[str, Any],
        evidence_refs: list[str],
        output_schema: dict[str, Any],
    ) -> str:
        descriptor = capability_descriptor.model_dump(
            by_alias=True,
            mode="json",
            exclude={"aliases", "domain_hints", "plugin_id", "plugin_version"},
        )
        request = {
            "capability": descriptor,
            "stepGoal": step_goal,
            "task": self._canonical_task(task_title, task_input),
            "context": {
                "upstreamData": context_data,
                "sourceData": source_data,
                "evidenceRefs": evidence_refs,
            },
            "outputSchema": output_schema,
        }
        payload = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        return (
            "Execute exactly one declared capability for an AgentOS workflow. "
            "Use only the supplied task and upstream facts. Do not invent measurements, "
            "prices, dates, sources, or completed actions. Separate known facts from "
            "assumptions and open questions. Show formulas and assumptions for numeric "
            "estimates. Be concise: unless the schema is stricter, use at most 8 useful "
            "items per array and keep each item under 400 characters. Preserve the task "
            "language. Return one JSON object that matches "
            "outputSchema exactly, without markdown fences or commentary.\n"
            f"RUNTIME_REQUEST={payload}"
        )

    @staticmethod
    def _canonical_task(task_title: str, task_input: dict[str, Any]) -> dict[str, Any]:
        """Keep semantic task facts once and exclude runtime/security metadata."""

        def text(value: Any) -> str:
            return str(value or "").strip()

        objective = next(
            (
                value
                for value in (
                    text(task_input.get("userIntent")),
                    text(task_input.get("taskGoal")),
                    text(task_title),
                )
                if value
            ),
            "",
        )
        seen = {objective}
        materials: list[str] = []
        for key in ("materialText", "contractText"):
            value = text(task_input.get(key))
            if value and value not in seen:
                materials.append(value)
                seen.add(value)

        canonical: dict[str, Any] = {"objective": objective}
        if text(task_title) and text(task_title) != objective:
            canonical["title"] = text(task_title)
        if materials:
            canonical["materials"] = materials
        for source_key, target_key in (
            ("constraints", "constraints"),
            ("expectedArtifacts", "expectedArtifacts"),
            ("sourceMaterials", "sourceMaterials"),
            ("pluginData", "pluginData"),
        ):
            value = task_input.get(source_key)
            if value:
                canonical[target_key] = value
        return canonical

    def build_repair(
        self,
        *,
        original_prompt: str,
        invalid_data: dict[str, Any],
        validation_error: str,
    ) -> str:
        invalid = json.dumps(invalid_data, ensure_ascii=False, separators=(",", ":"))
        return (
            f"{original_prompt}\n"
            "The previous JSON failed contract validation. Correct it once, preserving "
            "supported facts and returning only the corrected JSON object.\n"
            f"VALIDATION_ERROR={validation_error}\nPREVIOUS_JSON={invalid}"
        )

    def build_json_repair(
        self,
        *,
        original_prompt: str,
        validation_error: str,
    ) -> str:
        return (
            f"{original_prompt}\n"
            "The previous response was invalid or truncated JSON. Retry once with a "
            "smaller response. Use fewer and shorter items, close every string/array/object, "
            "and return only one complete JSON object.\n"
            f"PARSE_ERROR={validation_error}"
        )

    def build_artifact(self, **kwargs) -> str:
        return (
            self.build(**kwargs)
            + "\nFINAL_COMPOSITION_RULES="
            + json.dumps(
                {
                    "consumeAllRelevantUpstreamFields": True,
                    "requiredSections": [
                        "executive summary",
                        "requirements and acceptance",
                        "implementation or solution",
                        "resources and calculations",
                        "risks and controls",
                        "verification and unresolved gaps",
                    ],
                    "finalAnswer": "complete standalone Markdown deliverable",
                    "facts": "cite sourceRefs where supplied",
                    "unknowns": "record as openQuestions instead of inventing values",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )


__all__ = ["NATIVE_CAPABILITY_PROMPT_VERSION", "NativeCapabilityPromptBuilder"]
