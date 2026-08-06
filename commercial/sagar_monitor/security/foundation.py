from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import uuid


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "0005_security_foundation.sql"
ROLES = {"admin", "operator", "viewer"}
PASSWORD_MIN_LENGTH = 14


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _iso(value: datetime | str | None = None) -> str:
    return _utc(value).isoformat()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_username(value: object) -> str:
    username = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", username):
        raise ValueError("username must be 3-64 characters using letters, numbers, dot, underscore or hyphen")
    return username


def validate_password_strength(password: str) -> None:
    value = str(password or "")
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
    classes = (
        any(ch.islower() for ch in value),
        any(ch.isupper() for ch in value),
        any(ch.isdigit() for ch in value),
        any(not ch.isalnum() for ch in value),
    )
    if sum(classes) < 3:
        raise ValueError("password must contain at least three character classes")
    common = {"admin@12345", "password", "password123", "qwerty123", "letmein"}
    if value.lower() in common:
        raise ValueError("common/default passwords are forbidden")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    validate_password_strength(password)
    salt = salt or secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, expected = stored.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        digest = hashlib.scrypt(
            str(password).encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(_b64(digest), expected)
    except (ValueError, TypeError, MemoryError):
        return False


def apply_security_migration(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))


def create_organization(
    connection: sqlite3.Connection,
    *,
    name: str,
    organization_id: str | None = None,
    now: datetime | str | None = None,
) -> str:
    apply_security_migration(connection)
    clean_name = str(name or "").strip()
    if len(clean_name) < 2:
        raise ValueError("organization name is required")
    organization_id = organization_id or str(uuid.uuid4())
    connection.execute(
        "INSERT INTO organizations_v1(organization_id,name,status,created_at) VALUES(?,?,'active',?)",
        (organization_id, clean_name, _iso(now)),
    )
    connection.commit()
    return organization_id


def create_user(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    username: str,
    password: str,
    role: str,
    now: datetime | str | None = None,
) -> str:
    """Create a user only from an explicit strong password; no fallback exists."""
    apply_security_migration(connection)
    normalized_username = _normalize_username(username)
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in ROLES:
        raise ValueError(f"unsupported role: {role}")
    password_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    timestamp = _iso(now)
    connection.execute(
        """INSERT INTO users_v1(
            user_id,organization_id,username,password_hash,role,active,created_at,password_changed_at
        ) VALUES(?,?,?,?,?,1,?,?)""",
        (
            user_id,
            organization_id,
            normalized_username,
            password_hash,
            normalized_role,
            timestamp,
            timestamp,
        ),
    )
    connection.commit()
    return user_id


def authenticate_user(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    username: str,
    password: str,
) -> dict[str, Any] | None:
    connection.row_factory = sqlite3.Row
    try:
        normalized_username = _normalize_username(username)
    except ValueError:
        return None
    row = connection.execute(
        """SELECT user_id,organization_id,username,password_hash,role,active
           FROM users_v1 WHERE organization_id=? AND username=?""",
        (organization_id, normalized_username),
    ).fetchone()
    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        return None
    result = dict(row)
    result.pop("password_hash", None)
    return result


@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    expires_at: str


def create_session(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    ttl_seconds: int = 12 * 60 * 60,
    client_fingerprint: str = "",
    now: datetime | str | None = None,
) -> SessionTokens:
    if ttl_seconds < 60 or ttl_seconds > 7 * 24 * 60 * 60:
        raise ValueError("session TTL must be between 60 seconds and 7 days")
    apply_security_migration(connection)
    connection.row_factory = sqlite3.Row
    user = connection.execute(
        "SELECT user_id,organization_id,active FROM users_v1 WHERE user_id=?", (user_id,)
    ).fetchone()
    if not user or not user["active"]:
        raise PermissionError("active user is required")
    created = _utc(now)
    expires = created + timedelta(seconds=ttl_seconds)
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    connection.execute(
        """INSERT INTO sessions_v1(
            session_hash,user_id,organization_id,csrf_hash,created_at,expires_at,
            last_seen_at,revoked_at,client_fingerprint_hash
        ) VALUES(?,?,?,?,?,?,?,NULL,?)""",
        (
            _sha256(session_token),
            user_id,
            user["organization_id"],
            _sha256(csrf_token),
            created.isoformat(),
            expires.isoformat(),
            created.isoformat(),
            _sha256(client_fingerprint) if client_fingerprint else "",
        ),
    )
    connection.commit()
    return SessionTokens(session_token=session_token, csrf_token=csrf_token, expires_at=expires.isoformat())


