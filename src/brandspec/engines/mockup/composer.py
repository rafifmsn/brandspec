"""Deterministic SVG surface layout composer for mockup slots."""

from __future__ import annotations

from dataclasses import dataclass
import io
import re
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageDraw
import resvg_py

from .schema import MockupSlot

VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')
SVG_OPEN_RE = re.compile(r"<svg[^>]*>", re.IGNORECASE)
SVG_CLOSE_RE = re.compile(r"</svg>\s*$", re.IGNORECASE)
TITLE_RE = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
FILL_ATTR_RE = re.compile(r'\bfill="([^"]+)"')
DEFS_BLOCK_RE = re.compile(r"<defs>.*?</defs>", re.IGNORECASE | re.DOTALL)

FONT_STACK = "Noto Sans, Liberation Sans, DejaVu Sans, sans-serif"
DISPLAY_FONT_STACK = FONT_STACK


@dataclass(frozen=True)
class MockupContext:
    brand_name: str = "Brandspec"
    headline: str = "Precision built for scale."
    tagline: str = "Deterministic identity across every surface."
    website: str = "brandspec.com"
    accent: str = "#525252"
    surface_dark: str = "#111318"
    surface_light: str = "#f5f4ef"
    text_light: str = "#f9fafb"
    text_dark: str = "#111318"


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (17, 19, 24)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _is_dark(hex_color: str) -> bool:
    r, g, b = _hex_rgb(hex_color)
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return lum < 0.52


def _contrast_text(bg_hex: str, light: str = "#f9fafb", dark: str = "#111318") -> str:
    return light if _is_dark(bg_hex) else dark


def _shift_hex(hex_color: str, delta: int) -> str:
    r, g, b = _hex_rgb(hex_color)
    nr = max(0, min(255, r + delta))
    ng = max(0, min(255, g + delta))
    nb = max(0, min(255, b + delta))
    return f"#{nr:02x}{ng:02x}{nb:02x}"


def _surface_gradient_defs(base_hex: str, grad_id: str = "surf-bg") -> tuple[str, str]:
    """Build a subtle tonal gradient so colored/dark/light surfaces never look flat."""
    r, g, b = _hex_rgb(base_hex)
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    if lum < 0.18:
        c1 = _shift_hex(base_hex, 26)
        c2 = _shift_hex(base_hex, 6)
    elif lum > 0.82:
        c1 = "#fafaf8"
        c2 = "#eae8e2"
    else:
        c1 = _shift_hex(base_hex, 18)
        c2 = _shift_hex(base_hex, -24)
    defs = (
        f'<defs><linearGradient id="{grad_id}" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="{c1}"/>'
        f'<stop offset="100%" stop-color="{c2}"/>'
        f"</linearGradient></defs>"
    )
    return defs, f"url(#{grad_id})"


def _auto_mark_fill(svg_text: str, bg_hex: str) -> str | None:
    """Return a contrast override hex if svg_text has low contrast against bg_hex."""
    bg_dark = _is_dark(bg_hex)
    if "linearGradient" in svg_text or "radialGradient" in svg_text:
        return "#f9fafb" if bg_dark else None
    fills = [m for m in FILL_ATTR_RE.findall(svg_text) if m != "none" and not m.startswith("url(")]
    if not fills:
        return _contrast_text(bg_hex)
    fill_hex = fills[0]
    if bg_dark and _is_dark(fill_hex):
        return "#f9fafb"
    if not bg_dark and not _is_dark(fill_hex):
        return "#111318"
    return None


def _wrap_lines(text: str, max_chars: int, max_lines: int = 3) -> list[str]:
    words = text.strip().split()
    if not words:
        return []
    lines: list[str] = []
    curr = words[0]
    for word in words[1:]:
        if len(curr) + 1 + len(word) <= max_chars:
            curr += " " + word
        else:
            lines.append(curr)
            curr = word
            if len(lines) >= max_lines:
                break
    if len(lines) < max_lines:
        lines.append(curr)
    return lines[:max_lines]


