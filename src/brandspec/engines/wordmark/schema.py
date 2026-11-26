"""Pydantic schema for vector wordmark specifications."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...core.paths import PostProcessSpec
from ..mark.schema import ShapeSpec


class InkTrapSpec(BaseModel):
    depth_u: float = Field(default=0.12, gt=0.0, le=1.0)
    width_u: float = Field(default=0.08, gt=0.0, le=1.0)
    angle_threshold_deg: float = Field(default=65.0, gt=5.0, lt=175.0)


class WordmarkSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str = "wordmark"
    text: str = Field(min_length=1)
    font_path: str
    case: Literal["as_is", "upper", "lower"] = "as_is"
    unit: float = Field(default=40.0, gt=1.0)
    em_units: float = Field(default=4.0, gt=0.5, le=20.0)
    tracking_em: float = 0.0
    kerning_pairs: dict[str, float] = Field(default_factory=dict)
    ink_trap: InkTrapSpec | None = None
    stencil_cuts: list[ShapeSpec] = Field(default_factory=list)
    post: PostProcessSpec = Field(default_factory=PostProcessSpec)
