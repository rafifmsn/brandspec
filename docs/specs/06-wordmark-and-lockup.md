# Leaf Spec 06: Wordmark and Lockup Engines (`#5` Phase 2)

## Problem Statement

Pairing a crisp geometric mark with raw `<text>` elements breaks cross-platform consistency and prevents custom glyph geometry edits.
`engines/wordmark` and `engines/lockup` outline real `.ttf` and `.otf` fonts into pure vector paths in Python, enabling ink traps, stencil cuts, and optical pairing.

## Technical Contract

1. Add `fontTools>=4.50` to `pyproject.toml` dependencies (pure Python, zero Node.js runtime).
2. `src/brandspec/engines/wordmark/`:
   - `schema.py` (`WordmarkSpec`, `schemaVersion: 1`):
     - `text: str`, `font_path: str`, `case: Literal["as_is", "upper", "lower"] = "as_is"`
     - `tracking_em: float = 0.0`, `kerning_pairs: dict[str, float] = {}`
     - `ink_trap: InkTrapSpec | None = None` (`depth_u`, `width_u`, `angle_threshold_deg`)
     - `stencil_cuts: list[ShapeSpec] = []`
   - `compiler.py`: Reads glyph contours via `fontTools.ttLib.TTFont` and a custom `SkiaPath` recording pen into `pathops.Path`, applies kerning/tracking, carves ink traps or stencil cuts, and returns `CompiledWordmark`.
3. `src/brandspec/engines/lockup/`:
   - `schema.py` (`LockupSpec`, `schemaVersion: 1`): `mark_spec: str`, `wordmark_spec: str`, `layout: Literal["horizontal", "stacked", "badge"] = "horizontal"`, `gap_u: float = 1.0`, `mark_scale: float = 1.0`, `align: Literal["center", "baseline"] = "center"`, `clearspace_u: float = 1.0`.
   - `compiler.py`: Scales and aligns compiled `mark` and `wordmark` paths, emits `lockup.svg` and `lockup-clearspace.svg` with dashed `1u`/`2u` exclusion guides, and integrates with `inspect` and `studio`.
4. CLI commands in `src/brandspec/cli.py`:
   ```text
   brandspec wordmark build <wordmark.spec.json> [--out-dir <dir>]
   brandspec lockup build <lockup.spec.json> [--out-dir <dir>]
   ```

## Feature Checklist

- [ ] Add `fontTools>=4.50` to `pyproject.toml` and build the glyph-to-`pathops.Path` pen converter under `src/brandspec/engines/wordmark/`.
- [ ] Implement deterministic tracking, per-pair kerning overrides, ink-trap notches, and stencil cuts.
- [ ] Implement `engines/lockup` supporting `horizontal`, `stacked`, and `badge` compositions with `1u`/`2u` clearspace guides.
- [ ] Expose `brandspec wordmark build` and `brandspec lockup build` CLI subcommands and route outputs to `studio` review.

## Required Test Coverage

File: `tests/test_wordmark_lockup.py`
- `test_wordmark_outlines_glyphs_without_text_elements`: Compile a bundled fixture `.ttf` wordmark and assert `<text` is absent while `<path` output is deterministic.
- `test_lockup_respects_clearspace_and_layout_bounds`: Build `horizontal` and `stacked` lockups from a sample mark and wordmark, asserting non-overlapping bounding boxes separated by exact `gap_u`.

## Edge Cases

- Missing glyph in the supplied font file or unsupported variable-font glyph table: Raise explicit `ValueError` naming the character and font path.
- Overlapping glyph contours under tight negative tracking or italic slant: Run `pathops.simplify(..., fix_winding=True)` so overlapping strokes merge cleanly without winding holes.
