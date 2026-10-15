"""Lightweight CRM dashboard server for the AI Sales Assistant.

Serves the lead dashboard UI and a small JSON API over the standard library
http.server. All data is read from and written to unified_leads.json.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = Path(__file__).resolve().parent
GENERATED_PAGES_DIR = ROOT_DIR / "generated_landing_pages"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

UNIFIED_LEADS_FILE = Path(os.environ.get("LEADS_DB", ROOT_DIR / "unified_leads.json"))
STAGING_LEADS_FILE = ROOT_DIR / "lead-finder" / "leads.json"

ALLOWED_CRM_FIELDS = {"status", "priority", "notes", "tags", "emailSentAt"}
STATUS_VALUES = {"new", "contacted", "follow-up-sent", "replied", "declined", "won"}

MAX_BODY_BYTES = 64 * 1024
MAX_TAGS = 20
MAX_TAG_LEN = 30
MAX_NOTES_LEN = 2000
RATE_LIMIT_PER_MINUTE = 60

_local_hosts = {"127.0.0.1", "localhost", "::1"}
ALLOW_REMOTE = os.environ.get("DASHBOARD_ALLOW_REMOTE") == "1"
_rate_windows: Dict[str, List[float]] = {}
_rate_lock = threading.Lock()

# Optional shared-token auth. When DASHBOARD_TOKEN is set, every request must
# carry it in the X-Dashboard-Token header, a ?token= query param, or the
# cookie planted after a successful query-param login (assets can't send
# headers or query params, so the cookie is what lets the page load).
DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN", "")
AUTH_COOKIE = "dashboard_token"
AUTH_COOKIE_MAX_AGE = 30 * 24 * 3600
AUTH_MAX_FAILURES_PER_MINUTE = 5
_auth_failures: Dict[str, List[float]] = {}

PIPELINE_TIMEOUT_SECONDS = 30 * 60
MAX_PIPELINE_RESULTS = 50
_run_field_re = re.compile(r"^[\w\s.\-,'()áéíóúüñÁÉÍÓÚÜÑ]+$")

_pipeline_state: Dict[str, Any] = {
    "running": False,
    "startedAt": None,
    "finishedAt": None,
    "result": None,
}
_pipeline_lock = threading.Lock()


def _load_leads() -> Dict[str, Any]:
    """Load the unified leads database."""
    if not UNIFIED_LEADS_FILE.exists():
        return {"schemaVersion": 1, "leads": []}
    return json.loads(UNIFIED_LEADS_FILE.read_text(encoding="utf-8"))


def _save_leads(payload: Dict[str, Any]) -> None:
    """Persist the unified leads database atomically (tmp file + rename)."""
    fd, tmp_path = tempfile.mkstemp(
        dir=str(UNIFIED_LEADS_FILE.parent), suffix=".tmp", prefix=".leads-"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(UNIFIED_LEADS_FILE))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _rate_limited(client_ip: str) -> bool:
    """Return True when the client exceeded the per-minute request budget."""
    now = time.monotonic()
    with _rate_lock:
        window = [t for t in _rate_windows.get(client_ip, []) if now - t < 60]
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            _rate_windows[client_ip] = window
            return True
        window.append(now)
        _rate_windows[client_ip] = window
    return False


def _auth_throttled(client_ip: str) -> bool:
    """Return True when the client exceeded the failed-auth budget."""
    now = time.monotonic()
    with _rate_lock:
        window = [t for t in _auth_failures.get(client_ip, []) if now - t < 60]
        _auth_failures[client_ip] = window
        return len(window) >= AUTH_MAX_FAILURES_PER_MINUTE


def _record_auth_failure(client_ip: str) -> None:
    """Register a failed auth attempt for throttling."""
    now = time.monotonic()
    with _rate_lock:
        window = [t for t in _auth_failures.get(client_ip, []) if now - t < 60]
        window.append(now)
        _auth_failures[client_ip] = window


def _validate_run_inputs(
    city: Any, sector: Any, max_results: Any
) -> Optional[str]:
    """Validate pipeline run arguments (frontier validation, no shell)."""
    if not isinstance(city, str) or not 1 <= len(city) <= 80:
        return "city must be a string of 1-80 characters"
    if not _run_field_re.match(city):
        return "city contains invalid characters"
    if not isinstance(sector, str) or not 1 <= len(sector) <= 80:
        return "sector must be a string of 1-80 characters"
    if not _run_field_re.match(sector):
        return "sector contains invalid characters"
    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or max_results < 1
        or max_results > MAX_PIPELINE_RESULTS
    ):
        return f"max must be an integer between 1 and {MAX_PIPELINE_RESULTS}"
    return None


def _run_pipeline_worker(city: str, sector: str, max_results: int) -> None:
    """Execute the pipeline CLI as a subprocess and record the outcome."""
    script = ROOT_DIR / "run_pipeline.py"
    if not script.exists():
        result = {
            "ok": False,
            "added": 0,
            "total": 0,
            "stdout": "",
            "stderr": (
                "The pipeline (lead scraper) is not available in this demo "
                "copy. It only runs on the main computer. You can still "
                "view, edit, delete and export leads here."
            ),
        }
        with _pipeline_lock:
            _pipeline_state["running"] = False
            _pipeline_state["finishedAt"] = datetime.now(timezone.utc).isoformat()
            _pipeline_state["result"] = result
        return
    cmd = [
        sys.executable,
        str(script),
        "--city",
        city,
        "--sector",
        sector,
        "--max",
        str(max_results),
        "--skip-build",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
        ok = proc.returncode == 0
        added = total = 0
        match = re.search(r"New leads added: (\d+)", proc.stdout)
        if match:
            added = int(match.group(1))
        match = re.search(r"Total leads in database: (\d+)", proc.stdout)
        if match:
            total = int(match.group(1))
        result: Dict[str, Any] = {
            "ok": ok,
            "added": added,
            "total": total,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-2000:],
        }
    except subprocess.TimeoutExpired:
        result = {
            "ok": False,
            "added": 0,
            "total": 0,
            "stdout": "",
            "stderr": "Pipeline timed out after 30 minutes.",
        }
    except Exception as exc:  # noqa: BLE001 - report failure without details
        result = {
            "ok": False,
            "added": 0,
            "total": 0,
            "stdout": "",
            "stderr": f"Pipeline failed to start: {exc.__class__.__name__}",
        }
    with _pipeline_lock:
        _pipeline_state["running"] = False
        _pipeline_state["finishedAt"] = datetime.now(timezone.utc).isoformat()
        _pipeline_state["result"] = result


def _start_pipeline(city: str, sector: str, max_results: int) -> bool:
    """Start the pipeline in a background thread. Returns False when busy."""
    with _pipeline_lock:
        if _pipeline_state["running"]:
            return False
        _pipeline_state["running"] = True
        _pipeline_state["startedAt"] = datetime.now(timezone.utc).isoformat()
        _pipeline_state["finishedAt"] = None
        _pipeline_state["result"] = None
    threading.Thread(
        target=_run_pipeline_worker, args=(city, sector, max_results), daemon=True
    ).start()
    return True


def _remove_from_staging(place_id: str) -> None:
    """Drop a lead from the scraper staging file so it cannot be re-added."""
    if not STAGING_LEADS_FILE.exists():
        return
    try:
        payload = json.loads(STAGING_LEADS_FILE.read_text(encoding="utf-8"))
        leads = payload.get("leads", [])
        kept = [lead for lead in leads if lead.get("placeId") != place_id]
        if len(kept) != len(leads):
            payload["leads"] = kept
            STAGING_LEADS_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception:
        pass


def _clear_staging() -> None:
    """Empty the scraper staging file so deleted leads never come back."""
    if not STAGING_LEADS_FILE.exists():
        return
    try:
        STAGING_LEADS_FILE.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "query": {},
                    "leads": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _normalize_path_sep(path: str) -> str:
    """Return a URL-friendly path using forward slashes."""
    return path.replace("\\", "/")


def _build_indexed_leads(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Index leads by placeId for fast lookup."""
    indexed: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("leads", []):
        place_id = item.get("lead", {}).get("placeId")
        if place_id:
            indexed[place_id] = item
    return indexed


