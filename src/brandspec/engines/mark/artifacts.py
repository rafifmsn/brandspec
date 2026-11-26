"""Shared artifact writer for compiled mark outputs and studio metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...inspect import QualityMetrics, render_inspection_sheet
from .compiler import CompiledMark
from .schema import MarkSpec


def build_mark_meta(spec: MarkSpec, compiled: CompiledMark) -> dict[str, Any]:
    """Build deterministic studio metadata payload for a compiled mark."""
    return {
        "name": spec.name,
        "concept": spec.concept,
        "unit": spec.unit,
        "grid": spec.grid.model_dump(mode="json"),
        "canvas_size": spec.post.canvas_size,
        "affine": list(compiled.affine),
    }


def write_mark_artifacts(
    spec: MarkSpec,
    compiled: CompiledMark,
    metrics: QualityMetrics,
    out_dir: Path,
) -> dict[str, Path]:
    """Write standard mark build outputs including meta.json into out_dir."""
    sheet = render_inspection_sheet(compiled)
    out_dir.mkdir(parents=True, exist_ok=True)

    svg_file = out_dir / "logo.svg"
    sheet_file = out_dir / "sheet.png"
    metrics_file = out_dir / "metrics.json"
    locked_spec = out_dir / "spec.json"
    meta_file = out_dir / "meta.json"

    svg_file.write_text(compiled.svg_markup, encoding="utf-8")
    sheet.save(sheet_file, format="PNG")
    metrics_file.write_text(json.dumps(metrics.to_dict(), indent=2) + "\n", encoding="utf-8")
    locked_spec.write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )
    meta_file.write_text(
        json.dumps(build_mark_meta(spec, compiled), indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "svg": svg_file,
        "sheet": sheet_file,
        "metrics": metrics_file,
        "spec": locked_spec,
        "meta": meta_file,
    }
