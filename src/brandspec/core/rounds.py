"""Shared round candidate snapshot helpers for multi-round studio reviews."""

from __future__ import annotations

import json
from pathlib import Path
import re

ALLOWED_CANDIDATE_FILES = {
    "logo.svg",
    "sheet.png",
    "overlay.svg",
    "metrics.json",
    "meta.json",
    "spec.json",
}
ROUND_DIR_RE = re.compile(r"^round-(\d+)$")


def candidate_dir_map(root_dir: Path) -> dict[str, Path]:
    """Return mapping of candidate ID to directory inside root_dir."""
    root = root_dir.resolve()
    if not root.is_dir():
        return {}
    if (root / "logo.svg").is_file():
        return {"default": root}
    mapping: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.is_dir() and child.name != "rounds" and (child / "logo.svg").is_file():
            mapping[child.name] = child
    return mapping


def snapshot_round_candidates(root_dir: Path, round_num: int) -> None:
    """Snapshot current candidate artifacts into rounds/round-<n>/ for branching."""
    cdirs = candidate_dir_map(root_dir)
    if not cdirs:
        return
    round_dir = root_dir / "rounds" / f"round-{round_num}"
    for cid, src_dir in cdirs.items():
        dst_dir = round_dir / cid
        dst_dir.mkdir(parents=True, exist_ok=True)
        for fname in ALLOWED_CANDIDATE_FILES:
            src_file = src_dir / fname
            if src_file.is_file():
                (dst_dir / fname).write_bytes(src_file.read_bytes())


def snapshot_prior_round_before_build(out_dir: Path) -> None:
    """Preserve prior reviewed candidates before overwriting out_dir with a new build."""
    review_path = out_dir / "review.json"
    if not review_path.is_file():
        return
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(review, dict) or "round" not in review:
        return
    round_num = int(review["round"])
    round_dir = out_dir / "rounds" / f"round-{round_num}"
    if not round_dir.exists():
        snapshot_round_candidates(out_dir, round_num)
