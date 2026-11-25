# Leaf Spec 01: Configurable Halo Join (`#1`)

## Problem Statement

`dilate_path` in `src/brandspec/core/paths.py` hardcodes `pathops.LineJoin.ROUND_JOIN` and `pathops.LineCap.ROUND_CAP`.
When carving negative space around sharp-angled or isometric `grid_path` layers configured with `join: "miter"`, rounded dilation carves curved shoulder notches into adjacent straight walls.

## Technical Contract

1. Extend `LayerSpec` in `src/brandspec/engines/mark/schema.py`:
   - `halo_join: Literal["round", "miter", "bevel"] = "round"`
   - `halo_cap: Literal["round", "butt", "square"] = "round"`
2. Update `dilate_path` in `src/brandspec/core/paths.py`:
   ```python
   def dilate_path(
       path: pathops.Path,
       halo_radius: float,
       join: Literal["round", "miter", "bevel"] = "round",
       cap: Literal["round", "butt", "square"] = "round",
   ) -> pathops.Path:
   ```
3. Map string literals to `pathops.LineJoin` (`ROUND_JOIN`, `MITER_JOIN`, `BEVEL_JOIN`) and `pathops.LineCap` (`ROUND_CAP`, `BUTT_CAP`, `SQUARE_CAP`) using lookup tables with miter limit `4.0`.
4. Pass `layer.halo_join` and `layer.halo_cap` from `compile_spec` in `src/brandspec/engines/mark/compiler.py` in both `op == "unite"` and `op == "subtract"` halo branches.

## Feature Checklist

- [ ] Add `halo_join` and `halo_cap` fields to `LayerSpec` defaulting to `"round"` for backwards compatibility.
- [ ] Parameterize `dilate_path` with `join` and `cap` mappings in `src/brandspec/core/paths.py`.
- [ ] Pass `layer.halo_join` and `layer.halo_cap` into `dilate_path` inside `compile_spec`.
- [ ] Update `skills/brandspec/SKILL.md` to advise `"halo_join": "miter"` on sharp angular or isometric `grid_path` weaves.
- [ ] Add regression tests covering mitered isometric/square crossings.

## Required Test Coverage

File: `tests/test_compiler.py`
- `test_halo_join_miter_preserves_sharp_channels`: Build an L-shaped or 60-degree crossing `grid_path` spec with `join="miter"`, `halo=0.4`, and `halo_join="miter"`, then assert `compile_spec` passes metrics and yields distinct contours from `halo_join="round"`.
- `test_halo_join_defaults_to_round`: Validate that specs omitting `halo_join` produce identical SVG output to explicit `halo_join="round"`.

## Edge Cases

- Acute corners under `"miter"` where miter extension exceeds `4.0 * stroke_width`: Skia's `miter_limit=4.0` automatically falls back to bevel, preventing spikes.
- `halo <= 1e-6`: Return `path` early without invoking stroke dilation regardless of `halo_join` or `halo_cap`.
- `op == "subtract"` with `halo > 0`: Ensure `halo_join` and `halo_cap` apply symmetrically to dilated subtraction masks.
