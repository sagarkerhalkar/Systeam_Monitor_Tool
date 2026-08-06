-- Commercial V1 migration 0004: database maintenance policy and audit evidence.
-- This migration does not prune, compact or rewrite operational data.

CREATE TABLE IF NOT EXISTS database_maintenance_policy_v1 (
    table_name TEXT PRIMARY KEY,
    timestamp_column TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    archive_required INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS database_maintenance_runs_v1 (
    run_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    table_name TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    cutoff_at TEXT,
    planned_rows INTEGER NOT NULL DEFAULT 0,
    archived_rows INTEGER NOT NULL DEFAULT 0,
    pruned_rows INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_database_maintenance_runs_started
ON database_maintenance_runs_v1(started_at);
