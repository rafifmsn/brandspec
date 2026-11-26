"""Bounded parameter sweep runner and contact sheet renderer for mark specs."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import io
import itertools
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from pydantic import BaseModel, Field, ValidationError
import resvg_py

from ...inspect import analyze_compiled
from .artifacts import write_mark_artifacts
from .compiler import compile_spec
from .schema import MarkSpec


class SweepAxis(BaseModel):
    path: str
    values: list[Any] = Field(min_length=1)


class SweepSpec(BaseModel):
    axes: list[SweepAxis] = Field(min_length=1, max_length=3)
    max_variants: int = Field(default=24, ge=1, le=64)


@dataclass(frozen=True)
class SweepResult:
    out_dir: Path
    variants_file: Path
    contact_sheet_file: Path
    variants: list[dict[str, Any]]


def _parse_token(token: str) -> Any:
    stripped = token.strip()
    if stripped == "":
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def parse_set_flag(expr: str) -> SweepAxis:
    """Parse a CLI --set path=v1,v2,... expression into a SweepAxis."""
    if "=" not in expr:
        raise ValueError(f"Invalid --set expression '{expr}'. Expected path=v1,v2,...")
    path_str, raw_values = expr.split("=", 1)
    path_str = path_str.strip()
    if not path_str:
        raise ValueError(f"Missing path in --set expression '{expr}'")
    tokens = [tok for tok in raw_values.split(",") if tok.strip() != ""]
    if not tokens:
        raise ValueError(f"No values provided in --set expression '{expr}'")
    return SweepAxis(path=path_str, values=[_parse_token(t) for t in tokens])


def merge_axes(
    sweep_spec: SweepSpec | None,
    set_exprs: list[str],
    max_variants_override: int | None = None,
) -> tuple[list[SweepAxis], int]:
    """Merge optional SweepSpec axes with CLI --set overrides."""
    ordered: dict[str, SweepAxis] = {}
    if sweep_spec is not None:
        for axis in sweep_spec.axes:
            ordered[axis.path] = axis
    for expr in set_exprs:
        axis = parse_set_flag(expr)
        ordered[axis.path] = axis

    axes = list(ordered.values())
    if not axes:
        raise ValueError("Provide at least one --set axis or --sweep manifest.")
    if len(axes) > 3:
        raise ValueError(f"Sweep supports at most 3 axes (got {len(axes)}).")

    max_variants = (
        max_variants_override
        if max_variants_override is not None
        else (sweep_spec.max_variants if sweep_spec is not None else 24)
    )
    if max_variants < 1 or max_variants > 64:
        raise ValueError(f"--max-variants must be between 1 and 64 (got {max_variants}).")
    return axes, max_variants


def _resolve_parent(root: Any, path: str) -> tuple[Any, str | int]:
    parts = path.split(".")
    curr = root
    for idx, part in enumerate(parts[:-1]):
        if isinstance(curr, dict):
            if part not in curr:
                raise ValueError(f"Sweep path '{path}' failed: unknown key '{part}'")
            curr = curr[part]
        elif isinstance(curr, list):
            try:
                list_idx = int(part)
            except ValueError as exc:
                raise ValueError(
                    f"Sweep path '{path}' failed: expected list index at segment '{part}'"
                ) from exc
            if list_idx < 0 or list_idx >= len(curr):
                raise ValueError(
                    f"Sweep path '{path}' failed: index {list_idx} out of range (len={len(curr)})"
                )
            curr = curr[list_idx]
        else:
            prefix = ".".join(parts[:idx])
            raise ValueError(
                f"Sweep path '{path}' failed: '{prefix}' is not a container"
            )

    leaf = parts[-1]
    if isinstance(curr, dict):
        if leaf not in curr:
            raise ValueError(f"Sweep path '{path}' failed: unknown key '{leaf}'")
        return curr, leaf
    if isinstance(curr, list):
        try:
            list_idx = int(leaf)
        except ValueError as exc:
            raise ValueError(
                f"Sweep path '{path}' failed: expected list index at leaf '{leaf}'"
            ) from exc
        if list_idx < 0 or list_idx >= len(curr):
            raise ValueError(
                f"Sweep path '{path}' failed: index {list_idx} out of range (len={len(curr)})"
            )
        return curr, list_idx
    raise ValueError(f"Sweep path '{path}' failed: target parent is not mutable")


def validate_sweep_paths(raw_spec: dict[str, Any], axes: list[SweepAxis]) -> None:
    """Validate that every sweep axis path resolves cleanly inside raw_spec."""
    for axis in axes:
        _resolve_parent(raw_spec, axis.path)


def set_dot_path(raw_spec: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a deep-copied spec dictionary with path updated to value."""
    mutated = copy.deepcopy(raw_spec)
    parent, key = _resolve_parent(mutated, path)
    parent[key] = value
    return mutated


