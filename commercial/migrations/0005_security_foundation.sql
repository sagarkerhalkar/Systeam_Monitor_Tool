-- Commercial V1 migration 0005: organization-scoped security foundation.
-- No default credential is created by this migration.

CREATE TABLE IF NOT EXISTS organizations_v1 (
    organization_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users_v1 (
    user_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    password_changed_at TEXT NOT NULL,
    UNIQUE(organization_id, username),
    FOREIGN KEY(organization_id) REFERENCES organizations_v1(organization_id)
);

CREATE INDEX IF NOT EXISTS ix_users_v1_org_role
ON users_v1(organization_id, role, active);

CREATE TABLE IF NOT EXISTS sessions_v1 (
    session_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    csrf_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    client_fingerprint_hash TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users_v1(user_id),
    FOREIGN KEY(organization_id) REFERENCES organizations_v1(organization_id)
);

CREATE INDEX IF NOT EXISTS ix_sessions_v1_user_expiry
ON sessions_v1(user_id, expires_at, revoked_at);

CREATE TABLE IF NOT EXISTS enrollment_tokens_v1 (
    token_hash TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    max_uses INTEGER NOT NULL DEFAULT 1,
    uses INTEGER NOT NULL DEFAULT 0,
    revoked_at TEXT,
    FOREIGN KEY(organization_id) REFERENCES organizations_v1(organization_id)
);

CREATE INDEX IF NOT EXISTS ix_enrollment_tokens_v1_org_expiry
ON enrollment_tokens_v1(organization_id, expires_at, revoked_at);

CREATE TABLE IF NOT EXISTS security_rate_limits_v1 (
    key_hash TEXT NOT NULL,
    window_start TEXT NOT NULL,
    request_count INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(key_hash, window_start)
);

CREATE INDEX IF NOT EXISTS ix_security_rate_limits_v1_expiry
ON security_rate_limits_v1(expires_at);

CREATE TABLE IF NOT EXISTS security_audit_log_v1 (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_user_id TEXT NOT NULL DEFAULT '',
    subject_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS ix_security_audit_log_v1_org_time
ON security_audit_log_v1(organization_id, created_at, sequence_id);

CREATE TABLE IF NOT EXISTS secret_references_v1 (
    reference_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    rotated_at TEXT,
    UNIQUE(organization_id, provider, external_key),
    FOREIGN KEY(organization_id) REFERENCES organizations_v1(organization_id)
);
