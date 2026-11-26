"""Tests for matched 24x24 icon set compiler and 3x3 seamless pattern tiler."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
import resvg_py

from brandspec.cli import main
from brandspec.engines.icons.compiler import compile_icon_set
from brandspec.engines.icons.schema import IconSetSpec
from brandspec.engines.pattern.compiler import compile_pattern
from brandspec.engines.pattern.schema import PatternSpec


def test_icon_set_inherits_mark_corner_and_stroke_defaults(tmp_path: Path) -> None:
    mark_path = tmp_path / "base-mark.json"
    mark_path.write_text(
        json.dumps(
            {
                "name": "Base Mark",
                "concept": "Rounded mitered path",
                "unit": 40,
                "layers": [
                    {
                        "id": "frame",
                        "op": "unite",
                        "shapes": [
                            {
                                "type": "grid_path",
                                "points": [[-3, -3], [3, -3], [3, 3], [-3, 3]],
                                "closed": True,
                                "width": 1.0,
                                "corner_radius": 0.5,
                                "cap": "round",
                                "join": "round",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    icons_spec_path = tmp_path / "icons.spec.json"
    icons_spec_path.write_text(
        json.dumps(
            {
                "name": "Core Icons",
                "inherits_mark": "base-mark.json",
                "stroke_width": 2.0,
                "icons": [
                    {
                        "id": "arrow-right",
                        "layers": [
                            {
                                "id": "shaft",
                                "op": "unite",
                                "shapes": [
                                    {"type": "grid_path", "points": [[-7, 0], [7, 0]]},
                                    {"type": "grid_path", "points": [[2, -5], [7, 0], [2, 5]]},
                                ],
                            }
                        ],
                    },
                    {
                        "id": "frame-box",
                        "layers": [
                            {
                                "id": "box",
                                "op": "unite",
                                "shapes": [
                                    {"type": "rect", "center": [0, 0], "width": 14, "height": 14},
                                ],
                            },
                            {
                                "id": "hole",
                                "op": "subtract",
                                "shapes": [
                                    {"type": "rect", "center": [0, 0], "width": 10, "height": 10},
                                ],
                            },
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "icons-out"
    assert main(["icons", "build", str(icons_spec_path), "--out-dir", str(out_dir)]) == 0
    assert (out_dir / "icons-sheet.png").is_file()

    compiled_set = compile_icon_set(
        IconSetSpec.model_validate(json.loads(icons_spec_path.read_text(encoding="utf-8"))),
        base_dir=tmp_path,
    )
    assert compiled_set.spec.cap == "round"
    assert compiled_set.spec.join == "round"
    assert compiled_set.spec.corner_radius == 0.5

    for icon in compiled_set.icons:
        svg = (out_dir / f"{icon.id}.svg").read_text(encoding="utf-8")
        assert 'viewBox="0 0 24 24"' in svg
        assert icon.metrics.passed

    fractional = compile_icon_set(
        IconSetSpec.model_validate(
            {
                "name": "Fractional",
                "stroke_width": 1.5,
                "icons": [
                    {
                        "id": "line",
                        "layers": [
                            {
                                "id": "l",
                                "op": "unite",
                                "shapes": [{"type": "grid_path", "points": [[-6, 0], [6, 0]]}],
                            }
                        ],
                    }
                ],
            }
        )
    )
    assert not fractional.icons[0].metrics.passed
    assert any("Non-integer stroke_width" in w for w in fractional.icons[0].metrics.warnings)


def test_pattern_tile_wraps_seamlessly(tmp_path: Path) -> None:
    pat_spec_path = tmp_path / "pattern.spec.json"
    pat_spec_path.write_text(
        json.dumps(
            {
                "name": "Diagonal Cross Tile",
                "tile_width": 4.0,
                "tile_height": 4.0,
                "unit": 40.0,
                "layers": [
                    {
                        "id": "diag",
                        "op": "unite",
                        "shapes": [
                            {
                                "type": "grid_path",
                                "points": [[-2.0, -2.0], [2.0, 2.0]],
                                "width": 0.6,
                                "cap": "butt",
                                "join": "miter",
                            },
                            {
                                "type": "circle",
                                "center": [2.0, 0.0],
                                "radius": 0.7,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "pattern-out"
    assert main(["pattern", "build", str(pat_spec_path), "--out-dir", str(out_dir)]) == 0
    assert (out_dir / "tile.svg").is_file()
    assert (out_dir / "pattern.svg").is_file()

    compiled = compile_pattern(
        PatternSpec.model_validate(json.loads(pat_spec_path.read_text(encoding="utf-8")))
    )
    w = int(compiled.tile_width_px)
    h = int(compiled.tile_height_px)

    tile_png = resvg_py.svg_to_bytes(
        svg_string=compiled.tile_svg_markup,
        width=w,
        height=h,
        background="#ffffff",
    )
    tile_arr = np.asarray(Image.open(io.BytesIO(tile_png)).convert("L"))

    pat_png = resvg_py.svg_to_bytes(
        svg_string=compiled.pattern_svg_markup,
        width=2 * w,
        height=2 * h,
        background="#ffffff",
    )
    pat_arr = np.asarray(Image.open(io.BytesIO(pat_png)).convert("L"))

    # Every 2x2 quadrant must match the single tile, and opposite edges must wrap cleanly
    assert np.mean(np.abs(pat_arr[:h, :w].astype(float) - tile_arr.astype(float))) < 2.0
    assert np.mean(np.abs(pat_arr[:h, w:].astype(float) - tile_arr.astype(float))) < 2.0
    assert np.mean(np.abs(pat_arr[h:, :w].astype(float) - tile_arr.astype(float))) < 2.0
    assert np.mean(np.abs(pat_arr[h:, w:].astype(float) - tile_arr.astype(float))) < 2.0
    # Left and right edges / top and bottom edges of the tile align seamlessly
    assert np.mean(np.abs(tile_arr[:, 0].astype(float) - tile_arr[:, -1].astype(float))) < 15.0
    assert np.mean(np.abs(tile_arr[0, :].astype(float) - tile_arr[-1, :].astype(float))) < 15.0
