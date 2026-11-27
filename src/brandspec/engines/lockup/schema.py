"""Pydantic schema for mark + wordmark lockup compositions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ...core.paths import FillSpec


class LockupSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str = "lockup"
    mark_spec: str
    wordmark_spec: str
    layout: Literal["horizontal", "stacked", "badge"] = "horizontal"
    gap_u: float = Field(default=1.0, ge=0.0, le=10.0)
    mark_scale: float = Field(default=1.0, gt=0.1, le=5.0)
    align: Literal["center", "baseline", "cap_height", "x_height", "optical_center"] = "center"
    offset_x_u: float = Field(default=0.0, ge=-5.0, le=5.0)
    offset_y_u: float = Field(default=0.0, ge=-5.0, le=5.0)
    fill: FillSpec | None = None
    mark_fill: FillSpec | None = None
    wordmark_fill: FillSpec | None = None
    clearspace_u: float = Field(default=1.0, gt=0.0, le=8.0)
    canvas_size: int = Field(default=1000, ge=256, le=4096)
    padding: float = Field(default=100.0, ge=0.0)
    precision: int = Field(default=2, ge=0, le=5)
