"""Tests for bounded parameter sweep CLI and studio-compatible gallery output."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path

from brandspec.cli import main

ARCHETYPES_DIR = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))


def test_sweep_cartesian_outputs_studio_compatible_dirs(tmp_path: Path) -> None:
    out_dir = tmp_path / "sweep-out"
    rc = main(
        [
            "sweep",
            str(ARCHETYPES_DIR / "ribbon-weave.json"),
            "--set",
            "layers.1.halo=0.35,0.45",
            "--set",
            "post.invert=false,true",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert (out_dir / "variants.json").is_file()
    assert (out_dir / "contact_sheet.png").is_file()

    variants = json.loads((out_dir / "variants.json").read_text(encoding="utf-8"))
    assert len(variants) == 4
    assert [v["id"] for v in variants] == ["01", "02", "03", "04"]

    for vid in ("01", "02", "03", "04"):
        vdir = out_dir / vid
        assert (vdir / "spec.json").is_file()
        assert (vdir / "logo.svg").is_file()
        assert (vdir / "sheet.png").is_file()
        assert (vdir / "metrics.json").is_file()
        assert (vdir / "meta.json").is_file()


def test_sweep_enforces_max_variants_bound(tmp_path: Path) -> None:
    out_dir = tmp_path / "bounded-out"
    rc = main(
        [
            "sweep",
            str(ARCHETYPES_DIR / "ribbon-weave.json"),
            "--set",
            "layers.1.halo=0.3,0.35,0.4",
            "--set",
            "post.invert=false,true",
            "--max-variants",
            "4",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 1
    assert not (out_dir / "01").exists()


def test_sweep_invalid_path_fails_fast(tmp_path: Path) -> None:
    out_dir = tmp_path / "bad-path-out"
    rc = main(
        [
            "sweep",
            str(ARCHETYPES_DIR / "ribbon-weave.json"),
            "--set",
            "layers.99.halo=0.5",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 1
    assert not (out_dir / "variants.json").exists()


def test_sweep_manifest_with_set_override_and_failed_variant_handling(tmp_path: Path) -> None:
    spec_copy = tmp_path / "base.json"
    spec_copy.write_text(
        json.dumps(
            {
                "name": "Subtract Sweep",
                "concept": "Square with center cutout",
                "unit": 40,
                "layers": [
                    {
                        "id": "base",
                        "op": "unite",
                        "shapes": [{"type": "rect", "center": [0, 0], "width": 5, "height": 5}],
                    },
                    {
                        "id": "cut",
                        "op": "subtract",
                        "halo": 0.2,
                        "shapes": [{"type": "rect", "center": [0, 0], "width": 3.0, "height": 3.0}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    sweep_manifest = tmp_path / "sweep.json"
    sweep_manifest.write_text(
        json.dumps(
            {
                "axes": [
                    {"path": "layers.1.halo", "values": [0.1, 0.2]},
                    {"path": "post.invert", "values": [False, True]},
                ],
                "max_variants": 12,
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "manifest-out"
    rc = main(
        [
            "sweep",
            str(spec_copy),
            "--sweep",
            str(sweep_manifest),
            "--set",
            "post.invert=false",
            "--set",
            "layers.1.halo=0.2,3.0",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    variants = json.loads((out_dir / "variants.json").read_text(encoding="utf-8"))
    assert len(variants) == 2
    assert variants[0]["passed"] is True
    assert "error" in variants[1]
    assert variants[1]["passed"] is False
    assert (out_dir / "contact_sheet.png").is_file()
