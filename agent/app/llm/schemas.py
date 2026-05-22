from __future__ import annotations

from typing import Any, Dict


PARSE_CONTRACT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["contract_title", "parties", "contract_type", "key_dates", "amounts", "obligations", "summary"],
    "properties": {
        "contract_title": {"type": "string"},
        "parties": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "role"],
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                },
            },
        },
        "contract_type": {"type": "string"},
        "key_dates": {"type": "array"},
        "amounts": {"type": "array"},
        "obligations": {"type": "array"},
        "summary": {"type": "string"},
    },
}

RISK_DETECT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["risks"],
    "properties": {
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "level", "clause", "reason", "consequence", "suggestion", "evidenceIds"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "level": {"type": "string", "enum": ["high", "medium", "low"]},
                    "clause": {"type": "string"},
                    "reason": {"type": "string"},
                    "consequence": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "evidenceIds": {"type": "array"},
                },
            },
        }
    },
}

REPORT_GENERATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["report_markdown"],
    "properties": {
        "report_markdown": {"type": "string"},
    },
}


def compact_schema_name(schema: Dict[str, Any]) -> str:
    if schema is PARSE_CONTRACT_SCHEMA:
        return "parse_contract"
    if schema is RISK_DETECT_SCHEMA:
        return "risk_detect"
    if schema is REPORT_GENERATE_SCHEMA:
        return "report_generate"
    return "unknown"


__all__ = [
    "PARSE_CONTRACT_SCHEMA",
    "RISK_DETECT_SCHEMA",
    "REPORT_GENERATE_SCHEMA",
    "compact_schema_name",
]