def validate_session(
    connection: sqlite3.Connection,
    session_token: str,
    *,
    organization_id: str | None = None,
    client_fingerprint: str = "",
    now: datetime | str | None = None,
    touch: bool = False,
) -> dict[str, Any] | None:
    if not session_token:
        return None
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """SELECT s.session_hash,s.user_id,s.organization_id,s.csrf_hash,s.expires_at,
                  s.revoked_at,s.client_fingerprint_hash,u.username,u.role,u.active
           FROM sessions_v1 s JOIN users_v1 u ON u.user_id=s.user_id
           WHERE s.session_hash=?""",
        (_sha256(session_token),),
    ).fetchone()
    if not row or row["revoked_at"] or not row["active"]:
        return None
    if _utc(row["expires_at"]) <= _utc(now):
        return None
    if organization_id and row["organization_id"] != organization_id:
        return None
    expected_fingerprint = row["client_fingerprint_hash"]
    if expected_fingerprint and not hmac.compare_digest(
        expected_fingerprint, _sha256(client_fingerprint)
    ):
        return None
    result = dict(row)
    result.pop("csrf_hash", None)
    result.pop("session_hash", None)
    result.pop("client_fingerprint_hash", None)
    if touch:
        connection.execute(
            "UPDATE sessions_v1 SET last_seen_at=? WHERE session_hash=?",
            (_iso(now), _sha256(session_token)),
        )
        connection.commit()
    return result


def verify_csrf(connection: sqlite3.Connection, session_token: str, csrf_token: str) -> bool:
    if not session_token or not csrf_token:
        return False
    row = connection.execute(
        "SELECT csrf_hash,revoked_at,expires_at FROM sessions_v1 WHERE session_hash=?",
        (_sha256(session_token),),
    ).fetchone()
    if not row or row[1] or _utc(row[2]) <= _utc():
        return False
    return hmac.compare_digest(str(row[0]), _sha256(csrf_token))


def authorize(session: Mapping[str, Any] | None, allowed_roles: Iterable[str], *, organization_id: str) -> bool:
    if not session or session.get("organization_id") != organization_id:
        return False
    allowed = {str(role).lower() for role in allowed_roles}
    return str(session.get("role") or "").lower() in allowed


def revoke_session(
    connection: sqlite3.Connection,
    session_token: str,
    *,
    now: datetime | str | None = None,
) -> bool:
    before = connection.total_changes
    connection.execute(
        "UPDATE sessions_v1 SET revoked_at=? WHERE session_hash=? AND revoked_at IS NULL",
        (_iso(now), _sha256(session_token)),
    )
    changed = connection.total_changes > before
    connection.commit()
    return changed


def create_enrollment_token(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    ttl_seconds: int = 3600,
    max_uses: int = 1,
    label: str = "",
    now: datetime | str | None = None,
) -> str:
    if ttl_seconds < 60 or ttl_seconds > 30 * 24 * 60 * 60:
        raise ValueError("enrollment TTL must be between 60 seconds and 30 days")
    if max_uses < 1 or max_uses > 10000:
        raise ValueError("max_uses must be between 1 and 10000")
    apply_security_migration(connection)
    created = _utc(now)
    token = secrets.token_urlsafe(32)
    connection.execute(
        """INSERT INTO enrollment_tokens_v1(
            token_hash,organization_id,label,created_at,expires_at,max_uses,uses,revoked_at
        ) VALUES(?,?,?,?,?,?,0,NULL)""",
        (
            _sha256(token),
            organization_id,
            str(label or "").strip(),
            created.isoformat(),
            (created + timedelta(seconds=ttl_seconds)).isoformat(),
            max_uses,
        ),
    )
    connection.commit()
    return token


