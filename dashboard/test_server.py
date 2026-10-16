"""Tests for the lightweight CRM dashboard server."""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import unittest
from http.server import HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = ROOT_DIR / "dashboard"

_tmp_dir = TemporaryDirectory()
TEST_DB = Path(_tmp_dir.name) / "unified_leads.json"

def _reset_test_db():
    if (ROOT_DIR / "unified_leads.json").exists():
        shutil.copy(ROOT_DIR / "unified_leads.json", TEST_DB)
    else:
        sample = {
            "updatedAt": "2026-10-15T12:00:00Z",
            "totalLeads": 1,
            "leads": [
                {
                    "lead": {
                        "placeId": "ChIJtest123",
                        "companyName": "Test Corp",
                        "phone": "+34900000000",
                        "website": "https://example.com",
                        "address": "Calle Test 1",
                        "rating": 4.5,
                        "reviewCount": 10,
                        "status": "new",
                        "priority": "high",
                        "notes": "Initial note",
                        "tags": ["test"],
                        "auditScore": 75,
                        "email": "test@example.com",
                        "createdAt": "2026-10-15T10:00:00Z"
                    },
                    "coldEmail": {
                        "subject": "Test Subject",
                        "body": "Test Body"
                    }
                }
            ]
        }
        TEST_DB.write_text(json.dumps(sample), encoding="utf-8")

_reset_test_db()
os.environ["LEADS_DB"] = str(TEST_DB)
os.environ["STAGING_LEADS_DB"] = str(Path(_tmp_dir.name) / "staging_leads.json")

sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(ROOT_DIR))

from dashboard import server as server_mod  # noqa: E402
from dashboard.server import DashboardHandler  # noqa: E402
from integrate import process_leads_file  # noqa: E402


