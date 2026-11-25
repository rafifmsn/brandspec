# Leaf Spec 02: Skill Distribution and `uvx` Fallback (`#2`)

## Problem Statement

`npx skills add rafifmsn/brandspec` fetches `skills/brandspec/SKILL.md` without installing the `brandspec` Python CLI.
Because `SKILL.md` currently demonstrates bare `brandspec` invocations, clean environments fail with `command not found`, and Python-only `uv` users lack a native installer.

## Technical Contract

1. Keep `skills/brandspec/SKILL.md` as the single canonical file in git.
2. Bundle it into the wheel in `pyproject.toml`:
   ```toml
   [tool.hatch.build.targets.wheel.force-include]
   "skills/brandspec/SKILL.md" = "brandspec/skills/SKILL.md"
   ```
3. Add `install-skill` subcommand in `src/brandspec/cli.py`:
   ```text
   brandspec install-skill [--target <preset-or-path>] [--force]
   ```
   - Presets:
     - `agents` (default): `~/.agents/skills/brandspec/SKILL.md`
     - `project`: `./.agents/skills/brandspec/SKILL.md`
     - `claude`: `~/.claude/skills/brandspec/SKILL.md`
     - `cursor`: `~/.cursor/skills/brandspec/SKILL.md`
     - `codex`: `~/.codex/skills/brandspec/SKILL.md`
     - `antigravity`: `~/.gemini/skills/brandspec/SKILL.md`
     - Any path containing `/` or `~`: resolved directly as `<path>/SKILL.md` (or exact file path if ending in `.md`).
   - Reads bundled skill via `importlib.resources.files("brandspec").joinpath("skills/SKILL.md")`, falling back cleanly to repo-root `skills/brandspec/SKILL.md` during editable dev if needed.

## Feature Checklist

- [ ] Update `skills/brandspec/SKILL.md` command examples and intro to instruct agents: use `brandspec` if on `PATH`, otherwise run `uvx brandspec ...` (or `uv run brandspec ...` inside a repo clone).
- [ ] Add `force-include` mapping in `pyproject.toml` and verify `uv build` wheel includes `brandspec/skills/SKILL.md`.
- [ ] Implement `cmd_install_skill` and `--target` / `--force` parser flags in `src/brandspec/cli.py`.
- [ ] Update `README.md` CLI commands table to document `brandspec install-skill`.

## Required Test Coverage

File: `tests/test_cli_skill.py`
- `test_install_skill_writes_to_custom_target`: Run `main(["install-skill", "--target", str(tmp_dir)])` and assert `SKILL.md` matches canonical `skills/brandspec/SKILL.md`.
- `test_install_skill_refuses_overwrite_without_force`: Assert second call without `--force` exits non-zero and preserves existing content, while `--force` overwrites cleanly.
- `test_install_skill_resolves_named_presets`: Verify preset path resolution via `monkeypatch` on `Path.home()` without touching real home directories.

## Edge Cases

- Destination file already exists and `--force` is omitted: Exit with code `1` and clear message instead of silently overwriting user customizations.
- Target parent directory does not exist: Create intermediate directories with `mkdir(parents=True, exist_ok=True)`.
- Built wheel environment without repo checkout: `importlib.resources` must succeed independently of `Path(__file__).parents`.
