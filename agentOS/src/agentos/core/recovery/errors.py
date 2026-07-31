"""Structured errors raised by the controlled runtime-graph kernel."""


class RuntimeGraphError(ValueError):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class PatchValidationError(RuntimeGraphError):
    """A patch violates graph, contract, capability, state, or budget rules."""


class PatchConflictError(RuntimeGraphError):
    """A patch conflicts with persisted graph version or replay history."""


__all__ = ["PatchConflictError", "PatchValidationError", "RuntimeGraphError"]
