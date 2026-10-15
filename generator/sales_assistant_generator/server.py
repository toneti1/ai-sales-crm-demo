"""Tiny dependency-free HTTP server exposing POST /generate for integration demos."""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List

from .generator import generate_personalized_package

MAX_BODY_BYTES = 64 * 1024
RATE_LIMIT_PER_MINUTE = 30

_rate_windows: Dict[str, List[float]] = {}
_rate_lock = threading.Lock()


def _rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        window = [t for t in _rate_windows.get(client_ip, []) if now - t < 60]
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            _rate_windows[client_ip] = window
            return True
        window.append(now)
        _rate_windows[client_ip] = window
    return False


class GenerateHandler(BaseHTTPRequestHandler):
    server_version = "BaseHTTP/0.6"

    def version_string(self) -> str:
        """Avoid leaking server and Python version details."""
        return "BaseHTTP/0.6"

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib API
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "Not found. Use POST /generate or GET /health."})

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        if self.path != "/generate":
            self._send_json(404, {"error": "Not found. Use POST /generate."})
            return

        if _rate_limited(self.client_address[0]):
            self._send_json(429, {"error": "Too many requests"})
            return

        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            self._send_json(415, {"error": "Content-Type must be application/json"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "Request body too large"})
            return

        try:
            raw_body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "Body must be a JSON object"})
                return
            result = generate_personalized_package(payload)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON body"})
            return
        except Exception as exc:  # noqa: BLE001 - log detail, expose generic error
            print(f"POST /generate failed: {exc!r}", file=sys.stderr)
            self._send_json(400, {"error": "Invalid request"})
            return

        self._send_json(200, result)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8080) -> None:
    httpd = HTTPServer((host, port), GenerateHandler)
    print(f"Generator server running at http://{host}:{port}")
    print("POST lead JSON to /generate")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