class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for dashboard API and static files."""

    def version_string(self) -> str:
        """Avoid leaking server and Python version details."""
        return "BaseHTTP/0.6"

    def _origin_allowed(self) -> bool:
        """Block cross-origin mutations (CSRF / DNS-rebinding).

        Allows same-origin (no header) and requests from local hosts only,
        unless DASHBOARD_ALLOW_REMOTE=1 (public tunnel demo mode).
        """
        if ALLOW_REMOTE:
            return True
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if not origin:
            return True
        try:
            parsed = urlparse(origin)
        except ValueError:
            return False
        return parsed.hostname in _local_hosts

    def _client_ip(self) -> str:
        """Real client IP: prefer CF-Connecting-IP when behind the tunnel."""
        ip = self.client_address[0]
        if ip in _local_hosts:
            forwarded = self.headers.get("CF-Connecting-IP")
            if forwarded:
                return forwarded.strip()
        return ip

    def _check_auth(self) -> int:
        """Return 0 when authorized, else the error status (401/429) to send.

        The token is validated first so a valid token never hits the failure
        throttle (which counts only bad/missing tokens, per real client IP).
        """
        if not DASHBOARD_TOKEN:
            return 0
        provided = self.headers.get("X-Dashboard-Token")
        from_query = False
        if provided is None:
            provided = parse_qs(urlparse(self.path).query).get("token", [None])[0]
            from_query = provided is not None
        if provided is None:
            cookie_header = self.headers.get("Cookie", "")
            match = re.search(
                rf"(?:^|;\s*){AUTH_COOKIE}=([^;]*)", cookie_header
            )
            if match:
                provided = match.group(1)
        if provided is not None and hmac.compare_digest(provided, DASHBOARD_TOKEN):
            if from_query:
                self._set_auth_cookie = True
            return 0
        client_ip = self._client_ip()
        if _auth_throttled(client_ip):
            return 429
        _record_auth_failure(client_ip)
        return 401

    def _send_auth_cookie_if_needed(self) -> None:
        """Plant the auth cookie right after a successful ?token= login."""
        if getattr(self, "_set_auth_cookie", False):
            self.send_header(
                "Set-Cookie",
                f"{AUTH_COOKIE}={DASHBOARD_TOKEN}; Path=/; "
                f"Max-Age={AUTH_COOKIE_MAX_AGE}; SameSite=Strict; HttpOnly",
            )
            self._set_auth_cookie = False

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence default request logging to keep output clean."""
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_auth_cookie_if_needed()
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists():
            self._send_error("Not found", 404)
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self._send_auth_cookie_if_needed()
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length > 0 else b""

    @staticmethod
    def _content_type(path: Path) -> str:
        suffix = path.suffix.lower()
        return {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".ico": "image/x-icon",
            ".json": "application/json; charset=utf-8",
            ".woff2": "font/woff2",
        }.get(suffix, "application/octet-stream")

    def do_GET(self) -> None:  # noqa: N802
        auth_status = self._check_auth()
        if auth_status:
            self._send_error(
                "Unauthorized" if auth_status == 401 else "Too many requests",
                auth_status,
            )
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            index = FRONTEND_DIST / "index.html"
            if index.exists():
                self._send_file(index, "text/html; charset=utf-8")
            else:
                self._send_file(DASHBOARD_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path == "/api/pipeline/status":
            with _pipeline_lock:
                self._send_json({
                    "running": _pipeline_state["running"],
                    "startedAt": _pipeline_state["startedAt"],
                    "finishedAt": _pipeline_state["finishedAt"],
                    "result": _pipeline_state["result"],
                })
            return

        if path == "/api/leads":
            payload = _load_leads()
            # Normalize saved HTML paths for browser URLs.
            for item in payload.get("leads", []):
                saved = item.get("savedHtmlPath")
                if saved:
                    item["savedHtmlPath"] = _normalize_path_sep(saved)
            self._send_json(payload)
            return

        email_match = re.match(r"^/api/leads/([^/]+)/email$", path)
        if email_match:
            place_id = unquote(email_match.group(1))
            payload = _load_leads()
            item = _build_indexed_leads(payload).get(place_id)
            if not item:
                self._send_error("Lead not found", 404)
                return
            cold_email = item.get("coldEmail", {})
            self._send_json({
                "placeId": place_id,
                "companyName": item.get("lead", {}).get("companyName"),
                "subject": cold_email.get("subject"),
                "body": cold_email.get("body"),
            })
            return

        # Serve generated landing pages under /pages/.
        pages_match = re.match(r"^/pages/(.+)$", path)
        if pages_match:
            relative = pages_match.group(1).replace("/", "\\")
            file_path = GENERATED_PAGES_DIR / relative
            # Resolve and guard against directory traversal.
            try:
                file_path = file_path.resolve()
                if str(file_path).startswith(str(GENERATED_PAGES_DIR.resolve())):
                    self._send_file(file_path, "text/html; charset=utf-8")
                    return
            except Exception:
                pass
            self._send_error("Not found", 404)
            return

        # Serve the built frontend when available (SPA with index fallback).
        if FRONTEND_DIST.exists():
            relative = path.lstrip("/").replace("/", os.sep)
            candidate = (FRONTEND_DIST / relative).resolve()
            try:
                if str(candidate).startswith(str(FRONTEND_DIST.resolve())):
                    if candidate.is_file():
                        self._send_file(candidate, self._content_type(candidate))
                        return
                    index = FRONTEND_DIST / "index.html"
                    if index.exists():
                        self._send_file(index, "text/html; charset=utf-8")
                        return
            except Exception:
                pass

        self._send_error("Not found", 404)

    def do_POST(self) -> None:  # noqa: N802
        auth_status = self._check_auth()
        if auth_status:
            self._send_error(
                "Unauthorized" if auth_status == 401 else "Too many requests",
                auth_status,
            )
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/pipeline":
            if _rate_limited(self._client_ip()):
                self._send_error("Too many requests", 429)
                return
            if not self._origin_allowed():
                self._send_error("Origin not allowed", 403)
                return
            content_type = self.headers.get("Content-Type", "")
            if "application/json" not in content_type.lower():
                self._send_error("Content-Type must be application/json", 415)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY_BYTES:
                self._send_error("Request body too large", 413)
                return
            try:
                updates = json.loads(self._read_body().decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send_error("Invalid JSON body", 400)
                return
            if not isinstance(updates, dict):
                self._send_error("Body must be a JSON object", 400)
                return
            invalid = _validate_run_inputs(
                updates.get("city"), updates.get("sector"), updates.get("max")
            )
            if invalid:
                self._send_error(invalid, 400)
                return
            started = _start_pipeline(
                updates["city"], updates["sector"], updates["max"]
            )
            if not started:
                self._send_error("A pipeline run is already in progress", 409)
                return
            self._send_json({"status": "started"})
            return

        match = re.match(r"^/api/leads/([^/]+)$", path)
        if not match:
            self._send_error("Not found", 404)
            return

        if _rate_limited(self._client_ip()):
            self._send_error("Too many requests", 429)
            return

        if not self._origin_allowed():
            self._send_error("Origin not allowed", 403)
            return

        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            self._send_error("Content-Type must be application/json", 415)
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            self._send_error("Request body too large", 413)
            return

        place_id = unquote(match.group(1))
        body = self._read_body()
        try:
            updates = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            self._send_error("Invalid JSON body", 400)
            return

        if not isinstance(updates, dict):
            self._send_error("Body must be a JSON object", 400)
            return

        unknown = set(updates.keys()) - ALLOWED_CRM_FIELDS
        if unknown:
            self._send_error(f"Unknown fields: {', '.join(sorted(unknown))}", 400)
            return

        if "status" in updates and updates["status"] not in STATUS_VALUES:
            self._send_error(
                f"Invalid status. Allowed: {', '.join(sorted(STATUS_VALUES))}", 400
            )
            return

        if "tags" in updates:
            if not isinstance(updates["tags"], list):
                self._send_error("tags must be a list", 400)
                return
            if len(updates["tags"]) > MAX_TAGS:
                self._send_error(f"tags limited to {MAX_TAGS} items", 400)
                return
            if not all(
                isinstance(tag, str) and 0 < len(tag) <= MAX_TAG_LEN
                for tag in updates["tags"]
            ):
                self._send_error(
                    f"each tag must be a string of at most {MAX_TAG_LEN} characters", 400
                )
                return

        if "notes" in updates and isinstance(updates["notes"], str):
            if len(updates["notes"]) > MAX_NOTES_LEN:
                self._send_error(f"notes limited to {MAX_NOTES_LEN} characters", 400)
                return

        payload = _load_leads()
        indexed = _build_indexed_leads(payload)
        item = indexed.get(place_id)
        if not item:
            self._send_error("Lead not found", 404)
            return

        lead_record = item.setdefault("lead", {})
        for key, value in updates.items():
            if value is None:
                lead_record[key] = None
            else:
                lead_record[key] = value

        _save_leads(payload)
        self._send_json({"ok": True, "placeId": place_id, "lead": lead_record})

    def do_DELETE(self) -> None:  # noqa: N802
        auth_status = self._check_auth()
        if auth_status:
            self._send_error(
                "Unauthorized" if auth_status == 401 else "Too many requests",
                auth_status,
            )
            return
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/leads":
            if _rate_limited(self._client_ip()):
                self._send_error("Too many requests", 429)
                return
            if not self._origin_allowed():
                self._send_error("Origin not allowed", 403)
                return
            payload = _load_leads()
            deleted = len(payload.get("leads", []))
            payload["leads"] = []
            payload["totalLeads"] = 0
            _save_leads(payload)
            _clear_staging()
            self._send_json({"ok": True, "deleted": deleted})
            return

        match = re.match(r"^/api/leads/([^/]+)$", path)
        if not match:
            self._send_error("Not found", 404)
            return

        if _rate_limited(self._client_ip()):
            self._send_error("Too many requests", 429)
            return

        if not self._origin_allowed():
            self._send_error("Origin not allowed", 403)
            return

        place_id = unquote(match.group(1))
        payload = _load_leads()
        leads = payload.get("leads", [])
        new_leads = [item for item in leads if item.get("lead", {}).get("placeId") != place_id]

        if len(new_leads) == len(leads):
            self._send_error("Lead not found", 404)
            return

        payload["leads"] = new_leads
        payload["totalLeads"] = len(new_leads)
        _save_leads(payload)
        _remove_from_staging(place_id)
        self._send_json({"ok": True, "deleted": True, "placeId": place_id})


def run_server(port: int = 8000) -> None:
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    if host != "127.0.0.1" and not DASHBOARD_TOKEN:
        print(f"WARNING: dashboard has no authentication; binding to {host} exposes "
              "read/write/delete access to anyone who can reach the port.")
    if ALLOW_REMOTE and not DASHBOARD_TOKEN:
        print("WARNING: DASHBOARD_ALLOW_REMOTE=1 without DASHBOARD_TOKEN - public "
              "demo mode, no authentication. Anyone with the URL can edit and "
              "delete leads.")
    if DASHBOARD_TOKEN:
        print("Token auth enabled (DASHBOARD_TOKEN).")
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


def main() -> int:
    port = int(os.environ.get("DASHBOARD_PORT", "8000"))
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
