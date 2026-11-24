"""Parametric optical & kinetic Effect generators (line screens, radial blades, halftones)."""

from __future__ import annotations

import math

import numpy as np
import pathops

from ...core.grid import GridSpec, grid_to_xy
from .schema import HalftoneGridShape, LineScreenShape, RadialBladesShape


def _eval_line_profile(
    t: float,
    profile: str,
    wave_cycles: float,
    phase: float,
) -> float:
    if profile == "constant":
        return 1.0
    if profile == "linear":
        return t
    if profile == "center_bulge":
        return math.sin(math.pi * t)
    if profile == "center_pinch":
        return 1.0 - math.sin(math.pi * t)
    if profile == "sine":
        return 0.5 * (1.0 + math.sin(2.0 * math.pi * wave_cycles * t + math.radians(phase)))
    if profile == "exponential":
        return (math.exp(3.0 * t) - 1.0) / (math.e**3 - 1.0)
    return t


def build_line_screen(
    shape: LineScreenShape,
    grid: GridSpec,
    unit: float,
) -> pathops.Path:
    """Build parallel stripes with modulated thickness."""
    cx, cy = grid_to_xy(shape.center, grid, unit)
    rad = math.radians(shape.angle_deg)
    ca, sa = math.cos(rad), math.sin(rad)

    pitch = shape.pitch * unit
    half_len = 0.5 * shape.length * unit
    total_span = (shape.count - 1) * pitch
    y0 = -0.5 * total_span

    builder = pathops.OpBuilder()
    for i in range(shape.count):
        t = i / max(1, shape.count - 1)
        weight = _eval_line_profile(t, shape.profile, shape.wave_cycles, shape.phase)
        if shape.invert_profile:
            weight = 1.0 - weight
        w = (shape.min_width + (shape.max_width - shape.min_width) * weight) * unit
        hw = 0.5 * w
        yc = y0 + i * pitch

        bar = pathops.Path()
        bar.moveTo(-half_len, yc - hw)
        bar.lineTo(half_len, yc - hw)
        bar.lineTo(half_len, yc + hw)
        bar.lineTo(-half_len, yc + hw)
        bar.close()
        builder.add(bar, pathops.PathOp.UNION)

    combined = builder.resolve()
    return combined.transform(ca, sa, -sa, ca, cx, cy)


def _polar_xy(radius: float, deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    return (radius * math.sin(rad), -radius * math.cos(rad))


def build_radial_blades(
    shape: RadialBladesShape,
    grid: GridSpec,
    unit: float,
) -> pathops.Path:
    """Build N-fold twisted rotational blades around a center."""
    cx, cy = grid_to_xy(shape.center, grid, unit)
    r_in = shape.inner_radius * unit
    r_out = shape.outer_radius * unit
    r_mid = r_in + shape.curve_bias * (r_out - r_in)

    builder = pathops.OpBuilder()
    step = 360.0 / shape.count
    for k in range(shape.count):
        base_deg = shape.angle_deg + k * step
        in_a = base_deg - 0.5 * shape.inner_width_deg
        in_b = base_deg + 0.5 * shape.inner_width_deg
        out_center = base_deg + shape.twist_deg
        out_a = out_center - 0.5 * shape.outer_width_deg
        out_b = out_center + 0.5 * shape.outer_width_deg

        p_in_a = _polar_xy(r_in, in_a)
        p_in_b = _polar_xy(r_in, in_b)
        p_out_a = _polar_xy(r_out, out_a)
        p_out_b = _polar_xy(r_out, out_b)

        ctrl_a = _polar_xy(r_mid, in_a + 0.65 * shape.twist_deg)
        ctrl_b = _polar_xy(r_mid, in_b + 0.35 * shape.twist_deg)

        blade = pathops.Path()
        blade.moveTo(*p_in_a)
        blade.quadTo(*ctrl_a, *p_out_a)
        blade.lineTo(*p_out_b)
        blade.quadTo(*ctrl_b, *p_in_b)
        blade.close()
        blade = blade.transform(1, 0, 0, 1, cx, cy)
        builder.add(blade, pathops.PathOp.UNION)

    return pathops.simplify(builder.resolve(), fix_winding=True)


def build_halftone_grid(
    shape: HalftoneGridShape,
    grid: GridSpec,
    unit: float,
) -> pathops.Path:
    """Build a grid of geometric cells whose size follows a mathematical scalar field."""
    cx, cy = grid_to_xy(shape.center, grid, unit)
    pitch = shape.pitch * unit
    xs = (np.arange(shape.cols) - 0.5 * (shape.cols - 1)) * pitch
    ys = (np.arange(shape.rows) - 0.5 * (shape.rows - 1)) * pitch

    max_x = max(abs(xs[0]), abs(xs[-1]), 1e-6)
    max_y = max(abs(ys[0]), abs(ys[-1]), 1e-6)
    max_r = math.hypot(max_x, max_y)

    kappa = 0.5522847498307936
    builder = pathops.OpBuilder()
    for gy in ys:
        for gx in xs:
            nx = gx / max_x
            ny = gy / max_y
            nr = math.hypot(gx, gy) / max_r

            if shape.field == "radial_decay":
                val = 1.0 - nr
            elif shape.field == "radial_grow":
                val = nr
            elif shape.field == "linear_x":
                val = 0.5 * (nx + 1.0)
            elif shape.field == "linear_y":
                val = 0.5 * (ny + 1.0)
            elif shape.field == "diagonal":
                val = 0.25 * (nx + ny + 2.0)
            else:
                val = 0.5 * (1.0 + math.cos(2.0 * math.pi * nr))

            size = (shape.min_size + (shape.max_size - shape.min_size) * val) * unit
            r = 0.5 * size
            px, py = cx + float(gx), cy + float(gy)

            cell = pathops.Path()
            if shape.shape == "circle":
                k = r * kappa
                cell.moveTo(px, py - r)
                cell.cubicTo(px + k, py - r, px + r, py - k, px + r, py)
                cell.cubicTo(px + r, py + k, px + k, py + r, px, py + r)
                cell.cubicTo(px - k, py + r, px - r, py + k, px - r, py)
                cell.cubicTo(px - r, py - k, px - k, py - r, px, py - r)
                cell.close()
            elif shape.shape == "diamond":
                cell.moveTo(px, py - r)
                cell.lineTo(px + r, py)
                cell.lineTo(px, py + r)
                cell.lineTo(px - r, py)
                cell.close()
            else:
                cell.moveTo(px - r, py - r)
                cell.lineTo(px + r, py - r)
                cell.lineTo(px + r, py + r)
                cell.lineTo(px - r, py + r)
                cell.close()
            builder.add(cell, pathops.PathOp.UNION)

    return builder.resolve()
