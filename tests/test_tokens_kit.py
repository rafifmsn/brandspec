"""Tests for tokens contrast audit, palette extraction, and kit export."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path

import numpy as np
from PIL import Image

from brandspec.cli import main
from brandspec.engines.kit.schema import BrandManifest

ARCHETYPES_DIR = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))


def test_contrast_audit_flags_low_contrast_pair(tmp_path: Path) -> None:
    good_tokens = tmp_path / "good.tokens.spec.json"
    good_tokens.write_text(
        json.dumps(
            {
                "name": "Good",
                "bg_canvas": "#0b0c0e",
                "bg_surface": "#121316",
                "border": "#26282e",
                "text_primary": "#f3f4f6",
                "text_secondary": "#d1d5db",
                "mark_light": "#111111",
                "mark_dark": "#f3f4f6",
            }
        ),
        encoding="utf-8",
    )
    assert main(["tokens", "check", str(good_tokens)]) == 0

    bad_tokens = tmp_path / "bad.tokens.spec.json"
    bad_tokens.write_text(
        json.dumps(
            {
                "name": "Low Contrast",
                "bg_canvas": "#121316",
                "bg_surface": "#181a1f",
                "border": "#26282e",
                "text_primary": "#26282e",
                "text_secondary": "#2f3239",
                "mark_light": "#e5e7eb",
                "mark_dark": "#1f2228",
            }
        ),
        encoding="utf-8",
    )
    assert main(["tokens", "check", str(bad_tokens)]) == 2


def test_palette_extract_returns_deterministic_hex_tokens(tmp_path: Path) -> None:
    color_img = tmp_path / "brand-ref.png"
    arr = np.zeros((48, 48, 3), dtype=np.uint8)
    arr[:24, :24] = [15, 18, 24]
    arr[:24, 24:] = [240, 244, 248]
    arr[24:, :24] = [30, 90, 200]
    arr[24:, 24:] = [180, 184, 190]
    Image.fromarray(arr, mode="RGB").save(color_img)

    out_a = tmp_path / "a.tokens.spec.json"
    out_b = tmp_path / "b.tokens.spec.json"
    assert main(["palette", "extract", str(color_img), "--colors", "4", "--out", str(out_a)]) == 0
    assert main(["palette", "extract", str(color_img), "--colors", "4", "--out", str(out_b)]) == 0
    assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")
    assert main(["tokens", "check", str(out_a)]) == 0

    gray_img = tmp_path / "gray.png"
    gray_arr = np.zeros((32, 32, 3), dtype=np.uint8)
    gray_arr[:16, :] = [20, 20, 20]
    gray_arr[16:, :] = [235, 235, 235]
    Image.fromarray(gray_arr, mode="RGB").save(gray_img)
    gray_out = tmp_path / "gray.tokens.spec.json"
    assert main(["palette", "extract", str(gray_img), "--colors", "4", "--out", str(gray_out)]) == 0
    gray_data = json.loads(gray_out.read_text(encoding="utf-8"))
    assert gray_data["accent"] is None
    assert main(["tokens", "check", str(gray_out)]) == 0


def test_kit_export_generates_valid_ico_pwa_and_svg_variants(tmp_path: Path) -> None:
    build_dir = tmp_path / "mark"
    assert (
        main(["build", str(ARCHETYPES_DIR / "ribbon-weave.json"), "--out-dir", str(build_dir)]) == 0
    )

    tokens_path = tmp_path / "tokens.spec.json"
    tokens_path.write_text(
        json.dumps(
            {
                "name": "Ribbon",
                "bg_canvas": "#0b0c0e",
                "bg_surface": "#121316",
                "border": "#26282e",
                "text_primary": "#f3f4f6",
                "text_secondary": "#d1d5db",
                "mark_light": "#111111",
                "mark_dark": "#ffffff",
                "accent": "#60a5fa",
            }
        ),
        encoding="utf-8",
    )

    kit_spec_path = tmp_path / "kit.spec.json"
    kit_spec_path.write_text(
        json.dumps(
            {
                "brand_name": "Ribbon Studio",
                "tagline": "Deterministic brand geometry",
                "mark_svg": str(build_dir / "logo.svg"),
                "tokens_spec": str(tokens_path),
                "pwa_padding": 0.25,
            }
        ),
        encoding="utf-8",
    )

    kit_out = tmp_path / "kit-out"
    assert main(["kit", "build", str(kit_spec_path), "--out-dir", str(kit_out)]) == 0

    for fname in (
        "logo-dark.svg",
        "logo-light.svg",
        "logo-mono.svg",
        "favicon.ico",
        "apple-touch-icon.png",
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-512.png",
        "og-card.png",
        "tokens.css",
    ):
        assert (kit_out / fname).is_file(), f"Missing {fname}"

    with Image.open(kit_out / "favicon.ico") as ico:
        assert ico.format == "ICO"
    with Image.open(kit_out / "icon-192.png") as p192:
        assert p192.size == (192, 192)
    with Image.open(kit_out / "icon-maskable-512.png") as maskable:
        assert maskable.size == (512, 512)
        arr = np.asarray(maskable.convert("RGB"))
        bg = arr[0, 0]
        assert np.all(arr[:100, :] == bg)
    with Image.open(kit_out / "og-card.png") as og:
        assert og.size == (1200, 630)

    css = (kit_out / "tokens.css").read_text(encoding="utf-8")
    assert "--brand-bg-canvas: #0b0c0e;" in css
    assert "--brand-accent: #60a5fa;" in css

    manifest = BrandManifest.model_validate(
        {"name": "Ribbon Studio", "tokens": "tokens.spec.json", "kit": "kit.spec.json"}
    )
    assert manifest.name == "Ribbon Studio"
