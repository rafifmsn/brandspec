# Leaf Spec 07: Icons and Pattern Engines (`#5` Phase 3)

## Problem Statement

Once a brand ships a verified mark, color tokens, and wordmark lockup, product surfaces need matched UI pictograms and seamless textures that inherit the exact geometric grammar of the mark.

## Technical Contract

1. `src/brandspec/engines/icons/`:
   - `schema.py` (`IconSetSpec`, `schemaVersion: 1`):
     - `inherits_mark: str | None = None` (optional path to `MarkSpec` to pull default `unit`, `corner_radius`, `cap`, and `join`)
     - `viewbox_size: int = 24`, `stroke_width: float = 2.0`, `corner_radius: float = 0.0`
     - `cap: Literal["butt", "round", "square"] = "butt"`, `join: Literal["miter", "round", "bevel"] = "miter"`
     - `icons: list[IconItemSpec]` (`id`, `layers: list[LayerSpec]`)
   - `compiler.py`: Compiles each icon onto a crisp integer `24x24` grid via `src/brandspec/core/paths.py`, runs `analyze_compiled`, and generates per-icon SVGs plus an `icons-sheet.png` contact grid.
2. `src/brandspec/engines/pattern/`:
   - `schema.py` (`PatternSpec`, `schemaVersion: 1`): `tile_width: float`, `tile_height: float`, `unit: float = 40.0`, `grid: GridSpec`, `layers: list[LayerSpec]` reusing `line_screen`, `halftone_grid`, and `grid_path`.
   - `compiler.py`: Replicates shapes across all 3x3 periodic offsets (`dx in {-W, 0, +W}`, `dy in {-H, 0, +H}`) before intersecting with `[0, W] x [0, H]`, emitting `tile.svg` and an SVG `<pattern>` wrapper.
3. CLI commands in `src/brandspec/cli.py`:
   ```text
   brandspec icons build <icons.spec.json> [--out-dir <dir>]
   brandspec pattern build <pattern.spec.json> [--out-dir <dir>]
   ```

## Feature Checklist

- [ ] Implement `IconSetSpec` inheriting mark stroke, corner radius, cap, and join defaults and outputting `24x24` SVGs plus contact sheet.
- [ ] Implement `PatternSpec` with 3x3 wrap-around tiling compilation and seamless `<pattern>` SVG export.
- [ ] Reuse `src/brandspec/inspect/sheet.py` checks to flag any 24px icon collapse or tiny islands.
- [ ] Wire `brandspec icons build` and `brandspec pattern build` CLI subcommands.

## Required Test Coverage

File: `tests/test_icons_pattern.py`
- `test_icon_set_inherits_mark_corner_and_stroke_defaults`: Compile two icons inheriting `MarkSpec` geometry defaults and verify `24x24` viewBox dimensions and clean metrics.
- `test_pattern_tile_wraps_seamlessly`: Render a 2x2 tiled `PatternSpec` SVG via `resvg-py` and assert pixel continuity across vertical and horizontal tile boundaries.

## Edge Cases

- `PatternSpec` stroke or diagonal motif crossing tile corners: 3x3 periodic replication before clipping guarantees identical entry and exit geometry on opposite edges.
- Non-integer stroke weights on `24x24` icons causing 16px anti-aliasing blur: Warn via `analyze_compiled` when `stroke_width` produces fractional pixel alignment or weak `ink_ratio_24px`.