def _extract_svg_fragment(svg_text: str, mono_fill: str | None = None) -> tuple[str, str]:
    """Return (viewBox, inner_markup) from standalone logo SVG, optionally recolored."""
    vb_match = VIEWBOX_RE.search(svg_text)
    vb = vb_match.group(1) if vb_match else "0 0 1000 1000"
    inner = SVG_OPEN_RE.sub("", svg_text, count=1)
    inner = SVG_CLOSE_RE.sub("", inner, count=1)
    inner = TITLE_RE.sub("", inner)
    if mono_fill is not None:
        inner = DEFS_BLOCK_RE.sub("", inner)
        inner = FILL_ATTR_RE.sub(
            lambda m: 'fill="none"' if m.group(1) == "none" else f'fill="{mono_fill}"',
            inner,
        )
    return vb, inner.strip()


def _tight_viewbox(svg_text: str, vb: str) -> str:
    """Compute a tight ink viewBox so wide lockups and wordmarks fill mockup slots cleanly."""
    parts = vb.replace(",", " ").split()
    if len(parts) != 4:
        return vb
    try:
        vx, vy, vw, vh = (float(p) for p in parts)
    except ValueError:
        return vb
    if vw <= 0 or vh <= 0:
        return vb
    sample = 200
    try:
        png_bytes = resvg_py.svg_to_bytes(svg_string=svg_text, width=sample, height=sample)
        alpha = np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGBA"))[:, :, 3]
    except Exception:
        return vb
    ys, xs = np.nonzero(alpha > 10)
    if len(xs) == 0:
        return vb
    x0 = vx + (int(xs.min()) / sample) * vw
    y0 = vy + (int(ys.min()) / sample) * vh
    w_ink = max(vw * 0.05, ((int(xs.max()) - int(xs.min()) + 1) / sample) * vw)
    h_ink = max(vh * 0.05, ((int(ys.max()) - int(ys.min()) + 1) / sample) * vh)
    return f"{x0:.1f} {y0:.1f} {w_ink:.1f} {h_ink:.1f}"


def _nested_mark(
    svg_text: str,
    x: float,
    y: float,
    width: float,
    height: float | None = None,
    mono_fill: str | None = None,
    preserve_aspect: str = "xMidYMid meet",
) -> str:
    h = width if height is None else height
    vb, inner = _extract_svg_fragment(svg_text, mono_fill=mono_fill)
    tight_vb = _tight_viewbox(svg_text, vb)
    return (
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{h:.1f}" '
        f'viewBox="{escape(tight_vb)}" preserveAspectRatio="{preserve_aspect}">{inner}</svg>'
    )


def _svg_lines(
    lines: list[str],
    x: float,
    y: float,
    font_size: float,
    line_height: float,
    fill: str,
    weight: str = "600",
    anchor: str = "start",
    letter_spacing: float = -0.02,
    font_family: str = DISPLAY_FONT_STACK,
) -> str:
    parts = []
    for idx, line in enumerate(lines):
        ly = y + idx * line_height
        parts.append(
            f'<text x="{x:.1f}" y="{ly:.1f}" fill="{fill}" '
            f'font-family="{font_family}" font-size="{font_size:.1f}" '
            f'font-weight="{weight}" text-anchor="{anchor}" '
            f'letter-spacing="{letter_spacing}em">{escape(line)}</text>'
        )
    return "".join(parts)


