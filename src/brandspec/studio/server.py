"""Zero-build stdlib HTTP server for localhost brand review and pin-comment handoff."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
import mimetypes
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import unquote, urlparse

from ..core.grid import GridSpec, grid_overlay_svg
from ..core.paths import render_svg_doc

ALLOWED_CANDIDATE_FILES = {
    "logo.svg",
    "sheet.png",
    "overlay.svg",
    "metrics.json",
    "meta.json",
    "spec.json",
}
ALLOWED_KIT_FILES = {
    "tokens.spec.json",
    "tokens.css",
    "logo-dark.svg",
    "logo-light.svg",
    "logo-mono.svg",
    "favicon.ico",
    "apple-touch-icon.png",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
    "og-card.png",
}
VALID_STATUSES = {"approve", "revise", "reject"}
ROUND_RE = re.compile(r"^review\.round-(\d+)\.json$")


def _load_asset(filename: str) -> tuple[bytes, str]:
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise FileNotFoundError(filename)
    pkg_asset = resources.files("brandspec").joinpath(f"studio/assets/{safe_name}")
    try:
        data = pkg_asset.read_bytes()
    except (FileNotFoundError, OSError):
        local_asset = Path(__file__).resolve().parent / "assets" / safe_name
        if not local_asset.is_file():
            raise FileNotFoundError(filename)
        data = local_asset.read_bytes()
    mime, _ = mimetypes.guess_type(safe_name)
    if safe_name.endswith(".js"):
        mime = "application/javascript; charset=utf-8"
    elif safe_name.endswith(".css"):
        mime = "text/css; charset=utf-8"
    elif safe_name.endswith(".html"):
        mime = "text/html; charset=utf-8"
    elif mime is None:
        mime = "application/octet-stream"
    return data, mime


def _read_json_if_exists(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def discover_candidates(root_dir: Path) -> list[dict[str, Any]]:
    """Discover single or multi-candidate compiled directories inside root_dir."""
    root = root_dir.resolve()
    dirs: list[tuple[str, Path]] = []
    if (root / "logo.svg").is_file():
        dirs.append(("default", root))
    else:
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.is_dir() and (child / "logo.svg").is_file():
                dirs.append((child.name, child))

    candidates: list[dict[str, Any]] = []
    for cid, cdir in dirs:
        meta = _read_json_if_exists(cdir / "meta.json")
        metrics = _read_json_if_exists(cdir / "metrics.json")
        spec = _read_json_if_exists(cdir / "spec.json")
        has_overlay = (cdir / "overlay.svg").is_file() or (
            isinstance(meta, dict)
            and "grid" in meta
            and "affine" in meta
            and "unit" in meta
        )
        candidates.append(
            {
                "id": cid,
                "meta": meta,
                "metrics": metrics,
                "spec": spec,
                "files": {
                    "logo_svg": f"/api/candidates/{cid}/logo.svg",
                    "sheet_png": (
                        f"/api/candidates/{cid}/sheet.png"
                        if (cdir / "sheet.png").is_file()
                        else None
                    ),
                    "overlay_svg": (
                        f"/api/candidates/{cid}/overlay.svg" if has_overlay else None
                    ),
                },
            }
        )
    return candidates


def _candidate_dir_map(root_dir: Path) -> dict[str, Path]:
    root = root_dir.resolve()
    if (root / "logo.svg").is_file():
        return {"default": root}
    mapping: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.is_dir() and (child / "logo.svg").is_file():
            mapping[child.name] = child
    return mapping


def _build_overlay_svg(cdir: Path) -> str | None:
    overlay_path = cdir / "overlay.svg"
    if overlay_path.is_file():
        return overlay_path.read_text(encoding="utf-8")
    meta = _read_json_if_exists(cdir / "meta.json")
    logo_path = cdir / "logo.svg"
    if not isinstance(meta, dict) or not logo_path.is_file():
        return None
    logo_text = logo_path.read_text(encoding="utf-8")
    d_match = re.search(r'<path[^>]*\sd="([^"]*)"', logo_text)
    if not d_match:
        return None
    grid = GridSpec.model_validate(meta["grid"])
    unit = float(meta["unit"])
    canvas_size = int(meta.get("canvas_size", 1000))
    affine_list = meta["affine"]
    affine = (
        float(affine_list[0]),
        float(affine_list[1]),
        float(affine_list[2]),
        float(affine_list[3]),
        float(affine_list[4]),
        float(affine_list[5]),
    )
    grid_svg = grid_overlay_svg(grid, unit, affine, canvas_size)
    return render_svg_doc(
        d_match.group(1),
        canvas_size,
        fill="#111111",
        background="#ffffff",
        extra_before=grid_svg,
        title=f"{meta.get('name', 'mark')} (construction grid)",
    )


def _load_review_state(root_dir: Path) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    for path in sorted(root_dir.iterdir(), key=lambda p: p.name):
        if path.is_file() and ROUND_RE.match(path.name):
            data = _read_json_if_exists(path)
            if isinstance(data, dict):
                history.append(data)
    history.sort(key=lambda item: int(item.get("round", 0)))

    latest = _read_json_if_exists(root_dir / "review.json")
    if isinstance(latest, dict):
        next_round = max(
            int(latest.get("round", 1)) + 1,
            max((int(h.get("round", 0)) for h in history), default=0) + 2,
        )
    else:
        next_round = max((int(h.get("round", 0)) for h in history), default=0) + 1

    return {
        "round": next_round,
        "latest_review": latest if isinstance(latest, dict) else None,
        "history": history,
    }


def _archive_and_write_review(root_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    review_path = root_dir / "review.json"
    existing = _read_json_if_exists(review_path)
    max_archived = 0
    for path in root_dir.iterdir():
        match = ROUND_RE.match(path.name)
        if match:
            max_archived = max(max_archived, int(match.group(1)))

    if isinstance(existing, dict):
        prior_round = int(existing.get("round", max_archived + 1))
        while (root_dir / f"review.round-{prior_round}.json").exists():
            prior_round += 1
        archive_path = root_dir / f"review.round-{prior_round}.json"
        archive_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        next_round = max(prior_round, max_archived) + 1
    else:
        next_round = max_archived + 1

    record = {
        "schemaVersion": 1,
        "round": next_round,
        "status": payload["status"],
        "selected_candidate": payload.get("selected_candidate"),
        "summary": payload.get("summary", ""),
        "pins": payload.get("pins", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp_path = root_dir / ".review.json.tmp"
    tmp_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(review_path)
    return record


class StudioState:
    """Thread-safe shared state for an active Studio HTTP session."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.lock = threading.Lock()
        self.submitted_event = threading.Event()
        self.submitted_review: dict[str, Any] | None = None

    def session_payload(self) -> dict[str, Any]:
        with self.lock:
            candidates = discover_candidates(self.root_dir)
            review_state = _load_review_state(self.root_dir)
            variants = _read_json_if_exists(self.root_dir / "variants.json")
            tokens = _read_json_if_exists(self.root_dir / "tokens.spec.json")
            kit_files = {
                name: f"/api/kit/{name}"
                for name in sorted(ALLOWED_KIT_FILES)
                if (self.root_dir / name).is_file()
            }
            return {
                "dir": str(self.root_dir),
                "candidates": candidates,
                "variants": variants if isinstance(variants, list) else None,
                "tokens": tokens if isinstance(tokens, dict) else None,
                "kit": kit_files if kit_files else None,
                **review_state,
            }

    def save_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            record = _archive_and_write_review(self.root_dir, payload)
            self.submitted_review = record
            self.submitted_event.set()
            return record


