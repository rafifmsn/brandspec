"""Boolean layer compilation, optical normalization, and SVG generation for marks."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pathops
from PIL import Image
import resvg_py

from ...core.grid import GridSpec, grid_overlay_svg
from ...core.paths import SymmetrySpec, apply_symmetry, dilate_path, path_to_svg_d, render_svg_doc
from .geometry import build_shape
from .schema import LayerSpec, MarkSpec


@dataclass(frozen=True)
class CompiledMark:
    spec: MarkSpec
    path: pathops.Path
    svg_d: str
    svg_markup: str
    overlay_svg_markup: str
    affine: tuple[float, float, float, float, float, float]
    contour_count: int


CompiledLogo = CompiledMark


def _union_shapes(shapes: list, grid: GridSpec, unit: float) -> pathops.Path:
    builder = pathops.OpBuilder()
    for s in shapes:
        builder.add(build_shape(s, grid, unit), pathops.PathOp.UNION)
    out = builder.resolve()
    out.convertConicsToQuads(0.05)
    return pathops.simplify(out, fix_winding=True)


def _compile_layer(layer: LayerSpec, grid: GridSpec, unit: float) -> pathops.Path:
    layer_path = _union_shapes(layer.shapes, grid, unit)
    if layer.clip_to:
        clip_path = _union_shapes(layer.clip_to, grid, unit)
        layer_path = pathops.op(layer_path, clip_path, pathops.PathOp.INTERSECTION)
    if layer.symmetry is not None:
        layer_path = apply_symmetry(layer_path, layer.symmetry, unit)
    layer_path.convertConicsToQuads(0.05)
    return pathops.simplify(layer_path, fix_winding=True)


def _merge_parts(parts: dict[str, pathops.Path]) -> pathops.Path:
    builder = pathops.OpBuilder()
    for part in parts.values():
        builder.add(part, pathops.PathOp.UNION)
    out = builder.resolve()
    out.convertConicsToQuads(0.05)
    return pathops.simplify(out, fix_winding=True)


def compile_layers(
    layers: list[LayerSpec],
    grid: GridSpec,
    unit: float,
    symmetry: SymmetrySpec | None = None,
) -> pathops.Path:
    """Compile boolean layers on a grid into a simplified design-space path."""
    parts: dict[str, pathops.Path] = {}
    for layer in layers:
        layer_path = _compile_layer(layer, grid, unit)
        if not parts:
            parts[layer.id] = layer_path
            continue

        if layer.op == "unite":
            if layer.halo > 0.0:
                carve = dilate_path(
                    layer_path,
                    layer.halo * unit,
                    join=layer.halo_join,
                    cap=layer.halo_cap,
                )
                targets = list(parts.keys()) if layer.halo_targets is None else layer.halo_targets
                for tid in targets:
                    if tid not in parts:
                        raise ValueError(
                            f"Unknown halo_target '{tid}' in layer '{layer.id}'"
                        )
                    parts[tid] = pathops.op(parts[tid], carve, pathops.PathOp.DIFFERENCE)
            parts[layer.id] = layer_path
        elif layer.op == "subtract":
            target = (
                dilate_path(
                    layer_path,
                    layer.halo * unit,
                    join=layer.halo_join,
                    cap=layer.halo_cap,
                )
                if layer.halo > 0.0
                else layer_path
            )
            targets = list(parts.keys()) if layer.halo_targets is None else layer.halo_targets
            for tid in targets:
                if tid not in parts:
                    raise ValueError(
                        f"Unknown halo_target '{tid}' in layer '{layer.id}'"
                    )
                parts[tid] = pathops.op(parts[tid], target, pathops.PathOp.DIFFERENCE)
        elif layer.op == "intersect":
            merged = _merge_parts(parts)
            parts = {"__acc__": pathops.op(merged, layer_path, pathops.PathOp.INTERSECTION)}
        elif layer.op == "xor":
            merged = _merge_parts(parts)
            parts = {"__acc__": pathops.op(merged, layer_path, pathops.PathOp.XOR)}

    acc = _merge_parts(parts)
    acc = apply_symmetry(acc, symmetry, unit)
    acc.convertConicsToQuads(0.05)
    return pathops.simplify(acc, fix_winding=True)


def _compute_optical_nudge(svg_d: str, canvas_size: int, max_nudge: float) -> tuple[float, float]:
    sample_size = 200
    svg_doc = render_svg_doc(svg_d, canvas_size, fill="#000000", background="#ffffff")
    png_bytes = resvg_py.svg_to_bytes(svg_string=svg_doc, width=sample_size, height=sample_size)
    arr = np.asarray(Image.open(io.BytesIO(png_bytes)).convert("L"))
    ink = arr < 128
    if not np.any(ink):
        return (0.0, 0.0)
    ys, xs = np.nonzero(ink)
    cx = float(np.mean(xs)) * (canvas_size / sample_size)
    cy = float(np.mean(ys)) * (canvas_size / sample_size)
    target = 0.5 * canvas_size
    dx = max(-max_nudge, min(max_nudge, target - cx))
    dy = max(-max_nudge, min(max_nudge, target - cy))
    return (dx, dy)


def compile_mark_design_path(spec: MarkSpec) -> pathops.Path:
    """Compile a MarkSpec into its un-normalized centered design-space path."""
    acc = compile_layers(spec.layers, spec.grid, spec.unit, spec.symmetry)

    if spec.post.invert and acc.bounds is not None:
        x0, y0, x1, y1 = acc.bounds
        margin = spec.unit
        frame = pathops.Path()
        frame.moveTo(x0 - margin, y0 - margin)
        frame.lineTo(x1 + margin, y0 - margin)
        frame.lineTo(x1 + margin, y1 + margin)
        frame.lineTo(x0 - margin, y1 + margin)
        frame.close()
        acc = pathops.op(frame, acc, pathops.PathOp.DIFFERENCE)
        acc.convertConicsToQuads(0.05)
        acc = pathops.simplify(acc, fix_winding=True)

    if acc.bounds is None or len(list(acc.contours)) == 0:
        raise ValueError("Compiled geometry is empty after boolean operations.")
    return acc


def compile_spec(spec: MarkSpec) -> CompiledMark:
    """Compile a validated MarkSpec into normalized vector paths and SVGs."""
    acc = compile_mark_design_path(spec)
    min_x, min_y, max_x, max_y = acc.bounds
    w = max(max_x - min_x, 1e-6)
    h = max(max_y - min_y, 1e-6)

    canvas = spec.post.canvas_size
    usable = max(10.0, canvas - 2.0 * spec.post.padding)
    scale = usable / max(w, h)
    cx_src = 0.5 * (min_x + max_x)
    cy_src = 0.5 * (min_y + max_y)
    tx = 0.5 * canvas - scale * cx_src
    ty = 0.5 * canvas - scale * cy_src

    affine = (scale, 0.0, 0.0, scale, tx, ty)
    norm_path = acc.transform(*affine)
    norm_path.convertConicsToQuads(0.05)
    norm_path = pathops.simplify(norm_path, fix_winding=True)

    if spec.post.optical_center:
        draft_d = path_to_svg_d(norm_path, spec.post.precision)
        dx, dy = _compute_optical_nudge(draft_d, canvas, spec.post.padding * 0.45)
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            affine = (scale, 0.0, 0.0, scale, tx + dx, ty + dy)
            norm_path = norm_path.transform(1.0, 0.0, 0.0, 1.0, dx, dy)
            norm_path.convertConicsToQuads(0.05)
            norm_path = pathops.simplify(norm_path, fix_winding=True)

    svg_d = path_to_svg_d(norm_path, spec.post.precision)
    svg_markup = render_svg_doc(svg_d, canvas, fill=spec.post.fill, title=spec.name)
    grid_svg = grid_overlay_svg(spec.grid, spec.unit, affine, canvas)
    overlay_svg_markup = render_svg_doc(
        svg_d,
        canvas,
        fill="#111111",
        background="#ffffff",
        extra_before=grid_svg,
        title=f"{spec.name} (construction grid)",
    )
    contour_count = len(list(norm_path.contours))

    return CompiledMark(
        spec=spec,
        path=norm_path,
        svg_d=svg_d,
        svg_markup=svg_markup,
        overlay_svg_markup=overlay_svg_markup,
        affine=affine,
        contour_count=contour_count,
    )