def get_free_port() -> int:
    """Ask the OS for an ephemeral port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class DashboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Refresh the temp database from the real one before each test run.
        _reset_test_db()

        cls.server_port = get_free_port()
        cls.server = HTTPServer(("127.0.0.1", cls.server_port), DashboardHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server_port}"

        # Wait for the server to start listening.
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with urlopen(cls.base_url, timeout=1):
                    break
            except Exception:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        # Refresh the temp database before each test method for test isolation.
        _reset_test_db()

    def _get(self, path: str) -> tuple[int, Any]:
        with urlopen(f"{self.base_url}{path}", timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _get_raw(self, path: str) -> tuple[int, bytes]:
        with urlopen(f"{self.base_url}{path}", timeout=10) as resp:
            return resp.status, resp.read()

    def _post(self, path: str, payload: dict) -> tuple[int, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post_error(self, path: str, payload: dict) -> tuple[int, str]:
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8")
        except HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def test_index_html_is_served(self):
        status, body = self._get_raw("/")
        self.assertEqual(status, 200)
        self.assertIn(b"AI Sales Assistant CRM", body)
        self.assertIn(b"<div id=\"root\">", body)

    def test_api_leads_returns_valid_json(self):
        status, data = self._get("/api/leads")
        self.assertEqual(status, 200)
        self.assertIn("leads", data)
        self.assertIsInstance(data["leads"], list)

    def test_api_lead_email_returns_email_fields(self):
        _, data = self._get("/api/leads")
        if not data.get("leads"):
            self.skipTest("No leads available to test email endpoint")
        place_id = data["leads"][0]["lead"]["placeId"]
        status, email = self._get(f"/api/leads/{place_id}/email")
        self.assertEqual(status, 200)
        self.assertEqual(email["placeId"], place_id)
        self.assertIn("subject", email)
        self.assertIn("body", email)

    def test_post_lead_updates_and_persists(self):
        _, before = self._get("/api/leads")
        if not before.get("leads"):
            self.skipTest("No leads available to test update endpoint")

        lead = before["leads"][0]["lead"]
        place_id = lead["placeId"]
        new_status = "contacted" if lead.get("status") != "contacted" else "follow-up-sent"

        status, body = self._post(
            f"/api/leads/{place_id}",
            {"status": new_status, "notes": "Test note", "tags": ["test"]},
        )
        self.assertEqual(status, 200)
        self.assertTrue(body.get("ok"))
        self.assertEqual(body["lead"]["status"], new_status)
        self.assertEqual(body["lead"]["notes"], "Test note")
        self.assertEqual(body["lead"]["tags"], ["test"])

        # Verify persistence by reading the temp file directly.
        payload = json.loads(TEST_DB.read_text(encoding="utf-8"))
        updated = next(
            (l for l in payload.get("leads", []) if l.get("lead", {}).get("placeId") == place_id),
            None,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["lead"]["status"], new_status)
        self.assertEqual(updated["lead"]["notes"], "Test note")
        self.assertEqual(updated["lead"]["tags"], ["test"])

    def test_post_lead_rejects_unknown_fields(self):
        _, data = self._get("/api/leads")
        if not data.get("leads"):
            self.skipTest("No leads available")
        place_id = data["leads"][0]["lead"]["placeId"]
        status, body = self._post_error(
            f"/api/leads/{place_id}", {"unknownField": "value"}
        )
        self.assertEqual(status, 400)
        self.assertIn("Unknown fields", body)

    def test_post_lead_rejects_invalid_status(self):
        _, data = self._get("/api/leads")
        if not data.get("leads"):
            self.skipTest("No leads available")
        place_id = data["leads"][0]["lead"]["placeId"]
        status, body = self._post_error(
            f"/api/leads/{place_id}", {"status": "not-a-status"}
        )
        self.assertEqual(status, 400)
        self.assertIn("Invalid status", body)

    def test_post_lead_rejects_invalid_priority(self):
        _, data = self._get("/api/leads")
        if not data.get("leads"):
            self.skipTest("No leads available")
        place_id = data["leads"][0]["lead"]["placeId"]
        status, body = self._post_error(
            f"/api/leads/{place_id}", {"priority": "ultra-critical"}
        )
        self.assertEqual(status, 400)
        self.assertIn("Invalid priority", body)

    def test_post_lead_rejects_non_string_notes(self):
        _, data = self._get("/api/leads")
        if not data.get("leads"):
            self.skipTest("No leads available")
        place_id = data["leads"][0]["lead"]["placeId"]
        status, body = self._post_error(
            f"/api/leads/{place_id}", {"notes": {"injected": "dict"}}
        )
        self.assertEqual(status, 400)
        self.assertIn("notes must be a string", body)

    def test_post_lead_rejects_invalid_email_sent_at(self):
        _, data = self._get("/api/leads")
        if not data.get("leads"):
            self.skipTest("No leads available")
        place_id = data["leads"][0]["lead"]["placeId"]
        status, body = self._post_error(
            f"/api/leads/{place_id}", {"emailSentAt": "not-a-date"}
        )
        self.assertEqual(status, 400)
        self.assertIn("emailSentAt must be a valid ISO-8601 string", body)

    def test_delete_lead_removes_it(self):
        _, before = self._get("/api/leads")
        if not before.get("leads"):
            self.skipTest("No leads available to delete")

        total_before = before["totalLeads"]
        place_id = before["leads"][0]["lead"]["placeId"]

        req = Request(
            f"{self.base_url}/api/leads/{place_id}",
            method="DELETE",
        )
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)

        _, after = self._get("/api/leads")
        self.assertEqual(after["totalLeads"], total_before - 1)
        self.assertNotIn(place_id, [l.get("lead", {}).get("placeId") for l in after["leads"]])

    def test_delete_decodes_url_encoded_place_id(self):
        # Seed the temp database with a lead whose placeId contains a colon.
        encoded_place_id = "abc%3Adef"
        raw_place_id = "abc:def"
        TEST_DB.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "leads": [
                        {
                            "lead": {
                                "companyName": "Encoded Lead",
                                "placeId": raw_place_id,
                                "status": "new",
                                "priority": "medium",
                                "tags": [],
                                "createdAt": "2026-08-02T00:00:00+00:00",
                            },
                            "audit": {},
                            "coldEmail": {},
                        }
                    ],
                    "totalLeads": 1,
                }
            ),
            encoding="utf-8",
        )

        req = Request(
            f"{self.base_url}/api/leads/{encoded_place_id}",
            method="DELETE",
        )
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)

        _, after = self._get("/api/leads")
        self.assertEqual(after["totalLeads"], 0)
        self.assertEqual(after["leads"], [])

    def test_leads_include_created_at(self):
        _, data = self._get("/api/leads")
        self.assertIn("leads", data)
        if not data["leads"]:
            self.skipTest("No leads available")
        for item in data["leads"]:
            self.assertIn("createdAt", item.get("lead", {}))

    def test_crm_fields_preserved_across_integration_rerun(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_file = tmp_path / "leads.json"
            output_file = tmp_path / "unified_leads.json"
            html_dir = tmp_path / "pages"

            input_file.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "generatedAt": "2026-07-30T00:00:00.000Z",
                        "query": {"city": "Test", "sector": "dentists"},
                        "leads": [
                            {
                                "placeId": "preserve-test-1",
                                "name": "Alpha Dental",
                                "category": "Dentist",
                                "city": "Test",
                                "website": "https://alpha.example",
                                "email": "a@alpha.example",
                                "size": "small",
                                "priority": "medium",
                                "segment": "B",
                                "facts": {
                                    "https": True,
                                    "loadTimeMs": 1000,
                                    "hasContactForm": True,
                                    "bookingEngine": False,
                                    "mobileOverflow": False,
                                    "siteDown": False,
                                },
                                "seoFails": [],
                                "audit": {"painPoints": []},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = process_leads_file(input_file, output_file, html_dir)
            self.assertEqual(result["newLeadsAdded"], 1)
            lead0 = result["leads"][0]["lead"]
            self.assertEqual(lead0["status"], "new")

            # Simulate dashboard edits.
            lead0["status"] = "contacted"
            lead0["notes"] = "Follow-up next week"
            lead0["tags"] = ["hot"]
            lead0["emailSentAt"] = "2026-07-30T10:00:00.000Z"
            output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            # Re-run integration with the same input.
            result2 = process_leads_file(input_file, output_file, html_dir)
            self.assertEqual(result2["newLeadsAdded"], 0)
            self.assertEqual(result2["totalLeads"], 1)

            lead_after = result2["leads"][0]["lead"]
            self.assertEqual(lead_after["status"], "contacted")
            self.assertEqual(lead_after["notes"], "Follow-up next week")
            self.assertEqual(lead_after["tags"], ["hot"])
            self.assertEqual(lead_after["emailSentAt"], "2026-07-30T10:00:00.000Z")


class TokenAuthTests(unittest.TestCase):
    """Auth behavior when DASHBOARD_TOKEN is configured."""

    TOKEN = "test-token"

    @classmethod
    def setUpClass(cls) -> None:
        cls.server_port = get_free_port()
        cls.server = HTTPServer(("127.0.0.1", cls.server_port), DashboardHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server_port}"
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with urlopen(cls.base_url, timeout=1):
                    break
            except HTTPError:
                break  # 401 while token is patched still means the server is up
            except Exception:
                time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        server_mod.DASHBOARD_TOKEN = self.TOKEN
        server_mod._auth_failures.clear()

    def tearDown(self) -> None:
        server_mod.DASHBOARD_TOKEN = ""
        server_mod._auth_failures.clear()

    def _status(self, path: str, token: str | None = None) -> int:
        headers = {"X-Dashboard-Token": token} if token else {}
        req = Request(f"{self.base_url}{path}", headers=headers)
        try:
            with urlopen(req, timeout=10) as resp:
                return resp.status
        except HTTPError as exc:
            return exc.code

    def test_missing_token_returns_401(self):
        self.assertEqual(self._status("/api/leads"), 401)

    def test_wrong_token_returns_401(self):
        self.assertEqual(self._status("/api/leads", token="nope"), 401)

    def test_header_token_returns_200(self):
        self.assertEqual(self._status("/api/leads", token=self.TOKEN), 200)

    def test_query_token_returns_200(self):
        self.assertEqual(self._status(f"/api/leads?token={self.TOKEN}"), 200)

    def test_five_failures_then_429(self):
        for _ in range(5):
            self.assertEqual(self._status("/api/leads", token="bad"), 401)
        self.assertEqual(self._status("/api/leads", token="bad"), 429)
        # Even the correct token is throttled once the budget is spent.
        self.assertEqual(self._status("/api/leads", token=self.TOKEN), 429)

    def test_query_login_plants_cookie_and_cookie_authenticates(self):
        req = Request(f"{self.base_url}/api/leads?token={self.TOKEN}")
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            set_cookie = resp.headers.get("Set-Cookie", "")
        self.assertIn(f"{server_mod.AUTH_COOKIE}={self.TOKEN}", set_cookie)

        req = Request(
            f"{self.base_url}/api/leads",
            headers={"Cookie": f"{server_mod.AUTH_COOKIE}={self.TOKEN}"},
        )
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.status, 200)

    def test_security_headers_present(self):
        req = Request(f"{self.base_url}/api/leads", headers={"X-Dashboard-Token": self.TOKEN})
        with urlopen(req, timeout=10) as resp:
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")
            self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")

    def test_cookie_secure_flag_on_https(self):
        req = Request(
            f"{self.base_url}/api/leads?token={self.TOKEN}",
            headers={"X-Forwarded-Proto": "https"},
        )
        with urlopen(req, timeout=10) as resp:
            set_cookie = resp.headers.get("Set-Cookie", "")
            self.assertIn("; Secure", set_cookie)

    def test_socket_timeout_configured(self):
        self.assertEqual(DashboardHandler.timeout, 10)

    def test_oversized_place_id_rejected(self):
        long_id = "a" * 300
        req = Request(
            f"{self.base_url}/api/leads/{long_id}",
            data=b"{}",
            headers={"X-Dashboard-Token": self.TOKEN, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                self.fail(f"Expected 400, got {resp.status}")
        except HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_remote_origin_host_matching(self):
        prev_remote = server_mod.ALLOW_REMOTE
        server_mod.ALLOW_REMOTE = True
        try:
            bad_req = Request(
                f"{self.base_url}/api/leads/some-id",
                data=b"{}",
                headers={
                    "X-Dashboard-Token": self.TOKEN,
                    "Content-Type": "application/json",
                    "Origin": "https://evil.example.com",
                },
                method="POST",
            )
            try:
                with urlopen(bad_req, timeout=10) as resp:
                    self.fail(f"Expected 403, got {resp.status}")
            except HTTPError as exc:
                self.assertEqual(exc.code, 403)
        finally:
            server_mod.ALLOW_REMOTE = prev_remote


if __name__ == "__main__":
    unittest.main()
