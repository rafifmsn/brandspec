# Leaf Spec 04: Bounded Parameter Sweep (`#4`)

## Problem Statement

Tuning modernist proportions (`halo`, `twist_deg`, `line_screen.count`, `corner_radius`) currently requires manual edit-build loops one variant at a time.
Agents need a single bounded command to compile a deterministic parameter matrix, filter quality failures, and hand the gallery straight to `brandspec review`.

## Technical Contract

1. CLI command in `src/brandspec/cli.py`:
   ```text
   brandspec sweep <spec.json> [--set path=v1,v2,...]... [--sweep <sweep.json>] [--out-dir <dir>] [--max-variants 24] [--only-passed] [--review]
   ```
2. Path syntax for `--set`:
   - Dot-separated JSON path supporting dict keys and integer list indices, for example `layers.1.halo=0.3,0.4,0.5` or `post.invert=false,true`.
   - Values parse via JSON decoding per token with fallback to raw string so booleans, floats, ints, and enums resolve deterministically.
3. Optional external `sweep.json` schema (`SweepSpec` in `src/brandspec/engines/mark/sweep.py`):
   ```python
   class SweepAxis(BaseModel):
       path: str
       values: list[Any] = Field(min_length=1)

   class SweepSpec(BaseModel):
       axes: list[SweepAxis] = Field(min_length=1, max_length=3)
       max_variants: int = Field(default=24, ge=1, le=64)
   ```
   Keep `MarkSpec` strictly single-mark with zero embedded sweep fields.
4. Output structure inside `--out-dir` (default `<spec_dir>/out/<spec_stem>-sweep`):
   - `01/`, `02/`, ... matching the exact `studio` candidate folder contract (`spec.json`, `logo.svg`, `sheet.png`, `metrics.json`, `meta.json`).
   - `variants.json`: Ordered array of variant records (`id`, `params`, `passed`, `warnings`, `ink_ratio`, `ink_ratio_24px`).
   - `contact_sheet.png`: Numbered dark-header grid PNG (`4` columns max) labeled with variant ID, varied parameter summary, and pass/warn tag.

## Feature Checklist

- [ ] Implement `src/brandspec/engines/mark/sweep.py` with dot-path mutation, Cartesian product generation, and `--max-variants` guard.
- [ ] Render numbered `contact_sheet.png` and machine-readable `variants.json`.
- [ ] Emit studio-compatible candidate subdirectories (`01/`, `02/`, ...) with `meta.json`.
- [ ] Wire `brandspec sweep` in `src/brandspec/cli.py`, including `--only-passed` and `--review` handoff into `brandspec review --wait`.

## Required Test Coverage

File: `tests/test_sweep.py`
- `test_sweep_cartesian_outputs_studio_compatible_dirs`: Sweep 2 axes (`2x2`) on an archetype spec and assert `01/`..`04/`, `variants.json`, and `contact_sheet.png` exist.
- `test_sweep_enforces_max_variants_bound`: Pass combinations exceeding `--max-variants` and assert clean exit code `1` before compiling.
- `test_sweep_invalid_path_fails_fast`: Pass nonexistent `layers.99.halo=0.5` and assert descriptive error exit code `1`.

## Edge Cases

- Individual variant fails `compile_spec` (for example empty boolean result at extreme `halo`): Record `error` in `variants.json` and mark failed tile on `contact_sheet.png` instead of aborting valid variants.
- Both `--set` and `--sweep` supplied: Either merge with `--set` overriding matching axis paths or reject cleanly; prefer deterministic `--set` override.
