"""Tests for skill bundling, uvx fallback docs, and install-skill CLI."""

from __future__ import annotations

from pathlib import Path

from brandspec.cli import main, resolve_skill_target

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILL = REPO_ROOT / "skills" / "brandspec" / "SKILL.md"


def test_install_skill_writes_to_custom_target(tmp_path: Path) -> None:
    target_dir = tmp_path / "custom-skills" / "brandspec"
    rc = main(["install-skill", "--target", str(target_dir)])
    assert rc == 0

    installed = target_dir / "SKILL.md"
    assert installed.is_file()
    assert installed.read_text(encoding="utf-8") == CANONICAL_SKILL.read_text(encoding="utf-8")


def test_install_skill_refuses_overwrite_without_force(tmp_path: Path) -> None:
    target_dir = tmp_path / "host-skill"
    assert main(["install-skill", "--target", str(target_dir)]) == 0

    installed = target_dir / "SKILL.md"
    installed.write_text("custom local edits", encoding="utf-8")

    rc_no_force = main(["install-skill", "--target", str(target_dir)])
    assert rc_no_force == 1
    assert installed.read_text(encoding="utf-8") == "custom local edits"

    rc_force = main(["install-skill", "--target", str(target_dir), "--force"])
    assert rc_force == 0
    assert installed.read_text(encoding="utf-8") == CANONICAL_SKILL.read_text(encoding="utf-8")


def test_install_skill_resolves_named_presets(monkeypatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_cwd = tmp_path / "project"
    fake_home.mkdir()
    fake_cwd.mkdir()

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.chdir(fake_cwd)

    expected = {
        "agents": fake_home / ".agents" / "skills" / "brandspec" / "SKILL.md",
        "project": fake_cwd / ".agents" / "skills" / "brandspec" / "SKILL.md",
        "claude": fake_home / ".claude" / "skills" / "brandspec" / "SKILL.md",
        "cursor": fake_home / ".cursor" / "skills" / "brandspec" / "SKILL.md",
        "codex": fake_home / ".codex" / "skills" / "brandspec" / "SKILL.md",
        "antigravity": fake_home / ".gemini" / "skills" / "brandspec" / "SKILL.md",
    }
    for preset, expected_path in expected.items():
        assert resolve_skill_target(preset) == expected_path

    custom_md = tmp_path / "direct" / "CUSTOM.md"
    assert resolve_skill_target(str(custom_md)) == custom_md

    assert main(["install-skill", "--target", "antigravity"]) == 0
    assert expected["antigravity"].read_text(encoding="utf-8") == CANONICAL_SKILL.read_text(
        encoding="utf-8"
    )
