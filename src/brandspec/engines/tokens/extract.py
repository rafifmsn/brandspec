"""Pure-Python Pillow/numpy palette extractor for reference brand images."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .contrast import relative_luminance, wcag_contrast_ratio
from .schema import TokensSpec


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _chroma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    return max(r, g, b) - min(r, g, b)


def extract_palette_colors(image_path: Path, colors: int = 6) -> list[str]:
    """Deterministically quantize an image into sorted hex colors."""
    if colors < 2 or colors > 16:
        raise ValueError(f"colors must be between 2 and 16 (got {colors})")

    with Image.open(image_path) as img:
        rgb_img = img.convert("RGB")
        rgb_img.thumbnail((160, 160), Image.Resampling.LANCZOS)
        arr = np.asarray(rgb_img).reshape(-1, 3)

    unique_rows = np.unique(arr, axis=0)
    if len(unique_rows) <= colors:
        palette_rgb = [tuple(int(c) for c in row) for row in unique_rows]
    else:
        quantized = rgb_img.quantize(
            colors=colors,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        raw_pal = quantized.getpalette() or []
        used_indices = sorted({int(idx) for idx in quantized.getdata()})
        palette_rgb = [
            (int(raw_pal[3 * idx]), int(raw_pal[3 * idx + 1]), int(raw_pal[3 * idx + 2]))
            for idx in used_indices
            if 3 * idx + 2 < len(raw_pal)
        ]

    palette_hex = sorted(
        {_rgb_to_hex(rgb) for rgb in palette_rgb},
        key=lambda hx: (relative_luminance(hx), _chroma(_hex_tuple(hx)), hx),
    )
    return palette_hex


def _hex_tuple(hx: str) -> tuple[int, int, int]:
    c = hx.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _ensure_contrast(candidates: list[str], bg: str, min_ratio: float, fallback: str) -> str:
    for c in candidates:
        if wcag_contrast_ratio(c, bg) >= min_ratio:
            return c
    if wcag_contrast_ratio(fallback, bg) >= min_ratio:
        return fallback
    return "#ffffff" if wcag_contrast_ratio("#ffffff", bg) >= wcag_contrast_ratio("#000000", bg) else "#000000"


def extract_tokens_from_image(
    image_path: Path,
    colors: int = 6,
    name: str | None = None,
) -> dict[str, Any]:
    """Extract a contrast-safe TokensSpec dictionary plus raw palette from an image."""
    palette = extract_palette_colors(image_path, colors=colors)
    dark_neutrals = [
        c for c in palette if relative_luminance(c) < 0.2 and _chroma(_hex_tuple(c)) < 0.15
    ]
    bg_canvas = dark_neutrals[0] if dark_neutrals else "#0b0c0e"
    bg_surface = dark_neutrals[1] if len(dark_neutrals) > 1 else "#121316"
    border = "#26282e"

    text_primary = _ensure_contrast(list(reversed(palette)), bg_surface, 4.5, "#f3f4f6")
    text_secondary = _ensure_contrast(
        [c for c in reversed(palette) if c != text_primary],
        bg_surface,
        4.5,
        "#d1d5db",
    )
    mark_light = _ensure_contrast(palette, "#ffffff", 3.0, "#111111")
    mark_dark = _ensure_contrast(list(reversed(palette)), bg_canvas, 3.0, "#f3f4f6")

    chromatic = [c for c in palette if _chroma(_hex_tuple(c)) >= 0.08]
    accent: str | None = None
    if chromatic:
        best = max(chromatic, key=lambda c: (_chroma(_hex_tuple(c)), wcag_contrast_ratio(c, bg_surface)))
        if wcag_contrast_ratio(best, bg_surface) >= 3.0:
            accent = best

    spec = TokensSpec(
        name=name or image_path.stem,
        bg_canvas=bg_canvas,
        bg_surface=bg_surface,
        border=border,
        text_primary=text_primary,
        text_secondary=text_secondary,
        mark_light=mark_light,
        mark_dark=mark_dark,
        accent=accent,
    )
    out = spec.model_dump(mode="json")
    out["extracted_palette"] = palette
    return out
