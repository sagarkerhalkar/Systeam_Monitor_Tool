-- Commercial V1 migration 0001: permanent agent identity foundation
-- Additive only: no legacy client or history row is deleted or rewritten.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_installations (
    agent_install_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL DEFAULT 'default',
    canonical_client_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    current_hostname TEXT NOT NULL DEFAULT '',
    enrollment_status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_installations_canonical
ON agent_installations(canonical_client_id);

CREATE INDEX IF NOT EXISTS ix_agent_installations_last_seen
ON agent_installations(last_seen_at);

CREATE TABLE IF NOT EXISTS client_identity_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_client_id TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    alias_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(alias_type, alias_hash, canonical_client_id)
);

CREATE INDEX IF NOT EXISTS ix_client_identity_alias_lookup
ON client_identity_aliases(alias_type, alias_hash);

CREATE TABLE IF NOT EXISTS identity_quarantine (
    token_type TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    distinct_hostname_count INTEGER NOT NULL DEFAULT 0,
    first_detected_at TEXT NOT NULL,
    last_detected_at TEXT NOT NULL,
    PRIMARY KEY(token_type, token_hash)
);
