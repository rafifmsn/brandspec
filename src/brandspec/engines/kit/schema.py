"""Pydantic schema for export kit specifications and optional root brand manifest."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class KitSpec(BaseModel):
    schemaVersion: Literal[1] = 1
    brand_name: str
    tagline: str = ""
    mark_svg: str | None = None
    mark_spec: str | None = None
    tokens_spec: str | None = None
    og_size: tuple[int, int] = (1200, 630)
    pwa_padding: float = Field(default=0.22, ge=0.20, le=0.40)

    @model_validator(mode="after")
    def _require_mark_source(self) -> "KitSpec":
        if not self.mark_svg and not self.mark_spec:
            raise ValueError("KitSpec requires either mark_svg or mark_spec.")
        return self


class BrandManifest(BaseModel):
    schemaVersion: Literal[1] = 1
    name: str
    mark: str | None = None
    tokens: str | None = None
    wordmark: str | None = None
    lockup: str | None = None
    kit: str | None = None
    icons: str | None = None
    pattern: str | None = None
