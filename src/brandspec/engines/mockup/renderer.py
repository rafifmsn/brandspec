"""Perspective homography warp and photographic compositing for mockups."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .composer import MockupContext, render_slot_design
from .schema import MockupManifest, MockupSlot


def builtin_templates_dir() -> Path:
    """Return the bundled mockup templates directory."""
    pkg = Path(str(resources.files("brandspec").joinpath("engines/mockup/templates")))
    if pkg.is_dir():
        return pkg
    return Path(__file__).resolve().parent / "templates"


def discover_templates(templates_dir: Path | None = None) -> list[tuple[Path, MockupManifest]]:
    """Discover and validate all mockup template manifests inside templates_dir."""
    root = templates_dir or builtin_templates_dir()
    if not root.is_dir():
        return []
    items: list[tuple[Path, MockupManifest]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        manifest_file = child / "manifest.json"
        if child.is_dir() and manifest_file.is_file():
            manifest = MockupManifest.model_validate(
                json.loads(manifest_file.read_text(encoding="utf-8"))
            )
            items.append((child, manifest))
    return items


def _perspective_coeffs(
    dst_quad: list[tuple[float, float]],
    src_size: tuple[int, int],
) -> tuple[float, ...]:
    """Solve 8-coefficient PIL PERSPECTIVE mapping from output (x, y) to source (u, v)."""
    w, h = float(src_size[0]), float(src_size[1])
    src_pts = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    matrix: list[list[float]] = []
    rhs: list[float] = []
    for (x, y), (u, v) in zip(dst_quad, src_pts):
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
        rhs.append(u)
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
        rhs.append(v)
    coeffs = np.linalg.solve(np.asarray(matrix, dtype=np.float64), np.asarray(rhs, dtype=np.float64))
    return tuple(float(c) for c in coeffs)


def _slot_coverage_mask(
    bg_size: tuple[int, int],
    slot: MockupSlot,
    coeffs: tuple[float, ...],
) -> np.ndarray:
    w, h = slot.design_size
    mask_src = Image.new("L", (w, h), 0)
    if slot.corner_radius > 0:
        ImageDraw.Draw(mask_src).rounded_rectangle(
            [0, 0, w - 1, h - 1],
            radius=slot.corner_radius,
            fill=255,
        )
    else:
        ImageDraw.Draw(mask_src).rectangle([0, 0, w - 1, h - 1], fill=255)
    warped = mask_src.transform(
        bg_size,
        Image.Transform.PERSPECTIVE,
        coeffs,
        resample=Image.Resampling.BILINEAR,
    )
    return np.asarray(warped, dtype=np.float32) / 255.0


def _composite_slot(
    bg_rgb: np.ndarray,
    slot: MockupSlot,
    design_rgba: Image.Image,
) -> np.ndarray:
    h_bg, w_bg, _ = bg_rgb.shape
    coeffs = _perspective_coeffs(slot.quad, slot.design_size)
    warped_rgba = design_rgba.transform(
        (w_bg, h_bg),
        Image.Transform.PERSPECTIVE,
        coeffs,
        resample=Image.Resampling.BICUBIC,
    )
    warped_arr = np.asarray(warped_rgba, dtype=np.float32) / 255.0
    design_rgb = warped_arr[:, :, :3]
    design_alpha = warped_arr[:, :, 3]
    quad_mask = _slot_coverage_mask((w_bg, h_bg), slot, coeffs)
    alpha = (design_alpha * quad_mask * slot.opacity)[..., None]

    mode = slot.blend_mode
    if mode == "multiply":
        blended = bg_rgb * design_rgb
        return bg_rgb * (1.0 - alpha) + blended * alpha

    if mode == "luminance_transfer":
        bg_gray = 0.2126 * bg_rgb[:, :, 0] + 0.7152 * bg_rgb[:, :, 1] + 0.0722 * bg_rgb[:, :, 2]
        inside = quad_mask > 0.5
        lit_ref = float(np.percentile(bg_gray[inside], 90)) if np.any(inside) else 0.9
        lit_ref = max(0.35, lit_ref)
        lum_ratio = np.clip(bg_gray / lit_ref, 0.32, 1.06)[..., None]
        lit_design = np.clip(design_rgb * lum_ratio, 0.0, 1.0)
        return bg_rgb * (1.0 - alpha) + lit_design * alpha

    if mode == "screen":
        screened = 1.0 - (1.0 - bg_rgb) * (1.0 - design_rgb)
        return bg_rgb * (1.0 - alpha) + screened * alpha

    # normal (plus gentle ambient highlight preservation for glass screens)
    return bg_rgb * (1.0 - alpha) + design_rgb * alpha


def render_mockup(
    manifest: MockupManifest,
    template_dir: Path,
    logo_svg: str,
    ctx: MockupContext | None = None,
) -> Image.Image:
    """Render all slots of a mockup manifest onto its photographic background."""
    active_ctx = ctx or MockupContext()
    bg_path = template_dir / manifest.background
    if not bg_path.is_file():
        raise FileNotFoundError(f"Mockup background not found: {bg_path}")

    bg_img = Image.open(bg_path).convert("RGB")
    canvas = np.asarray(bg_img, dtype=np.float32) / 255.0

    for slot in manifest.slots:
        design_rgba = render_slot_design(slot, logo_svg, active_ctx)
        canvas = _composite_slot(canvas, slot, design_rgba)

    out_u8 = np.clip(np.round(canvas * 255.0), 0, 255).astype(np.uint8)
    return Image.fromarray(out_u8, mode="RGB")


def render_all_mockups(
    logo_svg: str,
    out_dir: Path,
    ctx: MockupContext | None = None,
    templates_dir: Path | None = None,
    only_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    """Render selected or all mockup templates into out_dir and return metadata records."""
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []
    for tdir, manifest in discover_templates(templates_dir):
        if only_ids is not None and manifest.id not in only_ids:
            continue
        rendered = render_mockup(manifest, tdir, logo_svg, ctx=ctx)
        out_file = out_dir / f"{manifest.id}.jpg"
        rendered.save(out_file, format="JPEG", quality=92)
        records.append(
            {
                "id": manifest.id,
                "title": manifest.title,
                "category": manifest.category,
                "file": out_file.name,
                "path": str(out_file),
            }
        )
    return records
