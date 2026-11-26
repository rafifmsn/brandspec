"""Pydantic schema for seamless tiling SVG patterns."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...core.grid import GridSpec
from ..mark.schema import LayerSpec


class PatternSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str = "pattern"
    tile_width: float = Field(gt=0.5)
    tile_height: float = Field(gt=0.5)
    unit: float = Field(default=40.0, gt=1.0)
    grid: GridSpec = Field(default_factory=GridSpec)
    layers: list[LayerSpec] = Field(min_length=1)
    precision: int = Field(default=2, ge=0, le=5)
