"""Periodic 3x3 wrap-around pattern compilation and SVG <pattern> export."""

from __future__ import annotations

from dataclasses import dataclass
from xml.sax.saxutils import escape

import pathops

from ...core.paths import path_to_svg_d
from ..mark.compiler import compile_layers
from .schema import PatternSpec


@dataclass(frozen=True)
class CompiledPattern:
    spec: PatternSpec
    tile_width_px: float
    tile_height_px: float
    path: pathops.Path
    svg_d: str
    tile_svg_markup: str
    pattern_svg_markup: str


def compile_pattern(spec: PatternSpec) -> CompiledPattern:
    """Compile a PatternSpec using 3x3 periodic replication clipped to [0, W] x [0, H]."""
    w_px = spec.tile_width * spec.unit
    h_px = spec.tile_height * spec.unit

    base_design = compile_layers(spec.layers, spec.grid, spec.unit)
    if base_design.bounds is None or len(list(base_design.contours)) == 0:
        raise ValueError("Pattern compiled to empty geometry.")
    centered = base_design.transform(1.0, 0.0, 0.0, 1.0, 0.5 * w_px, 0.5 * h_px)

    tiled_builder = pathops.OpBuilder()
    for dx in (-w_px, 0.0, w_px):
        for dy in (-h_px, 0.0, h_px):
            tiled_builder.add(
                centered.transform(1.0, 0.0, 0.0, 1.0, dx, dy),
                pathops.PathOp.UNION,
            )
    tiled = tiled_builder.resolve()

    clip_box = pathops.Path()
    clip_box.moveTo(0.0, 0.0)
    clip_box.lineTo(w_px, 0.0)
    clip_box.lineTo(w_px, h_px)
    clip_box.lineTo(0.0, h_px)
    clip_box.close()

    tile_path = pathops.op(tiled, clip_box, pathops.PathOp.INTERSECTION)
    tile_path.convertConicsToQuads(0.05)
    tile_path = pathops.simplify(tile_path, fix_winding=True)

    svg_d = path_to_svg_d(tile_path, spec.precision)
    title = escape(spec.name)
    w_str = f"{w_px:.2f}".rstrip("0").rstrip(".")
    h_str = f"{h_px:.2f}".rstrip("0").rstrip(".")

    tile_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w_str} {h_str}" width="{w_str}" height="{h_str}">'
        f"<title>{title}</title>"
        f'<path d="{svg_d}" fill="#000000" fill-rule="nonzero"/>'
        f"</svg>"
    )

    pat_id = "brandspec-tile"
    demo_w = f"{2.0 * w_px:.2f}".rstrip("0").rstrip(".")
    demo_h = f"{2.0 * h_px:.2f}".rstrip("0").rstrip(".")
    pattern_svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {demo_w} {demo_h}" width="{demo_w}" height="{demo_h}">'
        f"<title>{title} (tiled)</title>"
        f"<defs>"
        f'<pattern id="{pat_id}" width="{w_str}" height="{h_str}" patternUnits="userSpaceOnUse">'
        f'<path d="{svg_d}" fill="#000000" fill-rule="nonzero"/>'
        f"</pattern>"
        f"</defs>"
        f'<rect width="{demo_w}" height="{demo_h}" fill="url(#{pat_id})"/>'
        f"</svg>"
    )

    return CompiledPattern(
        spec=spec,
        tile_width_px=w_px,
        tile_height_px=h_px,
        path=tile_path,
        svg_d=svg_d,
        tile_svg_markup=tile_svg,
        pattern_svg_markup=pattern_svg,
    )
