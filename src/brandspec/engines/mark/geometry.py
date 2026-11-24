"""Constructive geometry shape builders for the mark engine."""

from __future__ import annotations

import math

import pathops

from ...core.grid import GridSpec, Point2D, grid_to_xy
from ...core.paths import add_rounded_polygon, circle_path
from .fields import build_halftone_grid, build_line_screen, build_radial_blades
from .schema import (
    ArcBandShape,
    CircleShape,
    GridPathShape,
    HalftoneGridShape,
    LineScreenShape,
    PolygonShape,
    RadialBladesShape,
    RectShape,
    RingShape,
    ShapeSpec,
)

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


def _arc_point(cx: float, cy: float, r: float, deg: float) -> Point2D:
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
    start_pt = _arc_point(cx, cy, r, shape.start_deg)
    end_pt = _arc_point(cx, cy, r, shape.end_deg)
    large_arc = pathops.ArcSize.LARGE if abs(sweep_deg) > 180.0 else pathops.ArcSize.SMALL
    direction = pathops.Direction.CW if sweep_deg >= 0 else pathops.Direction.CCW

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
        out = p.transform(1, 0, 0, 1, cx, cy)
        return pathops.simplify(out, fix_winding=True)

    if isinstance(shape, LineScreenShape):
        return build_line_screen(shape, grid, unit)

    if isinstance(shape, RadialBladesShape):
        return build_radial_blades(shape, grid, unit)

    if isinstance(shape, HalftoneGridShape):
        return build_halftone_grid(shape, grid, unit)

    raise ValueError(f"Unsupported shape type: {type(shape)}")
