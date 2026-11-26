"""Pydantic schema for 24x24 matched icon set specifications."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..mark.schema import LayerSpec


class IconItemSpec(BaseModel):
    id: str
    layers: list[LayerSpec] = Field(min_length=1)


class IconSetSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str = "icon-set"
    inherits_mark: str | None = None
    viewbox_size: int = Field(default=24, ge=16, le=128)
    stroke_width: float = Field(default=2.0, gt=0.25, le=12.0)
    corner_radius: float = Field(default=0.0, ge=0.0)
    cap: Literal["butt", "round", "square"] = "butt"
    join: Literal["miter", "round", "bevel"] = "miter"
    precision: int = Field(default=2, ge=0, le=5)
    icons: list[IconItemSpec] = Field(min_length=1)
