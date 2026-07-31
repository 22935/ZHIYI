"""Registration boundary for Legal Pack planning capabilities."""

from __future__ import annotations

from agentos.core.planning import CapabilityCatalog
from packs.legal.planning.capabilities import (
    LEGAL_CAPABILITY_IDS,
    legal_capability_descriptors,
)


def register_legal_capabilities(catalog: CapabilityCatalog) -> None:
    """Register the complete legal contribution, safely tolerating a full replay."""

    existing = []
    for capability_id in LEGAL_CAPABILITY_IDS:
        try:
            catalog.get(capability_id)
        except KeyError:
            existing.append(False)
        else:
            existing.append(True)

    if all(existing):
        return
    if any(existing):
        raise ValueError("partial Legal Pack capability registration detected")

    descriptors = legal_capability_descriptors()
    candidate = CapabilityCatalog([*catalog.available(), *descriptors])
    candidate.validate()
    for descriptor in descriptors:
        catalog.register(descriptor)
    catalog.validate()


__all__ = ["register_legal_capabilities"]