def _compose_slot_svg(slot: MockupSlot, logo_svg: str, ctx: MockupContext) -> str:
    w, h = slot.design_size
    style = slot.template_style

    if style == "mark_only":
        size = min(w, h) * 0.56
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{_nested_mark(logo_svg, 0.5 * (w - size), 0.5 * (h - size), size)}"
            f"</svg>"
        )

    if style == "card_minimal":
        mark_w = w * 0.34
        mark_h = h * 0.22
        pad_x = w * 0.08
        pad_y = h * 0.13
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{_nested_mark(logo_svg, pad_x, pad_y, mark_w, mark_h, preserve_aspect='xMinYMid meet')}"
            f'<text x="{w - pad_x:.1f}" y="{pad_y + mark_h * 0.55:.1f}" fill="{ctx.accent}" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.055:.1f}" font-weight="600" '
            f'text-anchor="end">{escape(ctx.website)}</text>'
            f'<text x="{pad_x:.1f}" y="{h - pad_y - h * 0.095:.1f}" fill="{ctx.text_dark}" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.105:.1f}" font-weight="700" '
            f'letter-spacing="-0.02em">{escape(ctx.brand_name)}</text>'
            f'<text x="{pad_x:.1f}" y="{h - pad_y:.1f}" fill="#525866" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.052:.1f}" font-weight="500">'
            f"{escape(ctx.tagline)}</text>"
            f"</svg>"
        )

    if style == "card_editorial":
        bg = ctx.accent
        fg = _contrast_text(bg, ctx.text_light, ctx.text_dark)
        s_defs, s_fill = _surface_gradient_defs(bg, "card-grad")
        mark_w = w * 0.56
        mark_h = h * 0.28
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{s_defs}"
            f'<rect width="{w}" height="{h}" fill="{s_fill}"/>'
            f"{_nested_mark(logo_svg, 0.5 * (w - mark_w), h * 0.20, mark_w, mark_h, mono_fill=fg)}"
            f'<text x="{0.5 * w:.1f}" y="{h * 0.67:.1f}" fill="{fg}" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.13:.1f}" font-weight="700" '
            f'text-anchor="middle" letter-spacing="0.02em">{escape(ctx.brand_name)}</text>'
            f'<text x="{0.5 * w:.1f}" y="{h * 0.85:.1f}" fill="{fg}" fill-opacity="0.78" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.048:.1f}" font-weight="500" '
            f'text-anchor="middle">{escape(ctx.website)}</text>'
            f"</svg>"
        )

    if style == "box_seal":
        ink = "#1c1917"
        mark_w = w * 0.48
        mark_h = h * 0.30
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{_nested_mark(logo_svg, 0.5 * (w - mark_w), h * 0.18, mark_w, mark_h, mono_fill=ink)}"
            f'<text x="{0.5 * w:.1f}" y="{h * 0.64:.1f}" fill="{ink}" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.11:.1f}" font-weight="700" '
            f'text-anchor="middle" letter-spacing="-0.02em">{escape(ctx.brand_name)}</text>'
            f'<text x="{0.5 * w:.1f}" y="{h * 0.77:.1f}" fill="{ink}" fill-opacity="0.75" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.046:.1f}" font-weight="600" '
            f'text-anchor="middle" letter-spacing="0.12em">{escape(ctx.website.upper())}</text>'
            f"</svg>"
        )

    if style == "banner_vertical":
        bg = ctx.accent
        fg = _contrast_text(bg, ctx.text_light, ctx.text_dark)
        s_defs, s_fill = _surface_gradient_defs(bg, "banner-grad")
        mark_w = w * 0.72
        mark_h = h * 0.34
        lines = _wrap_lines(ctx.headline, max_chars=14, max_lines=3)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{s_defs}"
            f'<rect width="{w}" height="{h}" fill="{s_fill}"/>'
            f'<text x="{w * 0.10:.1f}" y="{h * 0.09:.1f}" fill="{fg}" fill-opacity="0.85" '
            f'font-family="{FONT_STACK}" font-size="{w * 0.055:.1f}" font-weight="700" '
            f'letter-spacing="0.01em">{escape(ctx.brand_name)}</text>'
            f"{_nested_mark(logo_svg, 0.5 * (w - mark_w), h * 0.17, mark_w, mark_h, mono_fill=fg)}"
            f"{_svg_lines(lines, w * 0.10, h * 0.64, w * 0.105, w * 0.12, fg)}"
            f'<text x="{w * 0.10:.1f}" y="{h * 0.93:.1f}" fill="{fg}" fill-opacity="0.82" '
            f'font-family="{FONT_STACK}" font-size="{w * 0.045:.1f}" font-weight="500">'
            f"{escape(ctx.website)}</text>"
            f"</svg>"
        )

    if style == "billboard_split":
        is_wide = (w / max(1, h)) >= 3.0
        bg = ctx.surface_light if is_wide else ctx.accent
        fg = _contrast_text(bg, ctx.text_light, ctx.text_dark)
        s_defs, s_fill = _surface_gradient_defs(bg, "bb-grad")
        mark_fill = _auto_mark_fill(logo_svg, bg) if bg == ctx.surface_light else fg
        pad_x = w * 0.06
        mark_w = w * (0.24 if is_wide else 0.28)
        mark_h = h * (0.56 if is_wide else 0.48)
        char_len = max(1, len(ctx.headline.strip()))
        max_chars = (28 if is_wide else 22) if char_len <= 34 else (34 if is_wide else 28)
        lines = _wrap_lines(ctx.headline, max_chars=max_chars, max_lines=3)
        base_sz = min(h * 0.130, w * 0.048) if not is_wide else h * 0.175
        if len(lines) >= 3 or char_len > 36:
            base_sz *= 0.78
        elif len(lines) == 2 and char_len > 24:
            base_sz *= 0.90
        line_h = base_sz * 1.16
        block_h = len(lines) * line_h
        start_y = max(h * 0.24, 0.44 * h - 0.5 * block_h + base_sz * 0.85)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{s_defs}"
            f'<rect width="{w}" height="{h}" fill="{s_fill}"/>'
            f"{_svg_lines(lines, pad_x, start_y, base_sz, line_h, fg, weight='500')}"
            f'<text x="{pad_x:.1f}" y="{h * 0.86:.1f}" fill="{fg}" fill-opacity="0.76" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.056:.1f}" font-weight="500">'
            f"{escape(ctx.brand_name)}  ·  {escape(ctx.website)}</text>"
            f"{_nested_mark(logo_svg, w - pad_x - mark_w, 0.5 * (h - mark_h), mark_w, mark_h, mono_fill=mark_fill, preserve_aspect='xMaxYMid meet')}"
            f"</svg>"
        )

    if style == "hoarding_panel_left":
        bg = ctx.surface_light
        fg = ctx.text_dark
        mark_s = w * 0.34
        lines = _wrap_lines(ctx.headline, max_chars=14, max_lines=3)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>'
            f'<text x="{w * 0.12:.1f}" y="{h * 0.13:.1f}" fill="{fg}" '
            f'font-family="{FONT_STACK}" font-size="{w * 0.075:.1f}" font-weight="700">'
            f"{escape(ctx.brand_name)}</text>"
            f"{_svg_lines(lines, w * 0.12, h * 0.42, w * 0.105, w * 0.125, fg)}"
            f"{_nested_mark(logo_svg, w - mark_s - w * 0.10, h - mark_s - h * 0.08, mark_s, mono_fill=_auto_mark_fill(logo_svg, bg))}"
            f"</svg>"
        )

    if style == "hoarding_panel_mid":
        bg = ctx.surface_dark
        fg = ctx.text_light
        mark_w = w * 0.72
        mark_h = h * 0.48
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>'
            f'<text x="{0.5 * w:.1f}" y="{h * 0.13:.1f}" fill="{fg}" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.065:.1f}" font-weight="700" '
            f'text-anchor="middle">{escape(ctx.brand_name)}</text>'
            f"{_nested_mark(logo_svg, 0.5 * (w - mark_w), 0.5 * (h - mark_h), mark_w, mark_h, mono_fill=_auto_mark_fill(logo_svg, bg))}"
            f'<text x="{0.5 * w:.1f}" y="{h * 0.90:.1f}" fill="{fg}" fill-opacity="0.72" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.045:.1f}" font-weight="500" '
            f'text-anchor="middle">{escape(ctx.website)}</text>'
            f"</svg>"
        )

    if style == "hoarding_panel_right":
        bg = ctx.accent
        fg = _contrast_text(bg, ctx.text_light, ctx.text_dark)
        mark_w = w * 0.34
        mark_h = h * 0.44
        lines = _wrap_lines(ctx.tagline, max_chars=20, max_lines=3)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<defs><linearGradient id="hoard-grad" x1="0%" y1="0%" x2="100%" y2="100%">'
            f'<stop offset="0%" stop-color="{bg}"/>'
            f'<stop offset="100%" stop-color="{ctx.surface_dark}"/></linearGradient></defs>'
            f'<rect width="{w}" height="{h}" fill="url(#hoard-grad)"/>'
            f"{_nested_mark(logo_svg, w * 0.08, 0.5 * (h - mark_h), mark_w, mark_h, mono_fill=ctx.text_light, preserve_aspect='xMinYMid meet')}"
            f"{_svg_lines(lines, w * 0.50, h * 0.38, h * 0.074, h * 0.092, ctx.text_light)}"
            f'<text x="{w * 0.50:.1f}" y="{h * 0.84:.1f}" fill="{ctx.text_light}" fill-opacity="0.80" '
            f'font-family="{FONT_STACK}" font-size="{h * 0.048:.1f}" font-weight="600">'
            f"{escape(ctx.website)}</text>"
            f"</svg>"
        )

    # phone_splash
    mark_w = w * 0.58
    mark_h = h * 0.20
    lines = _wrap_lines(ctx.tagline, max_chars=22, max_lines=2)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f'<defs><radialGradient id="phone-glow" cx="50%" cy="40%" r="55%">'
        f'<stop offset="0%" stop-color="{ctx.accent}" stop-opacity="0.28"/>'
        f'<stop offset="100%" stop-color="{ctx.surface_dark}" stop-opacity="0"/></radialGradient></defs>'
        f'<rect width="{w}" height="{h}" fill="{ctx.surface_dark}"/>'
        f'<rect width="{w}" height="{h}" fill="url(#phone-glow)"/>'
        f'<rect x="{w * 0.36:.1f}" y="{h * 0.03:.1f}" width="{w * 0.28:.1f}" height="{h * 0.018:.1f}" '
        f'rx="{h * 0.009:.1f}" fill="#000000"/>'
        f"{_nested_mark(logo_svg, 0.5 * (w - mark_w), h * 0.27, mark_w, mark_h, mono_fill=_auto_mark_fill(logo_svg, ctx.surface_dark))}"
        f'<text x="{0.5 * w:.1f}" y="{h * 0.55:.1f}" fill="{ctx.text_light}" '
        f'font-family="{FONT_STACK}" font-size="{w * 0.088:.1f}" font-weight="700" '
        f'text-anchor="middle">{escape(ctx.brand_name)}</text>'
        f"{_svg_lines(lines, 0.5 * w, h * 0.61, w * 0.044, w * 0.058, '#9ca3af', weight='500', anchor='middle', letter_spacing=0.0)}"
        f'<rect x="{w * 0.14:.1f}" y="{h * 0.80:.1f}" width="{w * 0.72:.1f}" height="{h * 0.068:.1f}" '
        f'rx="{h * 0.034:.1f}" fill="{ctx.accent}"/>'
        f'<text x="{0.5 * w:.1f}" y="{h * 0.842:.1f}" fill="{_contrast_text(ctx.accent, ctx.text_light, ctx.text_dark)}" '
        f'font-family="{FONT_STACK}" font-size="{w * 0.048:.1f}" font-weight="700" '
        f'text-anchor="middle">Get Started</text>'
        f'<rect x="{w * 0.34:.1f}" y="{h * 0.965:.1f}" width="{w * 0.32:.1f}" height="{h * 0.006:.1f}" '
        f'rx="4" fill="#ffffff" fill-opacity="0.35"/>'
        f"</svg>"
    )


def render_slot_design(slot: MockupSlot, logo_svg: str, ctx: MockupContext) -> Image.Image:
    """Render an RGBA design image for a single mockup slot."""
    w, h = slot.design_size
    svg_doc = _compose_slot_svg(slot, logo_svg, ctx)
    png_bytes = resvg_py.svg_to_bytes(svg_string=svg_doc, width=w, height=h)
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    if slot.corner_radius > 0:
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=slot.corner_radius, fill=255)
        existing_alpha = img.getchannel("A")
        combined_alpha = Image.composite(existing_alpha, Image.new("L", (w, h), 0), mask)
        img.putalpha(combined_alpha)
    return img
