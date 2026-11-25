# Leaf Spec 05: Tokens, Palette Extraction, and Export Kit (`#5` Phase 1)

## Problem Statement

Once a monochrome mark passes review, users need deterministic color tokens, verified contrast pairs, production icon bundles, and realistic previews.
Following our agent-first philosophy, Python handles color quantization, WCAG/APCA contrast checks, and asset export while `studio` renders lightweight HTML/CSS mockup previews.

## Technical Contract

1. `src/brandspec/engines/tokens/`:
   - `schema.py` (`TokensSpec`, `schemaVersion: 1`): Monochrome neutral scale (`bg_canvas`, `bg_surface`, `border`, `text_primary`, `text_secondary`), `mark_light`, `mark_dark`, and optional `accent` hex colors plus semantic surface pairs (`light`, `dark`, `inverted`, `brand`).
   - `extract.py`: Pure `Pillow` + `numpy` quantized palette extractor for reference images:
     ```bash
     brandspec palette extract <image_path> [--colors 6] [--out tokens.spec.json]
     ```
   - `contrast.py`: Deterministic WCAG 2.1 ratio and APCA Lc contrast check across every declared foreground/background pair, failing `--strict` if primary pairs miss AA (`4.5:1` text, `3.0:1` UI/mark).
2. `src/brandspec/engines/kit/`:
   - `schema.py` (`KitSpec`, `schemaVersion: 1`): References `mark` SVG/spec and optional `tokens.spec.json`, plus `brand_name`, `tagline`, `og_size` (`1200x630`), and `pwa_padding`.
   - `exporter.py`: Outputs `logo-dark.svg`, `logo-light.svg`, `logo-mono.svg`, multi-resolution `favicon.ico` (`16, 32, 48`), `apple-touch-icon.png` (`180x180`), `icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `og-card.png`, and `tokens.css`.
   - CLI: `brandspec tokens check <tokens.spec.json>` and `brandspec kit build <kit.spec.json> --out-dir <dir>`.
3. `studio` Mockup Tab Extension:
   - When `tokens.spec.json` or `kit` artifacts exist in `--dir`, `studio` exposes a `Mockups` tab showing live HTML/CSS navbar, favicon tab, app-icon grid, and OG card previews in the browser with zero Node.js server dependency.

## Feature Checklist

- [ ] Implement `TokensSpec` schema, WCAG/APCA contrast auditor, and `brandspec palette extract` helper.
- [ ] Implement `KitSpec` and deterministic multi-size icon, SVG variant, CSS variable, and OG card exporter using `resvg-py` and `Pillow`.
- [ ] Support optional `brand.json` root manifest referencing `mark`, `tokens`, and `kit` files.
- [ ] Add `Mockups` preview tab in `studio/` when token/kit artifacts are present.

## Required Test Coverage

File: `tests/test_tokens_kit.py`
- `test_contrast_audit_flags_low_contrast_pair`: Verify low-contrast foreground/background pair fails `brandspec tokens check`.
- `test_palette_extract_returns_deterministic_hex_tokens`: Extract palette from a synthetic fixture PNG and assert deterministic sorted hex output.
- `test_kit_export_generates_valid_ico_pwa_and_svg_variants`: Build kit from a compiled sample mark and verify valid `favicon.ico`, PNG dimensions, and `tokens.css`.

## Edge Cases

- Tiny or low-contrast mark inside maskable PWA safe zone: Enforce `>= 20%` safe-zone padding on `icon-maskable-512.png` so OS circular masks never clip geometry.
- Grayscale-only reference image during `palette extract`: Return clean neutral ramp without division-by-zero in chroma sorting.
