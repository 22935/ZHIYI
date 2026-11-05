"""Regression tests for the public ACG model boundary."""

import ast
from pathlib import Path

def test_step_node_uses_the_exported_node_type() -> None:
    from support.acg.models import NodeType, StepNode

    node = StepNode(nodeId="step-1")

    assert isinstance(node.node_type, NodeType)
    assert node.node_type is NodeType.STEP


def test_acg_package_has_an_explicit_public_blueprint_export() -> None:
    from support.acg import ACGBlueprint, RuntimeBlueprintSpec

    assert ACGBlueprint is RuntimeBlueprintSpec
    assert RuntimeBlueprintSpec.__name__ == "RuntimeBlueprintSpec"


def test_task_understanding_preserves_detailed_acceptance_criteria() -> None:
    from support.acg.models import build_default_capability_catalog

    descriptor = build_default_capability_catalog().get("task_understanding")

    success_criteria = descriptor.output_contract["properties"]["success_criteria"]
    assert success_criteria["type"] == "array"
    assert "maxItems" not in success_criteria
    assert "maxLength" not in success_criteria["items"]


def test_legacy_models_module_is_an_import_only_compatibility_facade() -> None:
    import support.acg.models as facade
    from support.acg.capabilities import CapabilityCatalog
    from support.acg.schema import StepNode

    assert facade.StepNode is StepNode
    assert facade.CapabilityCatalog is CapabilityCatalog
    assert not hasattr(facade, "promote_workflow_to_acg")

    tree = ast.parse(Path(facade.__file__).read_text(encoding="utf-8"))
    implementation_nodes = (
        ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef,
    )
    assert not any(isinstance(node, implementation_nodes) for node in tree.body)
