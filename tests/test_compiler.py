"""Determinism, schema, and archetype compilation tests for brandspec."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path

import pathops
import pytest

from brandspec.core.paths import dilate_path
from brandspec.engines.mark.compiler import compile_spec
from brandspec.engines.mark.schema import MarkSpec
from brandspec.inspect import analyze_compiled

ARCHETYPES_DIR = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"


def test_all_archetypes_and_samples_compile_deterministically() -> None:
    files = sorted(ARCHETYPES_DIR.glob("*.json")) + sorted(SAMPLES_DIR.glob("*.json"))
    assert len(files) >= 8

    for spec_file in files:
        raw = json.loads(spec_file.read_text(encoding="utf-8"))
        spec = MarkSpec.model_validate(raw)

        first = compile_spec(spec)
        second = compile_spec(spec)

        assert first.svg_markup == second.svg_markup, f"Non-deterministic SVG for {spec_file.name}"
        assert len(first.svg_d) > 20

        metrics = analyze_compiled(first)
        assert metrics.ink_ratio > 0.1
        assert metrics.tiny_island_count == 0, f"Slivers detected in {spec_file.name}: {metrics}"
        assert metrics.passed, f"Metrics failed for {spec_file.name}: {metrics}"


def test_halo_carves_uniform_clearance() -> None:
    spec = MarkSpec.model_validate(
        {
            "name": "Halo Test",
            "concept": "Crossing bars with halo",
            "unit": 40,
            "layers": [
                {
                    "id": "back",
                    "op": "unite",
                    "shapes": [{"type": "rect", "center": [0, 0], "width": 6, "height": 1}],
                },
                {
                    "id": "front",
                    "op": "unite",
                    "halo": 0.4,
                    "shapes": [{"type": "rect", "center": [0, 0], "width": 1, "height": 6}],
                },
            ],
        }
    )
    compiled = compile_spec(spec)
    metrics = analyze_compiled(compiled)
    assert metrics.island_count == 3
    assert metrics.passed


def test_halo_targets_scopes_clearance_without_self_cut() -> None:
    spec = MarkSpec.model_validate(
        {
            "name": "Scoped Halo Test",
            "concept": "Overpass carves only crossing band without cutting base bar",
            "unit": 40,
            "layers": [
                {
                    "id": "base-bar",
                    "op": "unite",
                    "shapes": [{"type": "rect", "center": [0, 0], "width": 6, "height": 1}],
                },
                {
                    "id": "cross-bar",
                    "op": "unite",
                    "halo": 0.4,
                    "shapes": [{"type": "rect", "center": [0, 0], "width": 1, "height": 6}],
                },
                {
                    "id": "overpass",
                    "op": "unite",
                    "halo": 0.4,
                    "halo_targets": ["cross-bar"],
                    "shapes": [{"type": "rect", "center": [0, 0], "width": 2.4, "height": 1}],
                },
            ],
        }
    )
    compiled = compile_spec(spec)
    metrics = analyze_compiled(compiled)
    assert metrics.island_count == 3
    assert metrics.passed


def _angular_weave_spec(halo_join: str | None = None, halo_cap: str | None = None) -> MarkSpec:
    foreground: dict = {
        "id": "front-angle",
        "op": "unite",
        "halo": 0.4,
        "shapes": [
            {
                "type": "grid_path",
                "points": [[-2.0, -2.0], [0.0, 0.0], [2.0, -1.0]],
                "closed": False,
                "width": 1.0,
                "cap": "butt",
                "join": "miter",
            }
        ],
    }
    if halo_join is not None:
        foreground["halo_join"] = halo_join
    if halo_cap is not None:
        foreground["halo_cap"] = halo_cap

    return MarkSpec.model_validate(
        {
            "name": "Angular Weave Test",
            "concept": "Sharp isometric crossing grid_path weave",
            "unit": 40,
            "grid": {"type": "isometric", "divisions": 8},
            "layers": [
                {
                    "id": "back-bar",
                    "op": "unite",
                    "shapes": [
                        {
                            "type": "grid_path",
                            "points": [[-3.0, 0.0], [3.0, 0.0]],
                            "closed": False,
                            "width": 1.0,
                            "cap": "butt",
                            "join": "miter",
                        }
                    ],
                },
                foreground,
            ],
        }
    )


def test_halo_join_miter_preserves_sharp_channels() -> None:
    miter_compiled = compile_spec(_angular_weave_spec(halo_join="miter"))
    round_compiled = compile_spec(_angular_weave_spec(halo_join="round"))

    miter_metrics = analyze_compiled(miter_compiled)
    assert miter_metrics.passed, f"Metrics failed for miter halo: {miter_metrics}"
    assert miter_compiled.svg_d != round_compiled.svg_d
    assert "Q " not in miter_compiled.svg_d and "C " not in miter_compiled.svg_d
    assert "Q " in round_compiled.svg_d or "C " in round_compiled.svg_d


def test_halo_join_defaults_to_round() -> None:
    default_compiled = compile_spec(_angular_weave_spec())
    explicit_round = compile_spec(_angular_weave_spec(halo_join="round", halo_cap="round"))

    assert default_compiled.svg_markup == explicit_round.svg_markup


def test_halo_join_applies_to_subtract_layer() -> None:
    def make_subtract_spec(halo_join: str) -> MarkSpec:
        return MarkSpec.model_validate(
            {
                "name": "Subtract Halo Test",
                "concept": "Dilated miter subtraction mask",
                "unit": 40,
                "layers": [
                    {
                        "id": "block",
                        "op": "unite",
                        "shapes": [{"type": "rect", "center": [0, 0], "width": 6, "height": 4}],
                    },
                    {
                        "id": "notch",
                        "op": "subtract",
                        "halo": 0.4,
                        "halo_join": halo_join,
                        "shapes": [
                            {
                                "type": "grid_path",
                                "points": [[-1.5, -2.5], [0.0, 0.0], [1.5, -2.5]],
                                "closed": False,
                                "width": 0.8,
                                "cap": "butt",
                                "join": "miter",
                            }
                        ],
                    },
                ],
            }
        )

    miter_compiled = compile_spec(make_subtract_spec("miter"))
    round_compiled = compile_spec(make_subtract_spec("round"))

    assert analyze_compiled(miter_compiled).passed
    assert miter_compiled.svg_d != round_compiled.svg_d
    assert "Q " not in miter_compiled.svg_d and "C " not in miter_compiled.svg_d


def test_dilate_path_edge_cases() -> None:
    open_path = pathops.Path()
    open_path.moveTo(0.0, 0.0)
    open_path.lineTo(40.0, 0.0)
    open_path.lineTo(40.0, 40.0)

    assert dilate_path(open_path, 0.0, join="miter", cap="square") is open_path

    bevel_square = dilate_path(open_path, 10.0, join="bevel", cap="square")
    round_butt = dilate_path(open_path, 10.0, join="round", cap="butt")
    assert bevel_square.bounds is not None
    assert round_butt.bounds is not None
    assert bevel_square.bounds != round_butt.bounds

    with pytest.raises(ValueError, match="halo join"):
        dilate_path(open_path, 10.0, join="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="halo cap"):
        dilate_path(open_path, 10.0, cap="invalid")  # type: ignore[arg-type]
