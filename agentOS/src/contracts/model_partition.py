"""Independent contracts for neural-network layer partitioning."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


class ModelLayerRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    layer_id: StrictStr = Field(alias="layerId", min_length=1)
    start_layer: int = Field(alias="startLayer", ge=0)
    end_layer: int = Field(alias="endLayer", ge=0)

    @model_validator(mode="after")
    def range_is_forward(self) -> "ModelLayerRange":
        if self.end_layer < self.start_layer:
            raise ValueError("layer range must be forward")
        return self


class TensorBoundaryContract(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    tensor_name: StrictStr = Field(alias="tensorName", min_length=1)
    from_layer: StrictStr = Field(alias="fromLayer", min_length=1)
    to_layer: StrictStr = Field(alias="toLayer", min_length=1)
    dtype: StrictStr = Field(min_length=1)
    shape: list[int] = Field(min_length=1)

    @field_validator("shape")
    @classmethod
    def shape_is_positive(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value):
            raise ValueError("tensor boundary shape must be positive")
        return value

    @model_validator(mode="after")
    def endpoints_are_distinct(self) -> "TensorBoundaryContract":
        if self.from_layer == self.to_layer:
            raise ValueError("tensor boundary must connect two different layers")
        return self


class ModelPartitionPlan(BaseModel):
    """A complete ordered layer-to-resource partition, not a task placement."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)

    plan_id: StrictStr = Field(alias="planId", min_length=1)
    model_id: StrictStr = Field(alias="modelId", min_length=1)
    layers: list[ModelLayerRange] = Field(min_length=1)
    placements: dict[StrictStr, StrictStr] = Field(min_length=1)
    tensor_boundaries: list[TensorBoundaryContract] = Field(
        default_factory=list, alias="tensorBoundaries"
    )

    @model_validator(mode="after")
    def validate_partition(self) -> "ModelPartitionPlan":
        identifiers = [item.layer_id for item in self.layers]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("partition layer identifiers must be unique")
        if self.layers[0].start_layer != 0:
            raise ValueError("partition layers must start at layer zero")
        for previous, current in zip(self.layers, self.layers[1:]):
            if current.start_layer != previous.end_layer + 1:
                raise ValueError("partition layers must be contiguous without gaps or overlap")
        if set(self.placements) != set(identifiers):
            raise ValueError("partition must declare exactly one placement per layer")
        ranges = {item.layer_id: item for item in self.layers}
        for boundary in self.tensor_boundaries:
            if boundary.from_layer not in ranges or boundary.to_layer not in ranges:
                raise ValueError("tensor boundary references an unknown layer")
            source = ranges[boundary.from_layer]
            target = ranges[boundary.to_layer]
            if source.end_layer + 1 != target.start_layer:
                raise ValueError("tensor boundary must connect adjacent partition layers")
        return self


__all__ = ["ModelLayerRange", "ModelPartitionPlan", "TensorBoundaryContract"]
