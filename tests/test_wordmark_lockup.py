"""Tests for fontTools vector wordmark outlining and mark+wordmark lockup composition."""

from __future__ import annotations

from importlib import resources
import json
import math
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import pytest

from brandspec.cli import main
from brandspec.engines.lockup.compiler import compile_lockup
from brandspec.engines.lockup.schema import LockupSpec
from brandspec.engines.wordmark.compiler import compile_wordmark
from brandspec.engines.wordmark.schema import WordmarkSpec

ARCHETYPES_DIR = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))


def _build_fixture_ttf(dest: Path) -> Path:
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A", "V", "I"])
    fb.setupCharacterMap({ord("A"): "A", ord("V"): "V", ord("I"): "I"})

    glyphs = {}

    pen_nd = TTGlyphPen(None)
    pen_nd.moveTo((50, 0))
    pen_nd.lineTo((50, 700))
    pen_nd.lineTo((450, 700))
    pen_nd.lineTo((450, 0))
    pen_nd.closePath()
    glyphs[".notdef"] = pen_nd.glyph()

    # Sharp triangular A with acute apex to exercise ink_trap + glyph outlining
    pen_a = TTGlyphPen(None)
    pen_a.moveTo((40, 0))
    pen_a.lineTo((300, 720))
    pen_a.lineTo((560, 0))
    pen_a.lineTo((440, 0))
    pen_a.lineTo((300, 420))
    pen_a.lineTo((160, 0))
    pen_a.closePath()
    glyphs["A"] = pen_a.glyph()

    pen_v = TTGlyphPen(None)
    pen_v.moveTo((40, 720))
    pen_v.lineTo((160, 720))
    pen_v.lineTo((300, 200))
    pen_v.lineTo((440, 720))
    pen_v.lineTo((560, 720))
    pen_v.lineTo((300, 0))
    pen_v.closePath()
    glyphs["V"] = pen_v.glyph()

    pen_i = TTGlyphPen(None)
    pen_i.moveTo((100, 0))
    pen_i.lineTo((100, 720))
    pen_i.lineTo((240, 720))
    pen_i.lineTo((240, 0))
    pen_i.closePath()
    glyphs["I"] = pen_i.glyph()

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({".notdef": (500, 50), "A": (600, 40), "V": (600, 40), "I": (340, 100)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "TestGeom", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(dest)
    return dest


def test_wordmark_outlines_glyphs_without_text_elements(tmp_path: Path) -> None:
    font_file = _build_fixture_ttf(tmp_path / "test-geom.ttf")
    wm_spec_path = tmp_path / "wordmark.spec.json"
    wm_spec_path.write_text(
        json.dumps(
            {
                "name": "Avi",
                "text": "avi",
                "case": "upper",
                "font_path": str(font_file),
                "tracking_em": -0.05,
                "kerning_pairs": {"AV": -0.08},
                "ink_trap": {"depth_u": 0.14, "width_u": 0.1, "angle_threshold_deg": 75.0},
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "wm-out"
    assert main(["wordmark", "build", str(wm_spec_path), "--out-dir", str(out_dir)]) == 0
    svg_text = (out_dir / "wordmark.svg").read_text(encoding="utf-8")
    assert "<text" not in svg_text
    assert "<path " in svg_text

    spec = WordmarkSpec.model_validate(json.loads(wm_spec_path.read_text(encoding="utf-8")))
    assert compile_wordmark(spec).svg_markup == svg_text

    bad_spec = WordmarkSpec.model_validate(
        {"name": "Missing", "text": "Z", "font_path": str(font_file)}
    )
    with pytest.raises(ValueError, match="Missing glyph for character 'Z'"):
        compile_wordmark(bad_spec)


def test_lockup_respects_clearspace_and_layout_bounds(tmp_path: Path) -> None:
    font_file = _build_fixture_ttf(tmp_path / "test-geom.ttf")
    wm_spec_path = tmp_path / "wordmark.spec.json"
    wm_spec_path.write_text(
        json.dumps(
            {
                "name": "Avi",
                "text": "AVI",
                "font_path": str(font_file),
                "unit": 40.0,
            }
        ),
        encoding="utf-8",
    )

    horiz_path = tmp_path / "lockup-horiz.spec.json"
    horiz_path.write_text(
        json.dumps(
            {
                "name": "Avi Horizontal",
                "mark_spec": str(ARCHETYPES_DIR / "ribbon-weave.json"),
                "wordmark_spec": str(wm_spec_path),
                "layout": "horizontal",
                "gap_u": 1.25,
                "clearspace_u": 1.0,
            }
        ),
        encoding="utf-8",
    )

    horiz = compile_lockup(
        LockupSpec.model_validate(json.loads(horiz_path.read_text(encoding="utf-8"))),
        base_dir=tmp_path,
    )
    mx0, _my0, mx1, _my1 = horiz.mark_bounds_svg
    wx0, _wy0, _wx1, _wy1 = horiz.wordmark_bounds_svg
    assert wx0 > mx1
    assert math.isclose(wx0 - mx1, horiz.gap_svg, abs_tol=1e-2)
    assert "clearspace-guides" in horiz.clearspace_svg_markup
    assert "<text" not in horiz.svg_markup

    stacked = compile_lockup(
        LockupSpec.model_validate(
            {
                "name": "Avi Stacked",
                "mark_spec": str(ARCHETYPES_DIR / "ribbon-weave.json"),
                "wordmark_spec": str(wm_spec_path),
                "layout": "stacked",
                "gap_u": 1.5,
                "clearspace_u": 1.0,
            }
        ),
        base_dir=tmp_path,
    )
    _smx0, _smy0, _smx1, smy1 = stacked.mark_bounds_svg
    _swx0, swy0, _swx1, _swy1 = stacked.wordmark_bounds_svg
    assert swy0 > smy1
    assert math.isclose(swy0 - smy1, stacked.gap_svg, abs_tol=1e-2)

    lockup_out = tmp_path / "lockup-out"
    assert main(["lockup", "build", str(horiz_path), "--out-dir", str(lockup_out)]) == 0
    assert (lockup_out / "lockup.svg").is_file()
    assert (lockup_out / "lockup-clearspace.svg").is_file()