def _render_contact_sheet(
    tiles: list[tuple[dict[str, Any], bytes | None]],
) -> Image.Image:
    cols = min(4, max(1, len(tiles)))
    rows = (len(tiles) + cols - 1) // cols
    tile_w = 240
    tile_h = 286
    pad = 16
    header_h = 40

    width = pad + cols * (tile_w + pad)
    height = header_h + pad + rows * (tile_h + pad)
    sheet = Image.new("RGB", (width, height), (11, 12, 14))
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 13), f"brandspec sweep ({len(tiles)} variants)", fill=(243, 244, 246))

    for idx, (record, svg_bytes) in enumerate(tiles):
        r = idx // cols
        c = idx % cols
        x = pad + c * (tile_w + pad)
        y = header_h + pad + r * (tile_h + pad)
        draw.rectangle(
            [x, y, x + tile_w - 1, y + tile_h - 1],
            fill=(18, 19, 22),
            outline=(38, 40, 46),
        )

        img_box = (x + 12, y + 12, tile_w - 24, tile_w - 24)
        if svg_bytes is not None:
            thumb = Image.open(io.BytesIO(svg_bytes)).convert("RGB")
            sheet.paste(thumb, (img_box[0], img_box[1]))
        else:
            draw.rectangle(
                [img_box[0], img_box[1], img_box[0] + img_box[2], img_box[1] + img_box[3]],
                fill=(24, 26, 31),
                outline=(58, 62, 71),
            )
            draw.text((img_box[0] + 16, img_box[1] + 92), "COMPILE ERROR", fill=(229, 231, 235))

        status = "ERROR" if record.get("error") else ("PASS" if record.get("passed") else "WARN")
        param_summary = ", ".join(f"{k.split('.')[-1]}={v}" for k, v in record["params"].items())
        if len(param_summary) > 30:
            param_summary = param_summary[:27] + "..."
        draw.text((x + 12, y + tile_w - 4), f"{record['id']}  {status}", fill=(243, 244, 246))
        draw.text((x + 12, y + tile_w + 14), param_summary, fill=(156, 163, 175))

    return sheet


def run_sweep(
    raw_spec: dict[str, Any],
    axes: list[SweepAxis],
    out_dir: Path,
    max_variants: int = 24,
    only_passed: bool = False,
) -> SweepResult:
    """Compile a bounded Cartesian parameter sweep into studio-compatible directories."""
    base_spec = MarkSpec.model_validate(raw_spec)
    resolved_base = base_spec.model_dump(mode="python")
    validate_sweep_paths(resolved_base, axes)

    combos = list(itertools.product(*(axis.values for axis in axes)))
    if len(combos) > max_variants:
        raise ValueError(
            f"Sweep produces {len(combos)} variants, exceeding max_variants={max_variants}."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    variants: list[dict[str, Any]] = []
    tiles: list[tuple[dict[str, Any], bytes | None]] = []
    emitted_idx = 0

    for _raw_idx, combo in enumerate(combos, start=1):
        mutated = copy.deepcopy(resolved_base)
        params: dict[str, Any] = {}
        for axis, val in zip(axes, combo):
            mutated = set_dot_path(mutated, axis.path, val)
            params[axis.path] = val

        try:
            variant_spec = MarkSpec.model_validate(mutated)
            compiled = compile_spec(variant_spec)
            metrics = analyze_compiled(compiled)
        except (ValidationError, ValueError) as exc:
            if only_passed:
                continue
            emitted_idx += 1
            vid = f"{emitted_idx:02d}"
            record = {
                "id": vid,
                "params": params,
                "passed": False,
                "warnings": [str(exc)],
                "ink_ratio": 0.0,
                "ink_ratio_24px": 0.0,
                "error": str(exc),
            }
            variants.append(record)
            tiles.append((record, None))
            continue

        if only_passed and not metrics.passed:
            continue

        emitted_idx += 1
        vid = f"{emitted_idx:02d}"
        write_mark_artifacts(variant_spec, compiled, metrics, out_dir / vid)
        record = {
            "id": vid,
            "params": params,
            "passed": metrics.passed,
            "warnings": metrics.warnings,
            "ink_ratio": metrics.ink_ratio,
            "ink_ratio_24px": metrics.ink_ratio_24px,
        }
        variants.append(record)
        png_bytes = resvg_py.svg_to_bytes(
            svg_string=compiled.svg_markup,
            width=216,
            height=216,
            background="#ffffff",
        )
        tiles.append((record, png_bytes))

    variants_file = out_dir / "variants.json"
    variants_file.write_text(json.dumps(variants, indent=2) + "\n", encoding="utf-8")

    contact_sheet_file = out_dir / "contact_sheet.png"
    sheet_img = _render_contact_sheet(tiles)
    sheet_img.save(contact_sheet_file, format="PNG")

    return SweepResult(
        out_dir=out_dir,
        variants_file=variants_file,
        contact_sheet_file=contact_sheet_file,
        variants=variants,
    )
