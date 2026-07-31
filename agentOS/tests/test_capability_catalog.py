import pytest

from agentos.core.planning import CapabilityCatalog, PlanningCapabilityDescriptor
from agentos.core.planning.default_catalog import build_default_capability_catalog
from agentos.core.planning.native_capabilities import NATIVE_CAPABILITY_IDS


def descriptor(capability_id: str, **kwargs) -> PlanningCapabilityDescriptor:
    return PlanningCapabilityDescriptor(
        capabilityId=capability_id,
        displayName=capability_id,
        **kwargs,
    )


def test_catalog_register_get_resolve_and_stable_sorting():
    catalog = CapabilityCatalog()
    catalog.register(descriptor("later", aliases=["second"], priority=20))
    catalog.register(descriptor("first", aliases=["Primary"], priority=10))

    assert catalog.get("first").capability_id == "first"
    assert catalog.resolve(" primary ").capability_id == "first"
    assert [item.capability_id for item in catalog.available()] == ["first", "later"]


def test_catalog_rejects_duplicate_id_and_alias():
    catalog = CapabilityCatalog([descriptor("alpha", aliases=["shared"])])

    with pytest.raises(ValueError, match="duplicate capabilityId"):
        catalog.register(descriptor("alpha"))
    with pytest.raises(ValueError, match="duplicate capability alias"):
        catalog.register(descriptor("beta", aliases=["shared"]))


def test_catalog_rejects_dangling_dependency():
    catalog = CapabilityCatalog([descriptor("alpha", dependsOn=["missing"])])

    with pytest.raises(ValueError, match="dangling dependency"):
        catalog.validate()


def test_catalog_rejects_dependency_cycle():
    catalog = CapabilityCatalog(
        [
            descriptor("alpha", dependsOn=["beta"]),
            descriptor("beta", optionalDependencies=["alpha"]),
        ]
    )

    with pytest.raises(ValueError, match="dependency cycle"):
        catalog.validate()


def test_catalog_filters_domain_hints_without_cross_domain_leakage():
    catalog = CapabilityCatalog(
        [
            descriptor("shared"),
            descriptor("native", domainHints=["general"]),
            descriptor("specialized", domainHints=["specialized"]),
        ]
    )

    assert [item.capability_id for item in catalog.available("general")] == [
        "native",
        "shared",
    ]
    assert [item.capability_id for item in catalog.available("specialized")] == [
        "shared",
        "specialized",
    ]


def test_catalog_expands_dependencies_in_topological_order():
    catalog = CapabilityCatalog(
        [
            descriptor("understand"),
            descriptor("analyze", dependsOn=["understand"]),
            descriptor("deliver", dependsOn=["analyze"]),
        ]
    )
    catalog.validate()

    assert catalog.expand_dependencies(["deliver"]) == ["understand", "analyze", "deliver"]


def test_default_catalog_contains_only_core_native_capabilities():
    catalog = build_default_capability_catalog()

    assert {item.capability_id for item in catalog.available()} == set(
        NATIVE_CAPABILITY_IDS
    )
    with pytest.raises(KeyError):
        catalog.get("风险识别")
