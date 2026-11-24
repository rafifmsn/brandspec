"""Boolean compilation, symmetry operators, optical normalization, and SVG serialization."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
import pathops
from PIL import Image
import resvg_py

from .geometry import build_shape, dilate_path
from .grid import grid_overlay_svg
from .schema import LayerSpec, LogoSpec, SymmetrySpec


@dataclass(frozen=True)
class CompiledLogo:
    spec: LogoSpec
    path: pathops.Path
    svg_d: str
    svg_markup: str
    overlay_svg_markup: str
    affine: tuple[float, float, float, float, float, float]
    contour_count: int


def _fmt(value: float, precision: int) -> str:
    rounded = round(value, precision)
    if abs(rounded) < 10 ** (-precision):
        rounded = 0.0
    text = f"{rounded:.{precision}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def path_to_svg_d(path: pathops.Path, precision: int = 2) -> str:
    """Serialize a pathops.Path to a canonical SVG path d string."""
    parts: list[str] = []
    for verb, pts in path.segments:
        if verb == "moveTo":
            x, y = pts[0]
            parts.append(f"M {_fmt(x, precision)} {_fmt(y, precision)}")
        elif verb == "lineTo":
            x, y = pts[0]
            parts.append(f"L {_fmt(x, precision)} {_fmt(y, precision)}")
        elif verb == "qCurveTo":
            if len(pts) == 2:
                (x1, y1), (x2, y2) = pts
                parts.append(
                    f"Q {_fmt(x1, precision)} {_fmt(y1, precision)} "
                    f"{_fmt(x2, precision)} {_fmt(y2, precision)}"
                )
            elif len(pts) > 2:
                for i in range(len(pts) - 2):
                    cx, cy = pts[i]
                    nx, ny = pts[i + 1]
                    mx, my = 0.5 * (cx + nx), 0.5 * (cy + ny)
                    parts.append(
                        f"Q {_fmt(cx, precision)} {_fmt(cy, precision)} "
                        f"{_fmt(mx, precision)} {_fmt(my, precision)}"
                    )
                (x1, y1), (x2, y2) = pts[-2], pts[-1]
                parts.append(
                    f"Q {_fmt(x1, precision)} {_fmt(y1, precision)} "
                    f"{_fmt(x2, precision)} {_fmt(y2, precision)}"
                )
        elif verb == "curveTo":
            (x1, y1), (x2, y2), (x3, y3) = pts
            parts.append(
                f"C {_fmt(x1, precision)} {_fmt(y1, precision)} "
                f"{_fmt(x2, precision)} {_fmt(y2, precision)} "
                f"{_fmt(x3, precision)} {_fmt(y3, precision)}"
            )
        elif verb == "closePath":
            parts.append("Z")
    return " ".join(parts)


def apply_symmetry(path: pathops.Path, sym: SymmetrySpec | None, unit: float) -> pathops.Path:
    """Apply geometric symmetry transformation to a compiled path."""
    if sym is None or sym.type == "none":
        return path

    builder = pathops.OpBuilder()
    if sym.type == "mirror_x":
        dx = sym.offset * unit
        builder.add(path, pathops.PathOp.UNION)
        builder.add(path.transform(-1, 0, 0, 1, dx, 0), pathops.PathOp.UNION)
    elif sym.type == "mirror_y":
        dy = sym.offset * unit
        builder.add(path, pathops.PathOp.UNION)
        builder.add(path.transform(1, 0, 0, -1, 0, dy), pathops.PathOp.UNION)
    elif sym.type == "mirror_xy":
        builder.add(path, pathops.PathOp.UNION)
        builder.add(path.transform(-1, 0, 0, 1, 0, 0), pathops.PathOp.UNION)
        builder.add(path.transform(1, 0, 0, -1, 0, 0), pathops.PathOp.UNION)
        builder.add(path.transform(-1, 0, 0, -1, 0, 0), pathops.PathOp.UNION)
    elif sym.type == "rotate":
        step = sym.step_deg if sym.step_deg is not None else (360.0 / sym.count)
        for k in range(sym.count):
            rad = math.radians(k * step)
            scale = sym.scale_step**k
            ca = math.cos(rad) * scale
            sa = math.sin(rad) * scale
            builder.add(path.transform(ca, sa, -sa, ca, 0, 0), pathops.PathOp.UNION)
    elif sym.type == "glide_x":
        dx = (sym.offset if abs(sym.offset) > 1e-6 else 2.0) * unit
        for k in range(sym.count):
            sy = -1.0 if k % 2 == 1 else 1.0
            builder.add(path.transform(1, 0, 0, sy, k * dx, 0), pathops.PathOp.UNION)

    out = builder.resolve()
    out.convertConicsToQuads(0.05)
    return pathops.simplify(out, fix_winding=True)


def _union_shapes(shapes: list, spec: LogoSpec) -> pathops.Path:
    builder = pathops.OpBuilder()
    for s in shapes:
        builder.add(build_shape(s, spec.grid, spec.unit), pathops.PathOp.UNION)
    out = builder.resolve()
    out.convertConicsToQuads(0.05)
    return pathops.simplify(out, fix_winding=True)


def _compile_layer(layer: LayerSpec, spec: LogoSpec) -> pathops.Path:
    layer_path = _union_shapes(layer.shapes, spec)
    if layer.clip_to:
        clip_path = _union_shapes(layer.clip_to, spec)
        layer_path = pathops.op(layer_path, clip_path, pathops.PathOp.INTERSECTION)
    if layer.symmetry is not None:
        layer_path = apply_symmetry(layer_path, layer.symmetry, spec.unit)
    layer_path.convertConicsToQuads(0.05)
    return pathops.simplify(layer_path, fix_winding=True)


def _render_svg_doc(
    svg_d: str,
    canvas_size: int,
    fill: str = "#000000",
    background: str | None = None,
    extra_before: str = "",
    title: str = "",
) -> str:
    bg = f'<rect width="{canvas_size}" height="{canvas_size}" fill="{background}"/>' if background else ""
    title_el = f"<title>{title}</title>" if title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {canvas_size} {canvas_size}" '
        f'width="{canvas_size}" height="{canvas_size}">'
        f"{title_el}{bg}{extra_before}"
        f'<path d="{svg_d}" fill="{fill}" fill-rule="nonzero"/>'
        f"</svg>"
    )


def _compute_optical_nudge(svg_d: str, canvas_size: int, max_nudge: float) -> tuple[float, float]:
    sample_size = 200
    svg_doc = _render_svg_doc(svg_d, canvas_size, fill="#000000", background="#ffffff")
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


def compile_spec(spec: LogoSpec) -> CompiledLogo:
    """Compile a validated LogoSpec into normalized vector paths and SVGs."""
    acc: pathops.Path | None = None
    for layer in spec.layers:
        layer_path = _compile_layer(layer, spec)
        if acc is None:
            acc = layer_path
            continue

        if layer.op == "unite":
            if layer.halo > 0.0:
                carve = dilate_path(layer_path, layer.halo * spec.unit)
                acc = pathops.op(acc, carve, pathops.PathOp.DIFFERENCE)
            acc = pathops.op(acc, layer_path, pathops.PathOp.UNION)
        elif layer.op == "subtract":
            target = dilate_path(layer_path, layer.halo * spec.unit) if layer.halo > 0.0 else layer_path
            acc = pathops.op(acc, target, pathops.PathOp.DIFFERENCE)
        elif layer.op == "intersect":
            acc = pathops.op(acc, layer_path, pathops.PathOp.INTERSECTION)
        elif layer.op == "xor":
            acc = pathops.op(acc, layer_path, pathops.PathOp.XOR)

    assert acc is not None
    acc = apply_symmetry(acc, spec.symmetry, spec.unit)

    if spec.post.invert:
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

    bounds = acc.bounds
    if bounds is None:
        raise ValueError("Compiled geometry is empty after boolean operations.")
    min_x, min_y, max_x, max_y = bounds
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
    svg_markup = _render_svg_doc(svg_d, canvas, fill="#000000", title=spec.name)
    grid_svg = grid_overlay_svg(spec.grid, spec.unit, affine, canvas)
    overlay_svg_markup = _render_svg_doc(
        svg_d,
        canvas,
        fill="#111111",
        background="#ffffff",
        extra_before=grid_svg,
        title=f"{spec.name} (construction grid)",
    )
    contour_count = len(list(norm_path.contours))

    return CompiledLogo(
        spec=spec,
        path=norm_path,
        svg_d=svg_d,
        svg_markup=svg_markup,
        overlay_svg_markup=overlay_svg_markup,
        affine=affine,
        contour_count=contour_count,
    )