class StudioHandler(BaseHTTPRequestHandler):
    """HTTP request handler for BrandSpec Studio."""

    def __init__(self, *args: Any, state: StudioState, **kwargs: Any) -> None:
        self.state = state
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data: Any) -> None:
        raw = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", raw)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        req_path = unquote(parsed.path)

        if req_path == "/":
            try:
                data, mime = _load_asset("index.html")
                self._send_bytes(HTTPStatus.OK, mime, data)
            except FileNotFoundError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Studio index not found"})
            return

        if req_path.startswith("/assets/"):
            rel = req_path[len("/assets/") :]
            if not rel or "/" in rel or "\\" in rel or ".." in rel:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid asset path"})
                return
            try:
                data, mime = _load_asset(rel)
                self._send_bytes(HTTPStatus.OK, mime, data)
            except FileNotFoundError:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Asset not found"})
            return

        if req_path == "/api/session":
            self._send_json(HTTPStatus.OK, self.state.session_payload())
            return

        if req_path.startswith("/api/candidates/"):
            rest = req_path[len("/api/candidates/") :]
            if "\\" in rest or ".." in rest.split("/"):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "Path traversal rejected"})
                return
            parts = rest.split("/")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Invalid candidate path"})
                return
            cid, filename = parts
            if filename not in ALLOWED_CANDIDATE_FILES:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "File type not permitted"})
                return
            cdirs = _candidate_dir_map(self.state.root_dir)
            if cid not in cdirs:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown candidate"})
                return
            cdir = cdirs[cid]
            target = (cdir / filename).resolve()
            if not _is_within(self.state.root_dir, target) or not _is_within(cdir, target):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "Path outside candidate root"})
                return
            if filename == "overlay.svg" and not target.is_file():
                overlay = _build_overlay_svg(cdir)
                if overlay is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Overlay unavailable"})
                    return
                self._send_bytes(HTTPStatus.OK, "image/svg+xml; charset=utf-8", overlay.encode("utf-8"))
                return
            if not target.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
                return
            mime, _ = mimetypes.guess_type(target.name)
            if target.suffix == ".svg":
                mime = "image/svg+xml; charset=utf-8"
            elif target.suffix == ".json":
                mime = "application/json; charset=utf-8"
            elif mime is None:
                mime = "application/octet-stream"
            self._send_bytes(HTTPStatus.OK, mime, target.read_bytes())
            return

        if req_path.startswith("/api/kit/"):
            rel = req_path[len("/api/kit/") :]
            if not rel or "/" in rel or "\\" in rel or ".." in rel or rel not in ALLOWED_KIT_FILES:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "Invalid kit artifact path"})
                return
            target = (self.state.root_dir / rel).resolve()
            if not _is_within(self.state.root_dir, target) or not target.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Kit artifact not found"})
                return
            mime, _ = mimetypes.guess_type(target.name)
            if target.suffix == ".svg":
                mime = "image/svg+xml; charset=utf-8"
            elif target.suffix == ".css":
                mime = "text/css; charset=utf-8"
            elif target.suffix == ".json":
                mime = "application/json; charset=utf-8"
            elif mime is None:
                mime = "application/octet-stream"
            self._send_bytes(HTTPStatus.OK, mime, target.read_bytes())
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/review":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Route not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return
        if length <= 0 or length > 2_000_000:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid payload size"})
            return

        try:
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Invalid JSON: {exc}"})
            return

        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Expected JSON object"})
            return

        status = payload.get("status")
        if status not in VALID_STATUSES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "status must be one of: approve, revise, reject"},
            )
            return

        pins = payload.get("pins", [])
        if not isinstance(pins, list):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "pins must be a list"})
            return
        normalized_pins: list[dict[str, Any]] = []
        for idx, pin in enumerate(pins, start=1):
            if not isinstance(pin, dict):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Each pin must be an object"})
                return
            try:
                x_grid = round(float(pin["x_grid"]), 4)
                y_grid = round(float(pin["y_grid"]), 4)
            except (KeyError, TypeError, ValueError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"Pin {idx} requires numeric x_grid and y_grid"},
                )
                return
            normalized_pins.append(
                {
                    "id": int(pin.get("id", idx)),
                    "candidate_id": str(pin.get("candidate_id", "default")),
                    "x_grid": x_grid,
                    "y_grid": y_grid,
                    "comment": str(pin.get("comment", "")).strip(),
                }
            )

        selected = payload.get("selected_candidate")
        clean_payload = {
            "status": status,
            "selected_candidate": str(selected) if selected is not None else None,
            "summary": str(payload.get("summary", "")).strip(),
            "pins": normalized_pins,
        }
        record = self.state.save_review(clean_payload)
        self._send_json(HTTPStatus.OK, record)


class StudioHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def create_studio_server(
    root_dir: Path,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, StudioState]:
    """Create a configured ThreadingHTTPServer for the studio review directory."""
    state = StudioState(root_dir)
    handler = partial(StudioHandler, state=state)
    server = StudioHTTPServer((host, port), handler)
    return server, state
