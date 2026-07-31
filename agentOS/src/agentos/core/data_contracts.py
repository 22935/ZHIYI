"""Structured input/output contract validation shared by ACG and communication."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema.validators import validator_for


class ContextContractError(ValueError):
    """A step input or output does not satisfy its declared JSON Schema."""

    def __init__(self, *, step_id: str, direction: str, message: str, path: str = ""):
        self.step_id = step_id
        self.direction = direction
        self.path = path
        super().__init__(f"{direction} contract violation at {step_id}{f' ({path})' if path else ''}: {message}")


def check_contract_schema(schema: Dict[str, Any], *, label: str) -> None:
    if not schema:
        return
    validator = validator_for(schema)
    try:
        validator.check_schema(schema)
    except Exception as exc:
        raise ValueError(f"invalid JSON Schema for {label}: {exc}") from exc


def validate_contract_payload(
    payload: Any,
    schema: Dict[str, Any],
    *,
    step_id: str,
    direction: str,
) -> None:
    if not schema:
        return
    validator = validator_for(schema)(schema)
    try:
        validator.validate(payload)
    except JSONSchemaValidationError as exc:
        path = ".".join(str(item) for item in exc.absolute_path)
        raise ContextContractError(
            step_id=step_id,
            direction=direction,
            message=exc.message,
            path=path,
        ) from exc


def apply_contract_defaults(payload: Any, schema: Dict[str, Any]) -> Any:
    """Copy a payload while applying only explicit JSON Schema defaults.

    Model output remains untrusted input. This conservative normalizer never
    coerces types, drops array items, or invents undeclared values.
    """

    if isinstance(payload, dict):
        normalized = {key: deepcopy(value) for key, value in payload.items()}
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return normalized
        for key, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                continue
            if key not in normalized and "default" in property_schema:
                normalized[key] = deepcopy(property_schema["default"])
            if key in normalized:
                normalized[key] = apply_contract_defaults(
                    normalized[key], property_schema
                )
        return normalized

    if isinstance(payload, list):
        item_schema = schema.get("items")
        if not isinstance(item_schema, dict):
            return deepcopy(payload)
        return [apply_contract_defaults(item, item_schema) for item in payload]

    return deepcopy(payload)


__all__ = [
    "ContextContractError",
    "apply_contract_defaults",
    "check_contract_schema",
    "validate_contract_payload",
]