def consume_enrollment_token(
    connection: sqlite3.Connection,
    token: str,
    *,
    organization_id: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any] | None:
    if not token:
        return None
    apply_security_migration(connection)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM enrollment_tokens_v1 WHERE token_hash=?", (_sha256(token),)
        ).fetchone()
        if (
            not row
            or row["revoked_at"]
            or _utc(row["expires_at"]) <= _utc(now)
            or int(row["uses"]) >= int(row["max_uses"])
            or (organization_id and row["organization_id"] != organization_id)
        ):
            connection.rollback()
            return None
        connection.execute(
            "UPDATE enrollment_tokens_v1 SET uses=uses+1 WHERE token_hash=?",
            (_sha256(token),),
        )
        connection.commit()
        result = dict(row)
        result["uses"] = int(result["uses"]) + 1
        result.pop("token_hash", None)
        return result
    except Exception:
        connection.rollback()
        raise


def consume_rate_limit(
    connection: sqlite3.Connection,
    key: str,
    *,
    limit: int,
    window_seconds: int,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    if limit < 1 or window_seconds < 1:
        raise ValueError("positive limit and window_seconds are required")
    apply_security_migration(connection)
    anchor = _utc(now)
    epoch = int(anchor.timestamp())
    window_epoch = epoch - (epoch % window_seconds)
    window_start = datetime.fromtimestamp(window_epoch, tz=timezone.utc)
    expires = window_start + timedelta(seconds=window_seconds)
    key_hash = _sha256(str(key))
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT request_count FROM security_rate_limits_v1
               WHERE key_hash=? AND window_start=?""",
            (key_hash, window_start.isoformat()),
        ).fetchone()
        count = int(row[0]) if row else 0
        allowed = count < limit
        if allowed:
            connection.execute(
                """INSERT INTO security_rate_limits_v1(key_hash,window_start,request_count,expires_at)
                   VALUES(?,?,1,?)
                   ON CONFLICT(key_hash,window_start) DO UPDATE SET request_count=request_count+1""",
                (key_hash, window_start.isoformat(), expires.isoformat()),
            )
            count += 1
        connection.execute(
            "DELETE FROM security_rate_limits_v1 WHERE expires_at < ?", (anchor.isoformat(),)
        )
        connection.commit()
        return {
            "allowed": allowed,
            "limit": limit,
            "remaining": max(0, limit - count),
            "reset_at": expires.isoformat(),
        }
    except Exception:
        connection.rollback()
        raise


def append_audit_event(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    event_type: str,
    actor_user_id: str = "",
    subject_id: str = "",
    detail: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
) -> str:
    apply_security_migration(connection)
    created_at = _iso(now)
    detail_json = json.dumps(dict(detail or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    previous = connection.execute(
        "SELECT event_hash FROM security_audit_log_v1 ORDER BY sequence_id DESC LIMIT 1"
    ).fetchone()
    previous_hash = str(previous[0]) if previous else "GENESIS"
    canonical = json.dumps(
        {
            "organization_id": organization_id,
            "event_type": event_type,
            "actor_user_id": actor_user_id,
            "subject_id": subject_id,
            "created_at": created_at,
            "detail_json": detail_json,
            "previous_hash": previous_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    event_hash = _sha256(canonical)
    connection.execute(
        """INSERT INTO security_audit_log_v1(
            organization_id,event_type,actor_user_id,subject_id,created_at,
            detail_json,previous_hash,event_hash
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (
            organization_id,
            str(event_type or "").strip(),
            actor_user_id,
            subject_id,
            created_at,
            detail_json,
            previous_hash,
            event_hash,
        ),
    )
    connection.commit()
    return event_hash


def verify_audit_chain(connection: sqlite3.Connection) -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT * FROM security_audit_log_v1 ORDER BY sequence_id"
    ).fetchall()
    expected_previous = "GENESIS"
    for row in rows:
        if row["previous_hash"] != expected_previous:
            return {"ok": False, "sequence_id": row["sequence_id"], "reason": "previous_hash"}
        canonical = json.dumps(
            {
                "organization_id": row["organization_id"],
                "event_type": row["event_type"],
                "actor_user_id": row["actor_user_id"],
                "subject_id": row["subject_id"],
                "created_at": row["created_at"],
                "detail_json": row["detail_json"],
                "previous_hash": row["previous_hash"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        calculated = _sha256(canonical)
        if not hmac.compare_digest(calculated, row["event_hash"]):
            return {"ok": False, "sequence_id": row["sequence_id"], "reason": "event_hash"}
        expected_previous = row["event_hash"]
    return {"ok": True, "events": len(rows), "head_hash": expected_previous}
