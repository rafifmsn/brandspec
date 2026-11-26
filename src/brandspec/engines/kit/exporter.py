"""Deterministic multi-format brand kit exporter using resvg-py and Pillow."""

from __future__ import annotations

import io
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw
import resvg_py

from ...core.paths import render_svg_doc
from ..mark.compiler import compile_spec
from ..mark.schema import MarkSpec
from ..tokens.schema import TokensSpec
from .schema import KitSpec

PATH_D_RE = re.compile(r'<path[^>]*\sd="([^"]*)"')
VIEWBOX_RE = re.compile(r'viewBox="0\s+0\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)"')


def _resolve_rel(base_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else (base_dir / p)


def _extract_svg_path_and_size(svg_text: str) -> tuple[str, int]:
    d_match = PATH_D_RE.search(svg_text)
    if not d_match:
        raise ValueError("Source SVG does not contain a <path d=...> element.")
    vb_match = VIEWBOX_RE.search(svg_text)
    canvas_size = int(round(float(vb_match.group(1)))) if vb_match else 1000
    return d_match.group(1), canvas_size


def _rasterize_rgba(svg_text: str, size: int) -> Image.Image:
    png_bytes = resvg_py.svg_to_bytes(svg_string=svg_text, width=size, height=size)
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def _compose_square_icon(
    svg_text: str,
    size: int,
    bg_hex: str,
    padding_ratio: float,
) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), bg_hex)
    inner_size = max(1, int(round(size * (1.0 - 2.0 * padding_ratio))))
    mark_img = _rasterize_rgba(svg_text, inner_size)
    offset = (size - inner_size) // 2
    canvas.paste(mark_img, (offset, offset), mask=mark_img)
    return canvas


def _render_tokens_css(tokens: TokensSpec) -> str:
    lines = [
        ":root {",
        f"  --brand-bg-canvas: {tokens.bg_canvas};",
        f"  --brand-bg-surface: {tokens.bg_surface};",
        f"  --brand-border: {tokens.border};",
        f"  --brand-text-primary: {tokens.text_primary};",
        f"  --brand-text-secondary: {tokens.text_secondary};",
        f"  --brand-mark-light: {tokens.mark_light};",
        f"  --brand-mark-dark: {tokens.mark_dark};",
    ]
    if tokens.accent is not None:
        lines.append(f"  --brand-accent: {tokens.accent};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _render_og_card(
    kit: KitSpec,
    tokens: TokensSpec,
    mark_light_svg: str,
) -> Image.Image:
    w, h = kit.og_size
    img = Image.new("RGB", (w, h), tokens.bg_canvas)
    draw = ImageDraw.Draw(img)

    margin = 48
    draw.rectangle(
        [margin, margin, w - margin, h - margin],
        fill=tokens.bg_surface,
        outline=tokens.border,
        width=2,
    )

    mark_size = max(96, int(h * 0.36))
    mark_rgba = _rasterize_rgba(mark_light_svg, mark_size)
    mark_x = margin + 64
    mark_y = (h - mark_size) // 2
    img.paste(mark_rgba, (mark_x, mark_y), mask=mark_rgba)

    text_x = mark_x + mark_size + 56
    title_y = h // 2 - 28
    draw.text((text_x, title_y), kit.brand_name, fill=tokens.text_primary)
    if kit.tagline:
        draw.text((text_x, title_y + 28), kit.tagline, fill=tokens.text_secondary)
    return img


def export_kit(spec: KitSpec, base_dir: Path, out_dir: Path) -> dict[str, Path]:
    """Export SVG variants, favicon.ico, PWA icons, OG card, and tokens.css."""
    if spec.mark_svg:
        svg_path = _resolve_rel(base_dir, spec.mark_svg)
        svg_d, canvas_size = _extract_svg_path_and_size(svg_path.read_text(encoding="utf-8"))
    else:
        assert spec.mark_spec is not None
        mark_path = _resolve_rel(base_dir, spec.mark_spec)
        mark_spec = MarkSpec.model_validate(json.loads(mark_path.read_text(encoding="utf-8")))
        compiled = compile_spec(mark_spec)
        svg_d = compiled.svg_d
        canvas_size = compiled.spec.post.canvas_size

    tokens = (
        TokensSpec.model_validate(
            json.loads(_resolve_rel(base_dir, spec.tokens_spec).read_text(encoding="utf-8"))
        )
        if spec.tokens_spec
        else TokensSpec()
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = escape(spec.brand_name)

    logo_dark_svg = render_svg_doc(svg_d, canvas_size, fill=tokens.mark_light, title=safe_title)
    logo_light_svg = render_svg_doc(svg_d, canvas_size, fill=tokens.mark_dark, title=safe_title)
    logo_mono_svg = render_svg_doc(svg_d, canvas_size, fill="#000000", title=safe_title)

    dark_svg_path = out_dir / "logo-dark.svg"
    light_svg_path = out_dir / "logo-light.svg"
    mono_svg_path = out_dir / "logo-mono.svg"
    dark_svg_path.write_text(logo_dark_svg, encoding="utf-8")
    light_svg_path.write_text(logo_light_svg, encoding="utf-8")
    mono_svg_path.write_text(logo_mono_svg, encoding="utf-8")

    ico_base = _compose_square_icon(logo_dark_svg, 64, "#ffffff", 0.1)
    ico_path = out_dir / "favicon.ico"
    ico_base.save(ico_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    apple_path = out_dir / "apple-touch-icon.png"
    _compose_square_icon(logo_light_svg, 180, tokens.bg_canvas, 0.14).save(apple_path, format="PNG")

    icon_192_path = out_dir / "icon-192.png"
    _compose_square_icon(logo_light_svg, 192, tokens.bg_canvas, 0.14).save(
        icon_192_path, format="PNG"
    )

    icon_512_path = out_dir / "icon-512.png"
    _compose_square_icon(logo_light_svg, 512, tokens.bg_canvas, 0.14).save(
        icon_512_path, format="PNG"
    )

    maskable_path = out_dir / "icon-maskable-512.png"
    _compose_square_icon(logo_light_svg, 512, tokens.bg_canvas, spec.pwa_padding).save(
        maskable_path, format="PNG"
    )

    og_path = out_dir / "og-card.png"
    _render_og_card(spec, tokens, logo_light_svg).save(og_path, format="PNG")

    css_path = out_dir / "tokens.css"
    css_path.write_text(_render_tokens_css(tokens), encoding="utf-8")

    return {
        "logo_dark": dark_svg_path,
        "logo_light": light_svg_path,
        "logo_mono": mono_svg_path,
        "favicon": ico_path,
        "apple_touch_icon": apple_path,
        "icon_192": icon_192_path,
        "icon_512": icon_512_path,
        "icon_maskable_512": maskable_path,
        "og_card": og_path,
        "tokens_css": css_path,
    }
