"""Pydantic schemas for deterministic perspective mockup templates."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SlotStyle = Literal[
    "mark_only",
    "billboard_split",
    "card_editorial",
    "card_minimal",
    "banner_vertical",
    "hoarding_panel_left",
    "hoarding_panel_mid",
    "hoarding_panel_right",
    "phone_splash",
    "box_seal",
]

BlendMode = Literal["multiply", "luminance_transfer", "screen", "normal"]


class MockupSlot(BaseModel):
    id: str
    quad: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    design_size: tuple[int, int]
    template_style: SlotStyle = "mark_only"
    blend_mode: BlendMode = "luminance_transfer"
    opacity: float = Field(default=0.96, ge=0.0, le=1.0)
    corner_radius: int = Field(default=0, ge=0)


class MockupManifest(BaseModel):
    schemaVersion: Literal[1] = 1
    id: str
    title: str
    category: Literal["outdoor", "print", "packaging", "digital"]
    background: str = "background.jpg"
    slots: list[MockupSlot] = Field(min_length=1)
