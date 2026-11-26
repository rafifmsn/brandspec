"""Icon set compiler inheriting mark geometry defaults and generating 24px sheets."""

from __future__ import annotations

from dataclasses import dataclass
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
import pathops
import resvg_py

from ...core.grid import GridSpec
from ...core.paths import path_to_svg_d, render_svg_doc
from ...inspect import QualityMetrics, analyze_compiled
from ..mark.compiler import compile_layers
from ..mark.schema import GridPathShape, LayerSpec, MarkSpec, PolygonShape, RectShape
from .schema import IconSetSpec


@dataclass(frozen=True)
class CompiledIcon:
    id: str
    path: pathops.Path
    svg_d: str
    svg_markup: str
    contour_count: int
    metrics: QualityMetrics


@dataclass(frozen=True)
class CompiledIconSet:
    spec: IconSetSpec
    icons: list[CompiledIcon]
    sheet_image: Image.Image


def _resolve_rel(base_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p)


def _extract_mark_defaults(mark_spec: MarkSpec) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for layer in mark_spec.layers:
        for shape in layer.shapes:
            if isinstance(shape, GridPathShape):
                defaults.setdefault("cap", shape.cap)
                defaults.setdefault("join", shape.join)
                if shape.corner_radius > 0.0:
                    defaults.setdefault("corner_radius", shape.corner_radius)
            elif isinstance(shape, (RectShape, PolygonShape)) and shape.corner_radius > 0.0:
                defaults.setdefault("corner_radius", shape.corner_radius)
    return defaults


def _apply_icon_defaults(
    layer: LayerSpec,
    stroke_width: float,
    corner_radius: float,
    cap: str,
    join: str,
) -> LayerSpec:
    updated_shapes = []
    for shape in layer.shapes:
        if isinstance(shape, GridPathShape):
            updates: dict[str, Any] = {}
            if "width" not in shape.model_fields_set and shape.width > 0:
                updates["width"] = stroke_width
            if "corner_radius" not in shape.model_fields_set:
                updates["corner_radius"] = corner_radius
            if "cap" not in shape.model_fields_set:
                updates["cap"] = cap
            if "join" not in shape.model_fields_set:
                updates["join"] = join
            updated_shapes.append(shape.model_copy(update=updates))
        elif isinstance(shape, (RectShape, PolygonShape)):
            updates = {}
            if "corner_radius" not in shape.model_fields_set:
                updates["corner_radius"] = corner_radius
            updated_shapes.append(shape.model_copy(update=updates))
        else:
            updated_shapes.append(shape)
    return layer.model_copy(update={"shapes": updated_shapes})


def _render_icons_sheet(icons: list[CompiledIcon], viewbox_size: int) -> Image.Image:
    cols = min(6, max(1, len(icons)))
    rows = (len(icons) + cols - 1) // cols
    cell_w = 128
    cell_h = 148
    pad = 16
    sheet = Image.new("RGB", (pad + cols * (cell_w + pad), pad + rows * (cell_h + pad)), (11, 12, 14))
    draw = ImageDraw.Draw(sheet)

    for idx, icon in enumerate(icons):
        r = idx // cols
        c = idx % cols
        x = pad + c * (cell_w + pad)
        y = pad + r * (cell_h + pad)
        draw.rectangle([x, y, x + cell_w - 1, y + cell_h - 1], fill=(18, 19, 22), outline=(38, 40, 46))
        png_bytes = resvg_py.svg_to_bytes(
            svg_string=icon.svg_markup,
            width=72,
            height=72,
            background="#ffffff",
        )
        thumb = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        sheet.paste(thumb, (x + (cell_w - 72) // 2, y + 14))
        draw.text((x + 10, y + 96), icon.id[:14], fill=(243, 244, 246))
        status = "PASS" if icon.metrics.passed else "WARN"
        draw.text((x + 10, y + 114), f"{viewbox_size}px {status}", fill=(156, 163, 175))
    return sheet


def compile_icon_set(spec: IconSetSpec, base_dir: Path | None = None) -> CompiledIconSet:
    """Compile every icon in IconSetSpec onto a crisp integer viewBox grid."""
    effective_cap = spec.cap
    effective_join = spec.join
    effective_radius = spec.corner_radius

    if spec.inherits_mark:
        mark_path = _resolve_rel(base_dir or Path.cwd(), spec.inherits_mark)
        mark_spec = MarkSpec.model_validate(json.loads(mark_path.read_text(encoding="utf-8")))
        inherited = _extract_mark_defaults(mark_spec)
        if "cap" not in spec.model_fields_set and "cap" in inherited:
            effective_cap = inherited["cap"]
        if "join" not in spec.model_fields_set and "join" in inherited:
            effective_join = inherited["join"]
        if "corner_radius" not in spec.model_fields_set and "corner_radius" in inherited:
            effective_radius = inherited["corner_radius"]

    resolved_spec = spec.model_copy(
        update={
            "cap": effective_cap,
            "join": effective_join,
            "corner_radius": effective_radius,
        }
    )

    compiled_icons: list[CompiledIcon] = []
    half_vb = 0.5 * resolved_spec.viewbox_size
    fractional_stroke = abs(resolved_spec.stroke_width - round(resolved_spec.stroke_width)) > 1e-6

    for item in resolved_spec.icons:
        item_layers = [
            _apply_icon_defaults(
                layer,
                resolved_spec.stroke_width,
                effective_radius,
                effective_cap,
                effective_join,
            )
            for layer in item.layers
        ]
        design = compile_layers(
            item_layers,
            GridSpec(type="square", divisions=resolved_spec.viewbox_size),
            1.0,
        )
        if design.bounds is None or len(list(design.contours)) == 0:
            raise ValueError(f"Icon '{item.id}' compiled to empty geometry.")
        vb_path = design.transform(1.0, 0.0, 0.0, 1.0, half_vb, half_vb)
        vb_path.convertConicsToQuads(0.05)
        vb_path = pathops.simplify(vb_path, fix_winding=True)
        svg_d = path_to_svg_d(vb_path, resolved_spec.precision)
        svg_markup = render_svg_doc(
            svg_d,
            resolved_spec.viewbox_size,
            fill="#000000",
            title=item.id,
        )
        contour_count = len(list(vb_path.contours))

        class _Proxy:
            def __init__(self, markup: str, contours: int) -> None:
                self.svg_markup = markup
                self.contour_count = contours

        metrics = analyze_compiled(_Proxy(svg_markup, contour_count))  # type: ignore[arg-type]
        if fractional_stroke:
            warnings = list(metrics.warnings) + [
                f"Non-integer stroke_width={resolved_spec.stroke_width} may soften 16px/24px edges"
            ]
            metrics = QualityMetrics(
                ink_ratio=metrics.ink_ratio,
                ink_ratio_24px=metrics.ink_ratio_24px,
                bbox_aspect=metrics.bbox_aspect,
                island_count=metrics.island_count,
                tiny_island_count=metrics.tiny_island_count,
                contour_count=metrics.contour_count,
                optical_drift_pct=metrics.optical_drift_pct,
                warnings=warnings,
                passed=False,
            )

        compiled_icons.append(
            CompiledIcon(
                id=item.id,
                path=vb_path,
                svg_d=svg_d,
                svg_markup=svg_markup,
                contour_count=contour_count,
                metrics=metrics,
            )
        )

    sheet = _render_icons_sheet(compiled_icons, resolved_spec.viewbox_size)
    return CompiledIconSet(spec=resolved_spec, icons=compiled_icons, sheet_image=sheet)
