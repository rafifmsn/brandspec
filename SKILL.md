---
name: logo-modernism
description: Design and compile deterministic Logo Modernism monochrome logomarks from a structured geometric DSL (`spec.json`) using `logo-mod`, then visually audit the generated inspection sheet and metrics.
---

# Logo Modernism Design & Compilation Skill

Use this skill whenever asked to design, iterate on, or generate a minimalist geometric, optical-effect, or modular monogram logomark in the style of Jens Müller's *Logo Modernism*.

Never write raw SVG `<path d="...">` coordinates by hand. Always express the construction in a `spec.json` recipe and compile it deterministically with `logo-mod`.

## Available CLI Commands

Run `logo-mod` directly (or `uv run logo-mod` inside the `logo-mod` project):

```bash
logo-mod archetypes
logo-mod init <archetype> --out <path/to/spec.json>
logo-mod build <path/to/spec.json> --out-dir <path/to/out>
logo-mod check <path/to/spec.json>
```

Each `build` outputs four deterministic artifacts:
- `logo.svg`: Clean flattened single-color vector path on a `1000x1000` viewBox.
- `sheet.png`: 4-panel visual audit image (1. Construction grid overlay, 2. Positive 400px, 3. Inverted 400px, 4. 96px/48px/24px scale strip).
- `metrics.json`: Automated checks (`ink_ratio`, `ink_ratio_24px`, `bbox_aspect`, `island_count`, `tiny_island_count`, `optical_drift_pct`, `warnings`, `passed`).
- `spec.json`: Locked specification for exact reproduction.

## Modernist Construction Rules

1. **One unit governs everything**: Express stroke widths, gaps, radii, and clearances as clean multiples of the grid unit (`1.0`, `0.5`, `0.4`).
2. **Use `halo` and `halo_targets` for interlocking gaps**: Instead of manually calculating negative cutout bars where ribbons cross, put the crossing ribbon in its own `unite` layer with `"halo": 0.35` to `"halo": 0.5`. When adding an overpass that re-crosses an earlier band without cutting itself, set `"halo_targets": ["<crossing-layer-id>"]` so `halo` carves only the target layer and requires zero seam-healing patches.
3. **Use `grid_path` with `corner_radius` for continuous forms**: Prefer a single `grid_path` polyline with `corner_radius` over separate bars and arcs so tangents and stroke weights remain seamless.
4. **Use `clip_to` for optical effects**: Combine `line_screen` or `halftone_grid` with `clip_to: [circle | polygon | rect]` to produce kinetic *Logo Modernism* marks cleanly.
5. **Preserve 24px legibility**: Keep minimum stripe widths and `halo` gaps large enough (`>= 0.3` unit) so negative space does not collapse at 24px.

## Schema Quick Reference (`schemaVersion: 1`)

- **Grids (`grid.type`)**, origin `(0, 0)` is centered:
  - `"square"`: `[x, y]` in grid units (`+x` right, `+y` down).
  - `"isometric"`: `[q, r]` axial 30-degree coordinates (`(1,0)` down-right 30 deg, `(0,1)` straight down, `(1,-1)` up-right 30 deg).
  - `"polar"`: `[ring, angle_deg]` (`0` deg = 12 o'clock, increasing clockwise).
- **Shapes (`type`)**:
  - `grid_path`: `points`, `closed`, `width` (`0` = filled polygon), `corner_radius`, `cap`, `join`.
  - `arc_band`: `center`, `radius`, `start_deg`, `end_deg`, `width`, `fill_sector`, `cap`.
  - `circle`: `center`, `radius`.
  - `ring`: `center`, `outer_radius`, `inner_radius`.
  - `rect`: `center`, `width`, `height`, `corner_radius`, `angle_deg`.
  - `polygon`: `center`, `sides`, `radius`, `angle_deg`, `corner_radius`.
  - `line_screen`: `center`, `angle_deg`, `count`, `pitch`, `length`, `min_width`, `max_width`, `profile` (`constant`, `linear`, `center_bulge`, `center_pinch`, `sine`, `exponential`), `invert_profile`.
  - `radial_blades`: `center`, `count`, `inner_radius`, `outer_radius`, `angle_deg`, `twist_deg`, `inner_width_deg`, `outer_width_deg`, `curve_bias`.
  - `halftone_grid`: `center`, `cols`, `rows`, `pitch`, `shape` (`circle`, `square`, `diamond`), `min_size`, `max_size`, `field` (`radial_decay`, `radial_grow`, `linear_x`, `linear_y`, `diagonal`, `sine_ripple`).
- **Symmetry (`symmetry.type`)**: `"none"`, `"mirror_x"`, `"mirror_y"`, `"mirror_xy"`, `"rotate"` (`count`, `step_deg`, `scale_step`), `"glide_x"`.

## Agent Workflow (3 Steps)

1. **Map concept to archetype**: Choose 2 to 3 distinct structural directions (e.g., an interlocking ribbon, a radial vortex, or a modulated line screen) that fit the brand metaphor. Run `logo-mod init` or author `spec.json` drafts.
2. **Build and inspect**: Run `logo-mod build <spec.json> --out-dir <dir>` and read both `metrics.json` and `sheet.png` (using your file/image reader).
3. **Refine once**: Check the construction grid panel for misaligned tangents, check `metrics.json` for `warnings` (ink ratio target `0.22` to `0.55`, zero tiny islands), and check Panel 4 to ensure the silhouette reads cleanly at 24px. Adjust parameters in `spec.json`, rebuild, and deliver the final `logo.svg` + `spec.json`.
