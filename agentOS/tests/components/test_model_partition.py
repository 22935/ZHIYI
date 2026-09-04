from __future__ import annotations

import pytest

from components.model_partition.service import (
    ModelPartitionService,
    ModelPartitionUnavailableError,
)
from contracts.model_partition import ModelLayerRange, ModelPartitionPlan, TensorBoundaryContract


def _valid_plan() -> ModelPartitionPlan:
    return ModelPartitionPlan(
        planId="plan-1",
        modelId="vision-model",
        layers=[
            ModelLayerRange(layerId="encoder", startLayer=0, endLayer=3),
            ModelLayerRange(layerId="decoder", startLayer=4, endLayer=7),
        ],
        placements={"encoder": "edge-01", "decoder": "cloud-01"},
        tensorBoundaries=[TensorBoundaryContract(
            tensorName="encoder.hidden",
            fromLayer="encoder",
            toLayer="decoder",
            dtype="float16",
            shape=[1, 196, 768],
        )],
    )


def test_model_partition_plan_requires_contiguous_ordered_layers_and_boundaries() -> None:
    plan = _valid_plan()

    assert [item.layer_id for item in plan.layers] == ["encoder", "decoder"]
    assert plan.placements == {"encoder": "edge-01", "decoder": "cloud-01"}
    assert plan.tensor_boundaries[0].from_layer == "encoder"


@pytest.mark.parametrize(
    "layers",
    [
        [
            ModelLayerRange(layerId="encoder", startLayer=0, endLayer=3),
            ModelLayerRange(layerId="decoder", startLayer=5, endLayer=7),
        ],
        [
            ModelLayerRange(layerId="encoder", startLayer=0, endLayer=4),
            ModelLayerRange(layerId="decoder", startLayer=4, endLayer=7),
        ],
    ],
)
def test_model_partition_plan_rejects_layer_gaps_and_overlaps(layers) -> None:
    with pytest.raises(ValueError, match="contiguous"):
        ModelPartitionPlan(
            planId="invalid-plan",
            modelId="vision-model",
            layers=layers,
            placements={"encoder": "edge-01", "decoder": "cloud-01"},
            tensorBoundaries=[TensorBoundaryContract(
                tensorName="hidden",
                fromLayer="encoder",
                toLayer="decoder",
                dtype="float16",
                shape=[1, 2],
            )],
        )


def test_model_partition_execution_fails_explicitly_until_executor_exists() -> None:
    with pytest.raises(ModelPartitionUnavailableError, match="MODEL_PARTITION_UNAVAILABLE") as caught:
        ModelPartitionService().execute(_valid_plan(), {"input": "x"})

    assert caught.value.code == "MODEL_PARTITION_UNAVAILABLE"
