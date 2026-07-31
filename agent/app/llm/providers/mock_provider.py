from __future__ import annotations

from typing import Any, Dict


class MockLLMProvider:
    """Explicit development provider with schema-shaped, non-business output.

    Contract examples belong in tests. The application mock must never invent
    parties, clauses, risks, legal sources, or a report that could be mistaken
    for a real analysis.
    """

    provider_name = "mock"
    model = "mock"

    def generate_text(self, prompt: str, **kwargs) -> str:
        return ""

    def generate_json(self, prompt: str, schema: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        required = schema.get("required") if isinstance(schema, dict) else []
        result: Dict[str, Any] = {}
        for field in required or []:
            if field in {"parties", "key_dates", "amounts", "obligations", "risks", "evidenceIds"}:
                result[field] = []
            elif field == "confidence":
                result[field] = 0.0
            else:
                result[field] = ""
        if "report_markdown" in (schema.get("properties") or {}):
            result["report_markdown"] = ""
        return result


__all__ = ["MockLLMProvider"]
