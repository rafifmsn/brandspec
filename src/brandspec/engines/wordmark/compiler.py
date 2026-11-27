"""Font-to-path outlining, kerning/tracking, ink traps, and stencil cuts for wordmarks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
import pathops

from ...core.grid import GridSpec
from ...core.paths import path_to_svg_d, render_svg_doc
from ..mark.geometry import build_shape
from .schema import InkTrapSpec, WordmarkSpec


@dataclass(frozen=True)
class CompiledWordmark:
    spec: WordmarkSpec
    design_path: pathops.Path
    path: pathops.Path
    svg_d: str
    svg_markup: str
    baseline_y_design: float
    cap_height_design: float
    x_height_design: float
    contour_count: int


class SkiaPathPen(BasePen):
    """fontTools pen that records glyph outlines directly into a pathops.Path."""

    def __init__(self, glyphSet, out_path: pathops.Path) -> None:
        super().__init__(glyphSet)
        self.path = out_path

    def _moveTo(self, pt: tuple[float, float]) -> None:
        self.path.moveTo(float(pt[0]), float(pt[1]))

    def _lineTo(self, pt: tuple[float, float]) -> None:
        self.path.lineTo(float(pt[0]), float(pt[1]))

    def _curveToOne(
        self,
        pt1: tuple[float, float],
        pt2: tuple[float, float],
        pt3: tuple[float, float],
    ) -> None:
        self.path.cubicTo(
            float(pt1[0]),
            float(pt1[1]),
            float(pt2[0]),
            float(pt2[1]),
            float(pt3[0]),
            float(pt3[1]),
        )

    def _qCurveToOne(
        self,
        pt1: tuple[float, float],
        pt2: tuple[float, float],
    ) -> None:
        self.path.quadTo(float(pt1[0]), float(pt1[1]), float(pt2[0]), float(pt2[1]))

    def _closePath(self) -> None:
        self.path.close()

    def _endPath(self) -> None:
        return


def _apply_case(text: str, case: str) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    return text


def _font_kern_pairs(font: TTFont) -> dict[tuple[str, str], int]:
    pairs: dict[tuple[str, str], int] = {}
    if "kern" not in font:
        return pairs
    for subtable in font["kern"].kernTables:
        if hasattr(subtable, "kernTable") and isinstance(subtable.kernTable, dict):
            for pair, val in subtable.kernTable.items():
                pairs[pair] = pairs.get(pair, 0) + int(val)
    return pairs


def _apply_ink_traps(path: pathops.Path, trap: InkTrapSpec, unit: float) -> pathops.Path:
    """Carve small triangular notches at sharp acute vertices of polygonal contours."""
    depth = trap.depth_u * unit
    width = trap.width_u * unit
    thresh_rad = math.radians(trap.angle_threshold_deg)

    cutters = pathops.OpBuilder()
    has_cut = False
    for contour in path.contours:
        pts: list[tuple[float, float]] = []
        for verb, seg_pts in contour.segments:
            if verb == "moveTo" or verb == "lineTo":
                pt = seg_pts[0]
                if not pts or math.hypot(pt[0] - pts[-1][0], pt[1] - pts[-1][1]) > 1e-4:
                    pts.append((float(pt[0]), float(pt[1])))
        if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= 1e-4:
            pts.pop()
        n = len(pts)
        if n < 3:
            continue
        for i in range(n):
            p_prev = pts[(i - 1) % n]
            p_curr = pts[i]
            p_next = pts[(i + 1) % n]
            v1x, v1y = p_prev[0] - p_curr[0], p_prev[1] - p_curr[1]
            v2x, v2y = p_next[0] - p_curr[0], p_next[1] - p_curr[1]
            d1, d2 = math.hypot(v1x, v1y), math.hypot(v2x, v2y)
            if d1 < depth * 1.5 or d2 < depth * 1.5:
                continue
            u1x, u1y = v1x / d1, v1y / d1
            u2x, u2y = v2x / d2, v2y / d2
            dot = max(-1.0, min(1.0, u1x * u2x + u1y * u2y))
            angle = math.acos(dot)
            if angle >= thresh_rad or angle < 1e-3:
                continue
            bx, by = u1x + u2x, u1y + u2y
            bn = math.hypot(bx, by)
            if bn < 1e-6:
                continue
            bx /= bn
            by /= bn
            px, py = -by, bx
            tip = (p_curr[0] + bx * depth, p_curr[1] + by * depth)
            base_c = (p_curr[0] - bx * (0.25 * depth), p_curr[1] - by * (0.25 * depth))
            half_w = 0.5 * width
            b1 = (base_c[0] + px * half_w, base_c[1] + py * half_w)
            b2 = (base_c[0] - px * half_w, base_c[1] - py * half_w)
            notch = pathops.Path()
            notch.moveTo(*b1)
            notch.lineTo(*tip)
            notch.lineTo(*b2)
            notch.close()
            cutters.add(notch, pathops.PathOp.UNION)
            has_cut = True

    if not has_cut:
        return path
    notch_mask = cutters.resolve()
    out = pathops.op(path, notch_mask, pathops.PathOp.DIFFERENCE)
    out.convertConicsToQuads(0.05)
    return pathops.simplify(out, fix_winding=True)


def compile_wordmark(spec: WordmarkSpec, base_dir: Path | None = None) -> CompiledWordmark:
    """Compile a WordmarkSpec into pure vector glyph contours without <text>."""
    font_path = Path(spec.font_path)
    if not font_path.is_absolute() and base_dir is not None:
        font_path = base_dir / font_path
    if not font_path.is_file():
        raise ValueError(f"Font file not found: {font_path}")

    with TTFont(font_path) as font:
        if "head" not in font or "hmtx" not in font:
            raise ValueError(f"Unsupported font tables in {font_path}")
        if "glyf" not in font and "CFF " not in font:
            raise ValueError(
                f"Unsupported font outline table in {font_path}; expected glyf or CFF."
            )
        cmap = font.getBestCmap()
        if not cmap:
            raise ValueError(f"Missing character map in font {font_path}")
        glyph_set = font.getGlyphSet()
        upem = float(font["head"].unitsPerEm)
        hmtx = font["hmtx"]
        kern_table = _font_kern_pairs(font)
        os2 = font["OS/2"] if "OS/2" in font else None
        hhea = font["hhea"] if "hhea" in font else None
        ascent_units = float(getattr(hhea, "ascent", upem * 0.8))
        raw_cap = float(getattr(os2, "sCapHeight", 0) or (ascent_units * 0.9))
        raw_xh = float(getattr(os2, "sxHeight", 0) or (raw_cap * 0.7))

        rendered_text = _apply_case(spec.text, spec.case)
        scale = (spec.em_units * spec.unit) / upem
        cursor_x = 0.0
        prev_glyph: str | None = None
        prev_char: str | None = None

        builder = pathops.OpBuilder()
        has_ink = False

        for ch in rendered_text:
            code = ord(ch)
            if code not in cmap:
                raise ValueError(f"Missing glyph for character {ch!r} in font {font_path}")
            gname = cmap[code]
            if gname not in glyph_set:
                raise ValueError(f"Glyph {gname!r} for {ch!r} missing in font {font_path}")

            if prev_glyph is not None:
                kern_val = kern_table.get((prev_glyph, gname), 0)
                cursor_x += kern_val * scale
            if prev_char is not None:
                pair_override = spec.kerning_pairs.get(prev_char + ch, 0.0)
                cursor_x += pair_override * spec.em_units * spec.unit

            gpath = pathops.Path()
            pen = SkiaPathPen(glyph_set, gpath)
            glyph_set[gname].draw(pen)

            if gpath.bounds is not None and len(list(gpath.contours)) > 0:
                transformed = gpath.transform(scale, 0.0, 0.0, -scale, cursor_x, 0.0)
                transformed.convertConicsToQuads(0.05)
                transformed = pathops.simplify(transformed, fix_winding=True)
                builder.add(transformed, pathops.PathOp.UNION)
                has_ink = True

            adv_width = float(hmtx[gname][0]) * scale
            cursor_x += adv_width + (spec.tracking_em * spec.em_units * spec.unit)
            prev_glyph = gname
            prev_char = ch

    if not has_ink:
        raise ValueError(f"Wordmark text {spec.text!r} produced empty glyph geometry.")

    acc = builder.resolve()
    acc.convertConicsToQuads(0.05)
    acc = pathops.simplify(acc, fix_winding=True)

    bounds = acc.bounds
    if bounds is None or len(list(acc.contours)) == 0:
        raise ValueError("Wordmark geometry is empty after glyph simplification.")
    min_x, min_y, max_x, max_y = bounds
    cx_raw = 0.5 * (min_x + max_x)
    cy_raw = 0.5 * (min_y + max_y)
    design_path = acc.transform(1.0, 0.0, 0.0, 1.0, -cx_raw, -cy_raw)
    baseline_y_design = -cy_raw

    if spec.ink_trap is not None:
        design_path = _apply_ink_traps(design_path, spec.ink_trap, spec.unit)

    if spec.stencil_cuts:
        grid = GridSpec()
        cut_builder = pathops.OpBuilder()
        for shape in spec.stencil_cuts:
            cut_builder.add(build_shape(shape, grid, spec.unit), pathops.PathOp.UNION)
        cut_mask = cut_builder.resolve()
        design_path = pathops.op(design_path, cut_mask, pathops.PathOp.DIFFERENCE)
        design_path.convertConicsToQuads(0.05)
        design_path = pathops.simplify(design_path, fix_winding=True)

    d_bounds = design_path.bounds
    if d_bounds is None or len(list(design_path.contours)) == 0:
        raise ValueError("Wordmark geometry is empty after ink traps or stencil cuts.")

    d_min_x, d_min_y, d_max_x, d_max_y = d_bounds
    w = max(d_max_x - d_min_x, 1e-6)
    h = max(d_max_y - d_min_y, 1e-6)
    canvas = spec.post.canvas_size
    usable = max(10.0, canvas - 2.0 * spec.post.padding)
    norm_scale = usable / max(w, h)
    tx = 0.5 * canvas - norm_scale * 0.5 * (d_min_x + d_max_x)
    ty = 0.5 * canvas - norm_scale * 0.5 * (d_min_y + d_max_y)
    norm_path = design_path.transform(norm_scale, 0.0, 0.0, norm_scale, tx, ty)
    norm_path.convertConicsToQuads(0.05)
    norm_path = pathops.simplify(norm_path, fix_winding=True)

    svg_d = path_to_svg_d(norm_path, spec.post.precision)
    svg_markup = render_svg_doc(svg_d, canvas, fill=spec.post.fill, title=spec.name)
    return CompiledWordmark(
        spec=spec,
        design_path=design_path,
        path=norm_path,
        svg_d=svg_d,
        svg_markup=svg_markup,
        baseline_y_design=baseline_y_design,
        cap_height_design=raw_cap * scale,
        x_height_design=raw_xh * scale,
        contour_count=len(list(norm_path.contours)),
    )
