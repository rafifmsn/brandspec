"""Shared Skia path builders, corner fillets, halo dilation, symmetry, and SVG serialization."""

from __future__ import annotations

import math
from typing import Literal

import pathops
from pydantic import BaseModel, Field

from .grid import Point2D

KAPPA = 0.5522847498307936


class SymmetrySpec(BaseModel):
    type: Literal[
        "none",
        "mirror_x",
        "mirror_y",
        "mirror_xy",
        "rotate",
        "glide_x",
    ] = "none"
    count: int = Field(default=4, ge=2, le=36)
    step_deg: float | None = None
    scale_step: float = Field(default=1.0, gt=0.1, le=2.0)
    offset: float = 0.0


class PostProcessSpec(BaseModel):
    canvas_size: int = Field(default=1000, ge=256, le=4096)
    padding: float = Field(default=100.0, ge=0.0)
    optical_center: bool = True
    invert: bool = False
    precision: int = Field(default=2, ge=0, le=5)


def circle_path(cx: float, cy: float, radius: float) -> pathops.Path:
    """Create an exact 4-cubic circle path."""
    k = radius * KAPPA
    p = pathops.Path()
    p.moveTo(cx, cy - radius)
    p.cubicTo(cx + k, cy - radius, cx + radius, cy - k, cx + radius, cy)
    p.cubicTo(cx + radius, cy + k, cx + k, cy + radius, cx, cy + radius)
    p.cubicTo(cx - k, cy + radius, cx - radius, cy + k, cx - radius, cy)
    p.cubicTo(cx - radius, cy - k, cx - k, cy - radius, cx, cy - radius)
    p.close()
    return p


def add_rounded_polygon(
    pts: list[Point2D],
    closed: bool,
    corner_radius: float,
) -> pathops.Path:
    """Trace a polyline or polygon with exact cubic Bezier corner fillets."""
    p = pathops.Path()
    n = len(pts)
    if n < 2:
        return p

    if corner_radius <= 1e-6 or n < 3:
        p.moveTo(*pts[0])
        for x, y in pts[1:]:
            p.lineTo(x, y)
        if closed:
            p.close()
        return p

    def seg_unit(a: Point2D, b: Point2D) -> tuple[float, float, float]:
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        return (dx / d, dy / d, d) if d > 1e-9 else (0.0, 0.0, 0.0)

    fillets: dict[int, tuple[Point2D, Point2D, Point2D, Point2D]] = {}
    indices = range(n) if closed else range(1, n - 1)
    for i in indices:
        prev_pt = pts[(i - 1) % n]
        curr_pt = pts[i]
        next_pt = pts[(i + 1) % n]
        ux1, uy1, d1 = seg_unit(curr_pt, prev_pt)
        ux2, uy2, d2 = seg_unit(curr_pt, next_pt)
        if d1 < 1e-6 or d2 < 1e-6:
            continue
        dot = max(-1.0, min(1.0, ux1 * ux2 + uy1 * uy2))
        angle = math.acos(dot)
        if angle < 1e-4 or abs(angle - math.pi) < 1e-4:
            continue
        half_tan = math.tan(angle / 2.0)
        trim = min(corner_radius / half_tan, d1 * 0.45, d2 * 0.45)
        r_actual = trim * half_tan
        phi = math.pi - angle
        handle = r_actual * (4.0 / 3.0) * math.tan(phi / 4.0)
        p_in = (curr_pt[0] + ux1 * trim, curr_pt[1] + uy1 * trim)
        p_out = (curr_pt[0] + ux2 * trim, curr_pt[1] + uy2 * trim)
        c1 = (p_in[0] - ux1 * handle, p_in[1] - uy1 * handle)
        c2 = (p_out[0] - ux2 * handle, p_out[1] - uy2 * handle)
        fillets[i] = (p_in, c1, c2, p_out)

    if closed:
        start_pt = fillets[0][3] if 0 in fillets else pts[0]
        p.moveTo(*start_pt)
        for i in range(1, n + 1):
            idx = i % n
            if idx in fillets:
                p_in, c1, c2, p_out = fillets[idx]
                p.lineTo(*p_in)
                p.cubicTo(*c1, *c2, *p_out)
            else:
                p.lineTo(*pts[idx])
        p.close()
    else:
        p.moveTo(*pts[0])
        for i in range(1, n - 1):
            if i in fillets:
                p_in, c1, c2, p_out = fillets[i]
                p.lineTo(*p_in)
                p.cubicTo(*c1, *c2, *p_out)
            else:
                p.lineTo(*pts[i])
        p.lineTo(*pts[-1])

    return p


def dilate_path(path: pathops.Path, halo_radius: float) -> pathops.Path:
    """Expand a closed path outward by halo_radius for clean negative-space carving."""
    if halo_radius <= 1e-6:
        return path
    ring = pathops.Path()
    ring.addPath(path)
    ring.stroke(
        2.0 * halo_radius,
        pathops.LineCap.ROUND_CAP,
        pathops.LineJoin.ROUND_JOIN,
        4.0,
    )
    ring.convertConicsToQuads(0.05)
    ring = pathops.simplify(ring, fix_winding=True)
    return pathops.op(path, ring, pathops.PathOp.UNION)


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


def render_svg_doc(
    svg_d: str,
    canvas_size: int,
    fill: str = "#000000",
    background: str | None = None,
    extra_before: str = "",
    title: str = "",
) -> str:
    """Wrap an SVG path string into a standalone SVG document."""
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
