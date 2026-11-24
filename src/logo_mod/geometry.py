"""Constructive geometry primitives, stroke expansion, and halo carving."""

from __future__ import annotations

import math

import pathops

from .fields import build_halftone_grid, build_line_screen, build_radial_blades
from .grid import grid_to_xy
from .schema import (
    ArcBandShape,
    CircleShape,
    GridPathShape,
    GridSpec,
    HalftoneGridShape,
    LineScreenShape,
    Point2D,
    PolygonShape,
    RadialBladesShape,
    RectShape,
    RingShape,
    ShapeSpec,
)

KAPPA = 0.5522847498307936

CAP_MAP = {
    "butt": pathops.LineCap.BUTT_CAP,
    "round": pathops.LineCap.ROUND_CAP,
    "square": pathops.LineCap.SQUARE_CAP,
}

JOIN_MAP = {
    "miter": pathops.LineJoin.MITER_JOIN,
    "round": pathops.LineJoin.ROUND_JOIN,
    "bevel": pathops.LineJoin.BEVEL_JOIN,
}


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
    """Trace a polyline or polygon with exact rational-arc corner fillets."""
    p = pathops.Path()
    n = len(pts)
    if n < 2:
        return p

    if corner_radius <= 1e-6 or n < (3 if not closed else 3):
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


def _stroke_and_simplify(
    path: pathops.Path,
    width: float,
    cap: str,
    join: str,
) -> pathops.Path:
    out = pathops.Path()
    out.addPath(path)
    out.stroke(width, CAP_MAP[cap], JOIN_MAP[join], 4.0)
    out.convertConicsToQuads(0.05)
    return pathops.simplify(out, fix_winding=True)


def _arc_points(cx: float, cy: float, r: float, deg: float) -> Point2D:
    rad = math.radians(deg)
    return (cx + r * math.sin(rad), cy - r * math.cos(rad))


def _build_arc_band(
    shape: ArcBandShape,
    grid: GridSpec,
    unit: float,
) -> pathops.Path:
    cx, cy = grid_to_xy(shape.center, grid, unit)
    r = shape.radius * unit
    sweep_deg = shape.end_deg - shape.start_deg
    if abs(sweep_deg) >= 359.999:
        outer = circle_path(cx, cy, r + (0.0 if shape.fill_sector else 0.5 * shape.width * unit))
        if shape.fill_sector:
            return outer
        inner_r = max(1e-3, r - 0.5 * shape.width * unit)
        return pathops.op(outer, circle_path(cx, cy, inner_r), pathops.PathOp.DIFFERENCE)

    p = pathops.Path()
    start_pt = _arc_points(cx, cy, r, shape.start_deg)
    end_pt = _arc_points(cx, cy, r, shape.end_deg)
    large_arc = (
        pathops.ArcSize.LARGE if abs(sweep_deg) > 180.0 else pathops.ArcSize.SMALL
    )
    direction = (
        pathops.Direction.CW
        if sweep_deg >= 0
        else pathops.Direction.CCW
    )

    if shape.fill_sector:
        p.moveTo(cx, cy)
        p.lineTo(*start_pt)
        p.arcTo(r, r, 0.0, large_arc, direction, *end_pt)
        p.close()
        p.convertConicsToQuads(0.05)
        return pathops.simplify(p, fix_winding=True)

    p.moveTo(*start_pt)
    p.arcTo(r, r, 0.0, large_arc, direction, *end_pt)
    return _stroke_and_simplify(p, shape.width * unit, shape.cap, "round")


def _rotate_translate(
    path: pathops.Path,
    angle_deg: float,
    cx: float,
    cy: float,
) -> pathops.Path:
    if abs(angle_deg) < 1e-6 and abs(cx) < 1e-6 and abs(cy) < 1e-6:
        return path
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    return path.transform(c, s, -s, c, cx, cy)


def build_shape(shape: ShapeSpec, grid: GridSpec, unit: float) -> pathops.Path:
    """Compile any ShapeSpec into a simplified filled pathops.Path."""
    if isinstance(shape, GridPathShape):
        pts = [grid_to_xy(pt, grid, unit) for pt in shape.points]
        p = add_rounded_polygon(pts, shape.closed, shape.corner_radius * unit)
        if shape.width <= 1e-6:
            if not shape.closed:
                p.close()
            return pathops.simplify(p, fix_winding=True)
        return _stroke_and_simplify(p, shape.width * unit, shape.cap, shape.join)

    if isinstance(shape, ArcBandShape):
        return _build_arc_band(shape, grid, unit)

    if isinstance(shape, CircleShape):
        cx, cy = grid_to_xy(shape.center, grid, unit)
        return circle_path(cx, cy, shape.radius * unit)

    if isinstance(shape, RingShape):
        if shape.inner_radius >= shape.outer_radius:
            raise ValueError("ring inner_radius must be less than outer_radius")
        cx, cy = grid_to_xy(shape.center, grid, unit)
        outer = circle_path(cx, cy, shape.outer_radius * unit)
        inner = circle_path(cx, cy, shape.inner_radius * unit)
        return pathops.op(outer, inner, pathops.PathOp.DIFFERENCE)

    if isinstance(shape, RectShape):
        cx, cy = grid_to_xy(shape.center, grid, unit)
        hw = 0.5 * shape.width * unit
        hh = 0.5 * shape.height * unit
        pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        local = add_rounded_polygon(pts, True, shape.corner_radius * unit)
        return pathops.simplify(_rotate_translate(local, shape.angle_deg, cx, cy), fix_winding=True)

    if isinstance(shape, PolygonShape):
        cx, cy = grid_to_xy(shape.center, grid, unit)
        r = shape.radius * unit
        pts: list[Point2D] = []
        for k in range(shape.sides):
            rad = math.radians(shape.angle_deg + k * (360.0 / shape.sides))
            pts.append((r * math.sin(rad), -r * math.cos(rad)))
        p = add_rounded_polygon(pts, True, shape.corner_radius * unit)
        p.moveTo if False else None
        out = p.transform(1, 0, 0, 1, cx, cy)
        return pathops.simplify(out, fix_winding=True)

    if isinstance(shape, LineScreenShape):
        return build_line_screen(shape, grid, unit)

    if isinstance(shape, RadialBladesShape):
        return build_radial_blades(shape, grid, unit)

    if isinstance(shape, HalftoneGridShape):
        return build_halftone_grid(shape, grid, unit)

    raise ValueError(f"Unsupported shape type: {type(shape)}")


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
