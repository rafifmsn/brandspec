"""Determinism, schema, and archetype compilation tests for logo-mod."""

from __future__ import annotations

import json
from pathlib import Path

from logo_mod.compiler import compile_spec
from logo_mod.inspect import analyze_compiled
from logo_mod.schema import LogoSpec

ARCHETYPES_DIR = Path(__file__).resolve().parents[1] / "archetypes"


def test_all_archetypes_compile_and_are_deterministic() -> None:
    files = sorted(ARCHETYPES_DIR.glob("*.json"))
    assert len(files) >= 5

    for arch_file in files:
        raw = json.loads(arch_file.read_text(encoding="utf-8"))
        spec = LogoSpec.model_validate(raw)

        first = compile_spec(spec)
        second = compile_spec(spec)

        assert first.svg_markup == second.svg_markup, f"Non-deterministic SVG for {arch_file.name}"
        assert len(first.svg_d) > 20

        metrics = analyze_compiled(first)
        assert metrics.ink_ratio > 0.1
        assert metrics.tiny_island_count == 0, f"Slivers detected in {arch_file.name}: {metrics}"


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
    # Two separated horizontal stubs + one continuous vertical bar = 3 islands
    assert metrics.island_count == 3
    assert metrics.passed
