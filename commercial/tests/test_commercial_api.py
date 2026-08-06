from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sagar_monitor.api import CommercialAPI, Request, make_wsgi_app
from sagar_monitor.security import create_organization, create_user


PASSWORD = "Commercial#Secure2026"


def json_request(method: str, target: str, payload=None, headers=None, remote_addr="10.0.0.1") -> Request:
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return Request(method=method, target=target, headers=merged, body=body, remote_addr=remote_addr)


class CommercialAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "commercial.db"
        self.now = datetime.now(timezone.utc)
        self.api = CommercialAPI(
            self.db,
            clock=lambda: self.now,
            max_body_bytes=4096,
            login_limit=2,
            login_window_seconds=60,
        )
        connection = sqlite3.connect(self.db)
        try:
            create_organization(connection, name="Organization A", organization_id="org-a", now=self.now)
            create_organization(connection, name="Organization B", organization_id="org-b", now=self.now)
            self.admin_a = create_user(
                connection,
                organization_id="org-a",
                username="admin.a",
                password=PASSWORD,
                role="admin",
                now=self.now,
            )
            self.viewer_a = create_user(
                connection,
                organization_id="org-a",
                username="viewer.a",
                password=PASSWORD,
                role="viewer",
                now=self.now,
            )
            self.admin_b = create_user(
                connection,
                organization_id="org-b",
                username="admin.b",
                password=PASSWORD,
                role="admin",
                now=self.now,
            )
        finally:
            connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def login(self, organization_id="org-a", username="admin.a", password=PASSWORD, remote="10.0.0.1"):
        response = self.api.handle(
            json_request(
                "POST",
                "/api/v1/auth/login",
                {"organization_id": organization_id, "username": username, "password": password},
                headers={"X-Client-Fingerprint": "browser-a"},
                remote_addr=remote,
            )
        )
        self.assertEqual(response.status, 200, response.payload)
        return response.payload

    @staticmethod
    def auth_headers(login, *, csrf=False, fingerprint="browser-a"):
        headers = {
            "Authorization": f"Bearer {login['session_token']}",
            "X-Client-Fingerprint": fingerprint,
        }
        if csrf:
            headers["X-CSRF-Token"] = login["csrf_token"]
        return headers

    def test_health_is_public_and_has_security_headers(self):
        response = self.api.handle(
            Request(
                method="GET",
                target="/api/v1/health",
                headers={"X-Request-ID": "request-12345678"},
            )
        )
        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["ok"])
        self.assertEqual(response.headers["X-Request-ID"], "request-12345678")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")

    def test_invalid_json_content_type_and_body_limit(self):
        invalid = self.api.handle(
            Request(
                method="POST",
                target="/api/v1/auth/login",
                headers={"Content-Type": "application/json"},
                body=b"{bad",
            )
        )
        self.assertEqual(invalid.status, 400)
        wrong_type = self.api.handle(
            Request(
                method="POST",
                target="/api/v1/auth/login",
                headers={"Content-Type": "text/plain"},
                body=b"{}",
            )
        )
        self.assertEqual(wrong_type.status, 415)
        large = self.api.handle(
            Request(method="POST", target="/api/v1/auth/login", body=b"x" * 4097)
        )
        self.assertEqual(large.status, 413)

    def test_login_returns_tokens_but_database_stores_only_hashes(self):
        login = self.login()
        self.assertNotIn("password_hash", login["user"])
        connection = sqlite3.connect(self.db)
        try:
            stored = connection.execute("SELECT session_hash,csrf_hash FROM sessions_v1").fetchone()
        finally:
            connection.close()
        self.assertNotEqual(stored[0], login["session_token"])
        self.assertNotEqual(stored[1], login["csrf_token"])

    def test_failed_login_is_rate_limited(self):
        for index in range(2):
            response = self.api.handle(
                json_request(
                    "POST",
                    "/api/v1/auth/login",
                    {"organization_id": "org-a", "username": "admin.a", "password": "wrong"},
                    remote_addr="10.0.0.9",
                )
            )
            self.assertEqual(response.status, 401, index)
        blocked = self.api.handle(
            json_request(
                "POST",
                "/api/v1/auth/login",
                {"organization_id": "org-a", "username": "admin.a", "password": "wrong"},
                remote_addr="10.0.0.9",
            )
        )
        self.assertEqual(blocked.status, 429)

    def test_me_requires_valid_session_and_fingerprint(self):
        self.assertEqual(
            self.api.handle(Request(method="GET", target="/api/v1/auth/me")).status,
            401,
        )
        login = self.login()
        good = self.api.handle(
            Request(
                method="GET",
                target="/api/v1/auth/me",
                headers=self.auth_headers(login),
            )
        )
        self.assertEqual(good.status, 200)
        wrong_fingerprint = self.api.handle(
            Request(
                method="GET",
                target="/api/v1/auth/me",
                headers=self.auth_headers(login, fingerprint="other-browser"),
            )
        )
        self.assertEqual(wrong_fingerprint.status, 401)

    def test_admin_user_creation_requires_csrf_and_list_is_paginated(self):
        login = self.login()
        no_csrf = self.api.handle(
            json_request(
                "POST",
                "/api/v1/users",
                {"username": "new.viewer", "password": PASSWORD, "role": "viewer"},
                headers=self.auth_headers(login),
            )
        )
        self.assertEqual(no_csrf.status, 403)
        created = self.api.handle(
            json_request(
                "POST",
                "/api/v1/users",
                {"username": "new.viewer", "password": PASSWORD, "role": "viewer"},
                headers=self.auth_headers(login, csrf=True),
            )
        )
        self.assertEqual(created.status, 201, created.payload)
        listed = self.api.handle(
            Request(
                method="GET",
                target="/api/v1/users?limit=1&offset=0&q=new",
                headers=self.auth_headers(login),
            )
        )
        self.assertEqual(listed.status, 200)
        self.assertEqual(listed.payload["total"], 1)
        self.assertEqual(len(listed.payload["items"]), 1)
        self.assertNotIn("password_hash", listed.payload["items"][0])

    def test_viewer_cannot_queue_message_but_can_read_own_org(self):
        viewer = self.login(username="viewer.a", remote="10.0.0.2")
        denied = self.api.handle(
            json_request(
                "POST",
                "/api/v1/messages",
                {"canonical_client_ids": ["client-a"], "body": "Hello"},
                headers=self.auth_headers(viewer, csrf=True),
            )
        )
        self.assertEqual(denied.status, 403)
        listed = self.api.handle(
            Request(method="GET", target="/api/v1/messages", headers=self.auth_headers(viewer))
        )
        self.assertEqual(listed.status, 200)

    def test_message_queue_and_report_are_organization_scoped(self):
        admin_a = self.login(remote="10.0.0.3")
        queued = self.api.handle(
            json_request(
                "POST",
                "/api/v1/messages",
                {
                    "canonical_client_ids": ["client-a", "client-b", "client-a"],
                    "title": "Notice",
                    "body": "Class starts soon",
                },
                headers=self.auth_headers(admin_a, csrf=True),
            )
        )
        self.assertEqual(queued.status, 201, queued.payload)
        self.assertEqual(queued.payload["target_count"], 2)
        own = self.api.handle(
            Request(
                method="GET",
                target=f"/api/v1/messages/{queued.payload['message_id']}",
                headers=self.auth_headers(admin_a),
            )
        )
        self.assertEqual(own.status, 200)
        admin_b = self.login(organization_id="org-b", username="admin.b", remote="10.0.0.4")
        other = self.api.handle(
            Request(
                method="GET",
                target=f"/api/v1/messages/{queued.payload['message_id']}",
                headers=self.auth_headers(admin_b),
            )
        )
        self.assertEqual(other.status, 404)

    def test_enrollment_token_is_admin_only_and_not_stored_raw(self):
        admin = self.login(remote="10.0.0.5")
        response = self.api.handle(
            json_request(
                "POST",
                "/api/v1/enrollment-tokens",
                {"label": "lab", "max_uses": 2},
                headers=self.auth_headers(admin, csrf=True),
            )
        )
        self.assertEqual(response.status, 201)
        raw = response.payload["enrollment_token"]
        connection = sqlite3.connect(self.db)
        try:
            stored = connection.execute("SELECT token_hash FROM enrollment_tokens_v1").fetchone()[0]
        finally:
            connection.close()
        self.assertNotEqual(raw, stored)

    def test_logout_requires_csrf_and_revokes_session(self):
        login = self.login(remote="10.0.0.6")
        denied = self.api.handle(
            Request(
                method="POST",
                target="/api/v1/auth/logout",
                headers=self.auth_headers(login),
            )
        )
        self.assertEqual(denied.status, 403)
        done = self.api.handle(
            Request(
                method="POST",
                target="/api/v1/auth/logout",
                headers=self.auth_headers(login, csrf=True),
            )
        )
        self.assertEqual(done.status, 200)
        after = self.api.handle(
            Request(
                method="GET",
                target="/api/v1/auth/me",
                headers=self.auth_headers(login),
            )
        )
        self.assertEqual(after.status, 401)

    def test_wsgi_adapter_returns_bounded_json_response(self):
        wsgi = make_wsgi_app(self.api)
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        result = wsgi(
            {
                "REQUEST_METHOD": "GET",
                "PATH_INFO": "/api/v1/health",
                "QUERY_STRING": "",
                "CONTENT_LENGTH": "0",
                "wsgi.input": BytesIO(b""),
                "REMOTE_ADDR": "127.0.0.1",
            },
            start_response,
        )
        body = b"".join(result)
        payload = json.loads(body)
        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(int(captured["headers"]["Content-Length"]), len(body))
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
