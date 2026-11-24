"""Determinism, schema, and archetype compilation tests for logo-mod."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path

from logo_mod.compiler import compile_spec
from logo_mod.inspect import analyze_compiled
from logo_mod.schema import LogoSpec

ARCHETYPES_DIR = Path(str(resources.files("logo_mod").joinpath("archetypes")))
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"


def test_all_archetypes_and_samples_compile_deterministically() -> None:
    files = sorted(ARCHETYPES_DIR.glob("*.json")) + sorted(SAMPLES_DIR.glob("*.json"))
    assert len(files) >= 8

    for spec_file in files:
        raw = json.loads(spec_file.read_text(encoding="utf-8"))
        spec = LogoSpec.model_validate(raw)

        first = compile_spec(spec)
        second = compile_spec(spec)

        assert first.svg_markup == second.svg_markup, f"Non-deterministic SVG for {spec_file.name}"
        assert len(first.svg_d) > 20

        metrics = analyze_compiled(first)
        assert metrics.ink_ratio > 0.1
        assert metrics.tiny_island_count == 0, f"Slivers detected in {spec_file.name}: {metrics}"
        assert metrics.passed, f"Metrics failed for {spec_file.name}: {metrics}"


def test_halo_carves_uniform_clearance() -> None:
    spec = LogoSpec.model_validate(
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
    spec = LogoSpec.model_validate(
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
    # base-bar stays intact as 1 piece; cross-bar splits into top and bottom stubs = 3 islands
    assert metrics.island_count == 3
    assert metrics.passed
