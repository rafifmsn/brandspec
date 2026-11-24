"""Rasterization, 4-panel visual inspection sheet, and deterministic quality metrics."""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageDraw
import resvg_py

from .compiler import CompiledLogo, _render_svg_doc


@dataclass(frozen=True)
class QualityMetrics:
    ink_ratio: float
    ink_ratio_24px: float
    bbox_aspect: float
    island_count: int
    tiny_island_count: int
    contour_count: int
    optical_drift_pct: float
    warnings: list[str]
    passed: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _rasterize(svg_str: str, size: int, background: str | None = "#ffffff") -> Image.Image:
    png_bytes = resvg_py.svg_to_bytes(
        svg_string=svg_str,
        width=size,
        height=size,
        background=background,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def _count_islands(mask: np.ndarray) -> tuple[int, int]:
    """Count 4-connected foreground islands and micro-speck islands (<0.15% pixels)."""
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    min_speck = max(4, int(0.0015 * h * w))
    total = 0
    tiny = 0

    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if visited[sy, sx]:
            continue
        total += 1
        area = 0
        stack = [(sy, sx)]
        visited[sy, sx] = True
        while stack:
            cy, cx = stack.pop()
            area += 1
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        if area < min_speck:
            tiny += 1

    return total, tiny


def analyze_compiled(compiled: CompiledLogo) -> QualityMetrics:
    """Compute geometric & visual quality metrics directly from rasterized output."""
    canvas = compiled.spec.post.canvas_size
    pos_img = _rasterize(compiled.svg_markup, 240, background="#ffffff").convert("L")
    arr = np.asarray(pos_img)
    ink = arr < 128

    ys, xs = np.nonzero(ink)
    if len(xs) == 0:
        return QualityMetrics(
            ink_ratio=0.0,
            ink_ratio_24px=0.0,
            bbox_aspect=0.0,
            island_count=0,
            tiny_island_count=0,
            contour_count=compiled.contour_count,
            optical_drift_pct=100.0,
            warnings=["Empty raster output"],
            passed=False,
        )

    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    bbox_ink = float(np.mean(ink[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]))
    aspect = round(max(bw, bh) / max(1, min(bw, bh)), 2)

    cx_ink = float(np.mean(xs)) / 240.0
    cy_ink = float(np.mean(ys)) / 240.0
    drift = float(np.hypot(cx_ink - 0.5, cy_ink - 0.5) * 100.0)

    islands, tiny = _count_islands(ink)

    img_24 = _rasterize(compiled.svg_markup, 24, background="#ffffff").convert("L")
    arr_24 = np.asarray(img_24)
    ink_24 = float(np.mean(arr_24 < 160))

    warnings: list[str] = []
    if bbox_ink < 0.16:
        warnings.append(f"Too sparse inside bounding box (ink={bbox_ink:.2f} < 0.16)")
    if bbox_ink > 0.72:
        warnings.append(f"Too heavy inside bounding box (ink={bbox_ink:.2f} > 0.72)")
    if tiny > 0:
        warnings.append(f"Detected {tiny} tiny sliver/speck island(s)")
    if ink_24 < 0.06:
        warnings.append(f"Lines nearly vanish at 24px (ink_24={ink_24:.2f})")
    if ink_24 > 0.74:
        warnings.append(f"Negative space collapses at 24px (ink_24={ink_24:.2f})")
    if aspect > 2.6:
        warnings.append(f"Extreme aspect ratio ({aspect:.2f}) weakens compact mark legibility")

    return QualityMetrics(
        ink_ratio=round(bbox_ink, 3),
        ink_ratio_24px=round(ink_24, 3),
        bbox_aspect=aspect,
        island_count=islands,
        tiny_island_count=tiny,
        contour_count=compiled.contour_count,
        optical_drift_pct=round(drift, 2),
        warnings=warnings,
        passed=len(warnings) == 0,
    )


def render_inspection_sheet(compiled: CompiledLogo) -> Image.Image:
    """Build a 4-panel visual inspection sheet (grid, positive, inverted, scale strip)."""
    canvas_size = compiled.spec.post.canvas_size
    panel_size = 400
    pad = 24
    header_h = 36

    p1 = _rasterize(compiled.overlay_svg_markup, panel_size, background="#ffffff")
    p2 = _rasterize(compiled.svg_markup, panel_size, background="#ffffff")

    inv_svg = _render_svg_doc(
        compiled.svg_d,
        canvas_size,
        fill="#ffffff",
        background="#111111",
    )
    p3 = _rasterize(inv_svg, panel_size, background="#111111")

    strip = Image.new("RGB", (panel_size, panel_size), (245, 246, 248))
    s96 = _rasterize(compiled.svg_markup, 96, background="#ffffff")
    s48 = _rasterize(compiled.svg_markup, 48, background="#ffffff")
    s24 = _rasterize(compiled.svg_markup, 24, background="#ffffff")

    strip.paste(s96, (48, 84))
    strip.paste(s48, (188, 108))
    strip.paste(s24, (276, 120))

    s96_inv = _rasterize(inv_svg, 96, background="#111111")
    s48_inv = _rasterize(inv_svg, 48, background="#111111")
    s24_inv = _rasterize(inv_svg, 24, background="#111111")

    strip.paste(s96_inv, (48, 224))
    strip.paste(s48_inv, (188, 248))
    strip.paste(s24_inv, (276, 260))

    total_w = pad * 3 + panel_size * 2
    total_h = header_h + pad * 3 + panel_size * 2
    sheet = Image.new("RGB", (total_w, total_h), (236, 239, 244))
    draw = ImageDraw.Draw(sheet)

    draw.text(
        (pad, 12),
        f"{compiled.spec.name}  |  {compiled.spec.category}  |  grid={compiled.spec.grid.type}",
        fill=(25, 28, 32),
    )

    positions = [
        (pad, header_h + pad, p1, "1. Construction Grid"),
        (pad * 2 + panel_size, header_h + pad, p2, "2. Positive (400px)"),
        (pad, header_h + pad * 2 + panel_size, p3, "3. Inverted (400px)"),
        (pad * 2 + panel_size, header_h + pad * 2 + panel_size, strip, "4. Scale Test (96 / 48 / 24px)"),
    ]
    for x, y, img, label in positions:
        sheet.paste(img, (x, y))
        draw.rectangle([x, y, x + panel_size - 1, y + panel_size - 1], outline=(200, 206, 214))
        draw.text((x + 8, y + 6), label, fill=(100, 110, 125))

    return sheet
