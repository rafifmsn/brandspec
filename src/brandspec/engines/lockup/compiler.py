"""Deterministic composition of mark and wordmark paths with 1u/2u clearspace guides."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pathops

from ...core.paths import add_rounded_polygon, path_to_svg_d, render_svg_doc
from ..mark.compiler import compile_mark_design_path
from ..mark.schema import MarkSpec
from ..wordmark.compiler import compile_wordmark
from ..wordmark.schema import WordmarkSpec
from .schema import LockupSpec


@dataclass(frozen=True)
class CompiledLockup:
    spec: LockupSpec
    path: pathops.Path
    svg_d: str
    svg_markup: str
    clearspace_svg_markup: str
    mark_bounds_svg: tuple[float, float, float, float]
    wordmark_bounds_svg: tuple[float, float, float, float]
    gap_svg: float
    clearspace_svg: float
    contour_count: int


def _resolve_rel(base_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p)


def _translate_to_origin_top_left(path: pathops.Path) -> tuple[pathops.Path, float, float]:
    min_x, min_y, max_x, max_y = path.bounds
    return path.transform(1.0, 0.0, 0.0, 1.0, -min_x, -min_y), max_x - min_x, max_y - min_y


def compile_lockup(spec: LockupSpec, base_dir: Path) -> CompiledLockup:
    """Compile a LockupSpec pairing mark and wordmark into lockup and clearspace SVGs."""
    mark_path = _resolve_rel(base_dir, spec.mark_spec)
    wm_path = _resolve_rel(base_dir, spec.wordmark_spec)

    mark_spec = MarkSpec.model_validate(json.loads(mark_path.read_text(encoding="utf-8")))
    wm_spec = WordmarkSpec.model_validate(json.loads(wm_path.read_text(encoding="utf-8")))

    mark_design = compile_mark_design_path(mark_spec)
    if abs(spec.mark_scale - 1.0) > 1e-6:
        mark_design = mark_design.transform(spec.mark_scale, 0.0, 0.0, spec.mark_scale, 0.0, 0.0)
    wm_compiled = compile_wordmark(wm_spec, base_dir=wm_path.parent)
    wm_design = wm_compiled.design_path

    unit = mark_spec.unit
    gap = spec.gap_u * unit

    m_tl, mw, mh = _translate_to_origin_top_left(mark_design)
    w_tl, ww, wh = _translate_to_origin_top_left(wm_design)
    wm_baseline_from_top = wm_compiled.baseline_y_design - wm_design.bounds[1]

    if spec.layout == "horizontal":
        if spec.align == "baseline":
            # Align mark bottom edge with wordmark baseline
            m_y = max(0.0, wm_baseline_from_top - mh)
            w_y = max(0.0, mh - wm_baseline_from_top)
        else:
            total_h = max(mh, wh)
            m_y = 0.5 * (total_h - mh)
            w_y = 0.5 * (total_h - wh)
        m_placed = m_tl.transform(1.0, 0.0, 0.0, 1.0, 0.0, m_y)
        w_placed = w_tl.transform(1.0, 0.0, 0.0, 1.0, mw + gap, w_y)
    elif spec.layout == "stacked":
        total_w = max(mw, ww)
        m_x = 0.5 * (total_w - mw)
        w_x = 0.5 * (total_w - ww)
        m_placed = m_tl.transform(1.0, 0.0, 0.0, 1.0, m_x, 0.0)
        w_placed = w_tl.transform(1.0, 0.0, 0.0, 1.0, w_x, mh + gap)
    else:
        total_w = max(mw, ww)
        m_x = 0.5 * (total_w - mw)
        w_x = 0.5 * (total_w - ww)
        m_placed = m_tl.transform(1.0, 0.0, 0.0, 1.0, m_x, 0.0)
        w_placed = w_tl.transform(1.0, 0.0, 0.0, 1.0, w_x, mh + gap)

    builder = pathops.OpBuilder()
    builder.add(m_placed, pathops.PathOp.UNION)
    builder.add(w_placed, pathops.PathOp.UNION)

    if spec.layout == "badge":
        bx0, by0, bx1, by1 = (
            min(m_placed.bounds[0], w_placed.bounds[0]),
            min(m_placed.bounds[1], w_placed.bounds[1]),
            max(m_placed.bounds[2], w_placed.bounds[2]),
            max(m_placed.bounds[3], w_placed.bounds[3]),
        )
        pad_b = 0.75 * unit
        stroke_w = max(2.0, 0.14 * unit)
        badge_pts = [
            (bx0 - pad_b, by0 - pad_b),
            (bx1 + pad_b, by0 - pad_b),
            (bx1 + pad_b, by1 + pad_b),
            (bx0 - pad_b, by1 + pad_b),
        ]
        badge_rect = add_rounded_polygon(badge_pts, True, 0.5 * unit)
        badge_stroke = pathops.Path()
        badge_stroke.addPath(badge_rect)
        badge_stroke.stroke(
            stroke_w,
            pathops.LineCap.ROUND_CAP,
            pathops.LineJoin.ROUND_JOIN,
            4.0,
        )
        badge_stroke.convertConicsToQuads(0.05)
        builder.add(pathops.simplify(badge_stroke, fix_winding=True), pathops.PathOp.UNION)

    combined = builder.resolve()
    combined.convertConicsToQuads(0.05)
    combined = pathops.simplify(combined, fix_winding=True)

    c_min_x, c_min_y, c_max_x, c_max_y = combined.bounds
    cw = max(c_max_x - c_min_x, 1e-6)
    ch = max(c_max_y - c_min_y, 1e-6)

    clear_u = spec.clearspace_u * unit
    canvas = spec.canvas_size
    usable = max(10.0, canvas - 2.0 * spec.padding - 4.0 * clear_u * 0.25)
    scale = usable / max(cw + 2.0 * clear_u, ch + 2.0 * clear_u)
    tx = 0.5 * canvas - scale * 0.5 * (c_min_x + c_max_x)
    ty = 0.5 * canvas - scale * 0.5 * (c_min_y + c_max_y)
    affine = (scale, 0.0, 0.0, scale, tx, ty)

    norm_path = combined.transform(*affine)
    norm_path.convertConicsToQuads(0.05)
    norm_path = pathops.simplify(norm_path, fix_winding=True)

    m_svg = m_placed.transform(*affine).bounds
    w_svg = w_placed.transform(*affine).bounds
    gap_svg = gap * scale
    clear_1u = clear_u * scale
    clear_2u = 2.0 * clear_u * scale

    n_x0, n_y0, n_x1, n_y1 = norm_path.bounds
    guide_1u = (
        f'<rect x="{n_x0 - clear_1u:.2f}" y="{n_y0 - clear_1u:.2f}" '
        f'width="{(n_x1 - n_x0) + 2 * clear_1u:.2f}" '
        f'height="{(n_y1 - n_y0) + 2 * clear_1u:.2f}" '
        f'fill="none" stroke="#4b8bf4" stroke-width="1.2" stroke-dasharray="6 4"/>'
    )
    guide_2u = (
        f'<rect x="{n_x0 - clear_2u:.2f}" y="{n_y0 - clear_2u:.2f}" '
        f'width="{(n_x1 - n_x0) + 2 * clear_2u:.2f}" '
        f'height="{(n_y1 - n_y0) + 2 * clear_2u:.2f}" '
        f'fill="none" stroke="#9ca3af" stroke-width="1.0" stroke-dasharray="3 4"/>'
    )
    guides = f'<g id="clearspace-guides">{guide_2u}{guide_1u}</g>'

    svg_d = path_to_svg_d(norm_path, spec.precision)
    svg_markup = render_svg_doc(svg_d, canvas, fill="#000000", title=spec.name)
    clearspace_svg_markup = render_svg_doc(
        svg_d,
        canvas,
        fill="#000000",
        background="#ffffff",
        extra_before=guides,
        title=f"{spec.name} (clearspace)",
    )
    return CompiledLockup(
        spec=spec,
        path=norm_path,
        svg_d=svg_d,
        svg_markup=svg_markup,
        clearspace_svg_markup=clearspace_svg_markup,
        mark_bounds_svg=m_svg,
        wordmark_bounds_svg=w_svg,
        gap_svg=gap_svg,
        clearspace_svg=clear_1u,
        contour_count=len(list(norm_path.contours)),
    )
