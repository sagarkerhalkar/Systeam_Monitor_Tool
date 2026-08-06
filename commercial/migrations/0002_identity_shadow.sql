-- Commercial V1 migration 0002: read-only identity shadow evidence.
-- This migration does not update or delete latest/heartbeats rows.

CREATE TABLE IF NOT EXISTS identity_shadow_runs (
    run_id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    source_db_path TEXT NOT NULL DEFAULT '',
    raw_rows INTEGER NOT NULL,
    excluded_rows INTEGER NOT NULL,
    physical_clients INTEGER NOT NULL,
    online_clients INTEGER NOT NULL,
    offline_clients INTEGER NOT NULL,
    windows_clients INTEGER NOT NULL,
    linux_clients INTEGER NOT NULL,
    report_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_identity_shadow_runs_generated
ON identity_shadow_runs(generated_at);

CREATE TABLE IF NOT EXISTS identity_shadow_members (
    run_id TEXT NOT NULL,
    row_id TEXT NOT NULL,
    canonical_client_id TEXT NOT NULL,
    source TEXT NOT NULL,
    hostname TEXT NOT NULL DEFAULT '',
    os_family TEXT NOT NULL DEFAULT 'unknown',
    updated_at TEXT NOT NULL DEFAULT '',
    online INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(run_id, row_id),
    FOREIGN KEY(run_id) REFERENCES identity_shadow_runs(run_id)
);

CREATE INDEX IF NOT EXISTS ix_identity_shadow_members_canonical
ON identity_shadow_members(canonical_client_id);
