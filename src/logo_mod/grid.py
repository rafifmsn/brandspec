"""Coordinate system mappings and construction grid overlay generation."""

from __future__ import annotations

import math

from .schema import GridSpec, Point2D

COS_30 = math.cos(math.pi / 6.0)


def grid_to_xy(pt: Point2D, grid: GridSpec, unit: float) -> Point2D:
    """Convert grid coordinates into centered design-space XY coordinates."""
    a, b = pt
    if grid.type == "square":
        return (a * unit, b * unit)
    if grid.type == "isometric":
        x = a * unit * COS_30
        y = (b + 0.5 * a) * unit
        return (x, y)
    if grid.type == "polar":
        radius = a * unit
        rad = math.radians(b)
        return (radius * math.sin(rad), -radius * math.cos(rad))
    raise ValueError(f"Unsupported grid type: {grid.type}")


def grid_overlay_svg(
    grid: GridSpec,
    unit: float,
    affine: tuple[float, float, float, float, float, float],
    canvas_size: int,
) -> str:
    """Render faint construction grid lines transformed into final canvas coordinates."""
    sx, _, _, sy, tx, ty = affine
    half = grid.divisions // 2 + 1
    lines: list[str] = []

    def to_canvas(x: float, y: float) -> Point2D:
        return (x * sx + tx, y * sy + ty)

    if grid.type == "square":
        span = half * unit
        for i in range(-half, half + 1):
            offset = i * unit
            stroke = "#4b8bf4" if i == 0 else "#c8d6e5"
            width = "1.2" if i == 0 else "0.8"
            x1, y1 = to_canvas(-span, offset)
            x2, y2 = to_canvas(span, offset)
            lines.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{stroke}" stroke-width="{width}"/>'
            )
            x3, y3 = to_canvas(offset, -span)
            x4, y4 = to_canvas(offset, span)
            lines.append(
                f'<line x1="{x3:.1f}" y1="{y3:.1f}" x2="{x4:.1f}" y2="{y4:.1f}" '
                f'stroke="{stroke}" stroke-width="{width}"/>'
            )
    elif grid.type == "isometric":
        span = half + 2
        for i in range(-span, span + 1):
            p1 = to_canvas(*grid_to_xy((i, -span), grid, unit))
            p2 = to_canvas(*grid_to_xy((i, span), grid, unit))
            p3 = to_canvas(*grid_to_xy((-span, i), grid, unit))
            p4 = to_canvas(*grid_to_xy((span, i), grid, unit))
            p5 = to_canvas(*grid_to_xy((-span, i + span), grid, unit))
            p6 = to_canvas(*grid_to_xy((span, i - span), grid, unit))
            stroke = "#4b8bf4" if i == 0 else "#c8d6e5"
            for (ax, ay), (bx, by) in ((p1, p2), (p3, p4), (p5, p6)):
                lines.append(
                    f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                    f'stroke="{stroke}" stroke-width="0.8"/>'
                )
    elif grid.type == "polar":
        cx, cy = to_canvas(0.0, 0.0)
        scale = abs(sx)
        for r_idx in range(1, half + 1):
            r = r_idx * unit * scale
            lines.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                f'fill="none" stroke="#c8d6e5" stroke-width="0.8"/>'
            )
        max_r = half * unit
        spokes = max(8, grid.divisions)
        for k in range(spokes):
            deg = k * (360.0 / spokes)
            rad = math.radians(deg)
            x2, y2 = to_canvas(max_r * math.sin(rad), -max_r * math.cos(rad))
            stroke = "#4b8bf4" if k % (spokes // 4 or 1) == 0 else "#c8d6e5"
            lines.append(
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{stroke}" stroke-width="0.8"/>'
            )

    cx, cy = to_canvas(0.0, 0.0)
    lines.append(
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.5" fill="#e74c3c" opacity="0.7"/>'
    )
    return (
        f'<g id="construction-grid" clip-path="url(#canvas-clip)">'
        f'<defs><clipPath id="canvas-clip"><rect width="{canvas_size}" height="{canvas_size}"/></clipPath></defs>'
        + "".join(lines)
        + "</g>"
    )
