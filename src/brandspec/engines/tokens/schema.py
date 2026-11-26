"""Pydantic schema for brand color tokens and semantic surface pairs."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_hex(value: str) -> str:
    if not HEX_RE.match(value):
        raise ValueError(f"Expected #RRGGBB hex color, got {value!r}")
    return value.lower()


HexColor = Annotated[str, AfterValidator(_validate_hex)]


class SurfacePair(BaseModel):
    fg: HexColor
    bg: HexColor
    role: Literal["text", "ui", "mark"] = "mark"


class TokensSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str = "brand-tokens"
    bg_canvas: HexColor = "#0b0c0e"
    bg_surface: HexColor = "#121316"
    border: HexColor = "#26282e"
    text_primary: HexColor = "#f3f4f6"
    text_secondary: HexColor = "#9ca3af"
    mark_light: HexColor = "#111111"
    mark_dark: HexColor = "#f3f4f6"
    accent: HexColor | None = None
    surfaces: dict[str, SurfacePair] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _populate_default_surfaces(self) -> "TokensSpec":
        defaults = {
            "light": SurfacePair(fg=self.mark_light, bg="#ffffff", role="mark"),
            "dark": SurfacePair(fg=self.mark_dark, bg=self.bg_canvas, role="mark"),
            "inverted": SurfacePair(fg=self.bg_canvas, bg=self.text_primary, role="mark"),
            "brand": SurfacePair(
                fg=self.accent if self.accent is not None else self.text_primary,
                bg=self.bg_surface,
                role="ui",
            ),
        }
        merged = dict(defaults)
        merged.update(self.surfaces)
        self.surfaces = merged
        return self
