from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

from sagar_monitor.security.foundation import (
    append_audit_event,
    apply_security_migration,
    authenticate_user,
    authorize,
    consume_enrollment_token,
    consume_rate_limit,
    create_enrollment_token,
    create_organization,
    create_session,
    create_user,
    hash_password,
    revoke_session,
    validate_session,
    verify_audit_chain,
    verify_csrf,
    verify_password,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
PASSWORD = "Commercial#Secure2026"


class SecurityFoundationTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_security_migration(self.connection)
        self.org_a = create_organization(
            self.connection, name="Organization A", organization_id="org-a", now=NOW
        )
        self.org_b = create_organization(
            self.connection, name="Organization B", organization_id="org-b", now=NOW
        )
        self.admin_id = create_user(
            self.connection,
            organization_id=self.org_a,
            username="admin.user",
            password=PASSWORD,
            role="admin",
            now=NOW,
        )

    def tearDown(self):
        self.connection.close()

    def test_no_default_or_weak_password_is_accepted(self):
        with self.assertRaises(ValueError):
            hash_password("")
        with self.assertRaises(ValueError):
            hash_password("Admin@12345")
        with self.assertRaises(ValueError):
            create_user(
                self.connection,
                organization_id=self.org_a,
                username="weak.user",
                password="password",
                role="viewer",
            )

    def test_password_hash_and_authentication(self):
        stored = hash_password(PASSWORD, salt=b"0123456789abcdef")
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertTrue(verify_password(PASSWORD, stored))
        self.assertFalse(verify_password("wrong", stored))
        authenticated = authenticate_user(
            self.connection,
            organization_id=self.org_a,
            username="ADMIN.USER",
            password=PASSWORD,
        )
        self.assertIsNotNone(authenticated)
        self.assertNotIn("password_hash", authenticated)
        self.assertIsNone(
            authenticate_user(
                self.connection,
                organization_id=self.org_b,
                username="admin.user",
                password=PASSWORD,
            )
        )

    def test_session_and_csrf_store_only_hashes(self):
        tokens = create_session(
            self.connection,
            user_id=self.admin_id,
            ttl_seconds=3600,
            client_fingerprint="browser-a",
            now=NOW,
        )
        stored = self.connection.execute(
            "SELECT session_hash,csrf_hash FROM sessions_v1"
        ).fetchone()
        self.assertNotEqual(stored[0], tokens.session_token)
        self.assertNotEqual(stored[1], tokens.csrf_token)
        session = validate_session(
            self.connection,
            tokens.session_token,
            organization_id=self.org_a,
            client_fingerprint="browser-a",
            now=NOW + timedelta(minutes=1),
        )
        self.assertIsNotNone(session)
        self.assertTrue(verify_csrf(self.connection, tokens.session_token, tokens.csrf_token))
        self.assertFalse(verify_csrf(self.connection, tokens.session_token, "wrong"))
        self.assertIsNone(
            validate_session(
                self.connection,
                tokens.session_token,
                organization_id=self.org_b,
                client_fingerprint="browser-a",
                now=NOW,
            )
        )
        self.assertIsNone(
            validate_session(
                self.connection,
                tokens.session_token,
                organization_id=self.org_a,
                client_fingerprint="different-browser",
                now=NOW,
            )
        )

    def test_session_expiry_and_revocation(self):
        tokens = create_session(
            self.connection, user_id=self.admin_id, ttl_seconds=60, now=NOW
        )
        self.assertIsNone(
            validate_session(
                self.connection,
                tokens.session_token,
                now=NOW + timedelta(seconds=61),
            )
        )
        fresh = create_session(
            self.connection, user_id=self.admin_id, ttl_seconds=3600, now=NOW
        )
        self.assertTrue(revoke_session(self.connection, fresh.session_token, now=NOW))
        self.assertIsNone(validate_session(self.connection, fresh.session_token, now=NOW))

    def test_role_and_organization_authorization(self):
        tokens = create_session(
            self.connection, user_id=self.admin_id, ttl_seconds=3600, now=NOW
        )
        session = validate_session(self.connection, tokens.session_token, now=NOW)
        self.assertTrue(authorize(session, {"admin"}, organization_id=self.org_a))
        self.assertFalse(authorize(session, {"viewer"}, organization_id=self.org_a))
        self.assertFalse(authorize(session, {"admin"}, organization_id=self.org_b))

    def test_enrollment_token_is_scoped_expiring_and_limited(self):
        token = create_enrollment_token(
            self.connection,
            organization_id=self.org_a,
            ttl_seconds=600,
            max_uses=1,
            now=NOW,
        )
        stored = self.connection.execute("SELECT token_hash FROM enrollment_tokens_v1").fetchone()[0]
        self.assertNotEqual(stored, token)
        used = consume_enrollment_token(
            self.connection, token, organization_id=self.org_a, now=NOW
        )
        self.assertIsNotNone(used)
        self.assertIsNone(
            consume_enrollment_token(
                self.connection, token, organization_id=self.org_a, now=NOW
            )
        )
        expired = create_enrollment_token(
            self.connection,
            organization_id=self.org_a,
            ttl_seconds=60,
            now=NOW,
        )
        self.assertIsNone(
            consume_enrollment_token(
                self.connection,
                expired,
                organization_id=self.org_a,
                now=NOW + timedelta(seconds=61),
            )
        )

    def test_rate_limit_enforces_window_and_resets(self):
        first = consume_rate_limit(
            self.connection, "login:10.0.0.1", limit=2, window_seconds=60, now=NOW
        )
        second = consume_rate_limit(
            self.connection,
            "login:10.0.0.1",
            limit=2,
            window_seconds=60,
            now=NOW + timedelta(seconds=1),
        )
        third = consume_rate_limit(
            self.connection,
            "login:10.0.0.1",
            limit=2,
            window_seconds=60,
            now=NOW + timedelta(seconds=2),
        )
        reset = consume_rate_limit(
            self.connection,
            "login:10.0.0.1",
            limit=2,
            window_seconds=60,
            now=NOW + timedelta(seconds=61),
        )
        self.assertTrue(first["allowed"])
        self.assertTrue(second["allowed"])
        self.assertFalse(third["allowed"])
        self.assertTrue(reset["allowed"])

    def test_audit_chain_detects_tampering(self):
        append_audit_event(
            self.connection,
            organization_id=self.org_a,
            event_type="user.created",
            actor_user_id=self.admin_id,
            subject_id="user-2",
            detail={"role": "viewer"},
            now=NOW,
        )
        append_audit_event(
            self.connection,
            organization_id=self.org_a,
            event_type="session.revoked",
            actor_user_id=self.admin_id,
            subject_id="session-1",
            now=NOW + timedelta(seconds=1),
        )
        self.assertTrue(verify_audit_chain(self.connection)["ok"])
        self.connection.execute(
            "UPDATE security_audit_log_v1 SET detail_json='tampered' WHERE sequence_id=1"
        )
        self.connection.commit()
        verification = verify_audit_chain(self.connection)
        self.assertFalse(verification["ok"])
        self.assertEqual(verification["sequence_id"], 1)

    def test_migration_is_idempotent(self):
        apply_security_migration(self.connection)
        apply_security_migration(self.connection)
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("organizations_v1", tables)
        self.assertIn("sessions_v1", tables)
        self.assertIn("security_audit_log_v1", tables)


if __name__ == "__main__":
    unittest.main()
