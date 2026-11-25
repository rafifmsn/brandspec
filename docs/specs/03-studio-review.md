# Leaf Spec 03: Studio Localhost Review Server (`#3`)

## Problem Statement

Reviewing compiled `sheet.png` images forces users to translate spatial tweaks into vague chat prose.
`brandspec` already knows grid geometry, `CompiledMark.affine`, and unit scale, enabling an exact click-to-grid review console.

## Technical Contract

1. Package layout under `src/brandspec/studio/`:
   - `server.py`: Python stdlib `ThreadingHTTPServer` binding `127.0.0.1` (`--port 0` picks an ephemeral open port).
   - `assets/index.html`, `assets/studio.css`, `assets/studio.js`: Zero-build vanilla frontend bundled in package data.
2. CLI commands in `src/brandspec/cli.py`:
   ```text
   brandspec review --dir <dir> [--port 0] [--open] [--wait] [--timeout 900]
   brandspec serve --dir <dir> [--port 8420] [--open]
   ```
3. Compiler metadata output: Extend `brandspec build` (and `sweep`) to write `meta.json` alongside `logo.svg`, containing `name`, `concept`, `unit`, `grid`, `canvas_size`, and `affine: [sx, 0, 0, sy, tx, ty]`.
4. HTTP API routes:
   - `GET /api/session`: Returns discovered candidates (`id`, `metrics`, `meta`, `spec`, available image/SVG URLs), current round, and any prior `review.json` history.
   - `GET /api/candidates/<id>/<file>`: Serves `logo.svg`, `sheet.png`, or overlay SVG safely confined inside `--dir`.
   - `POST /api/review`: Validates payload, writes `<dir>/review.json`, archives prior round if present, and signals `--wait` event.
5. Inverse grid coordinate math in `studio.js`:
   - Convert canvas pixel `(px, py)` to design XY via `(px * canvas_size / rect.width - tx) / sx`, then invert `square`, `isometric` (`a = x / (unit * cos30)`, `b = y / unit - 0.5 * a`), or `polar` (`r = hypot(x, y) / unit`, `deg = (atan2(x, -y) * 180 / pi + 360) % 360`).

## UI Design Contract

Follow the exact monochrome tokens and anti-slop rules in [decisions.md](../decisions.md).
Single sans-serif font stack only with `font-variant-numeric: tabular-nums`; zero monospace font usage.
Provide a clean candidate grid and focused two-column stage: interactive SVG canvas with `Positive`, `Inverted`, `Grid`, and `24/48/96px` toggles plus optional surface hex preview on the left; numbered pin list and `Approve` / `Revise` / `Reject` controls on the right.

## Feature Checklist

- [ ] Emit `meta.json` during `brandspec build` with exact `affine`, `unit`, and `grid`.
- [ ] Implement `src/brandspec/studio/server.py` with path-traversal-safe static and candidate serving.
- [ ] Build zero-build monochrome frontend (`index.html`, `studio.css`, `studio.js`) with inverse-affine pin comments.
- [ ] Wire `brandspec review` (`--wait`, `--timeout`, `--open`) and `brandspec serve` in `src/brandspec/cli.py`.
- [ ] Support multi-round reviews by archiving prior rounds into `review.round-<n>.json` and returning round history in `GET /api/session`.

## Required Test Coverage

File: `tests/test_studio.py`
- `test_session_discovers_single_and_multi_candidate_dirs`: Verify both single `build` output and multi-folder `sweep` directories load cleanly.
- `test_post_review_writes_json_and_unblocks_wait`: Start server on ephemeral port, `POST /api/review`, and assert `review.json` schema, round increment, and `--wait` exit code `0`.
- `test_path_traversal_rejected`: Request `../` candidate paths and assert `403` or `404`.
- `test_inverse_grid_math_roundtrip`: Verify `square`, `isometric`, and `polar` forward and inverse conversions match within `1e-3`.

## Edge Cases

- `--wait` timeout expires (`--timeout > 0`): Shut down server cleanly, do not overwrite existing `review.json`, and exit with code `3`.
- Directory contains single-candidate `logo.svg` directly instead of subdirectories: Wrap automatically as candidate `"default"`.
- Port already in use: Surface clear error message with exit code `1`.
