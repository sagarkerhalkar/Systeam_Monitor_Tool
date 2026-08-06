-- Commercial V1 migration 0003: incremental per-client, per-day history.
-- No current client or heartbeat history row is removed.

CREATE TABLE IF NOT EXISTS history_samples_v1 (
    event_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL DEFAULT 'default',
    canonical_client_id TEXT NOT NULL,
    local_day TEXT NOT NULL,
    event_at TEXT NOT NULL,
    timezone_name TEXT NOT NULL,
    hostname TEXT NOT NULL DEFAULT '',
    download_counter_bytes INTEGER NOT NULL DEFAULT 0,
    upload_counter_bytes INTEGER NOT NULL DEFAULT 0,
    current_download_mbps REAL,
    current_upload_mbps REAL,
    cpu_percent REAL,
    ram_percent REAL,
    payload_hash TEXT NOT NULL DEFAULT '',
    inserted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_history_samples_client_day_time
ON history_samples_v1(organization_id, canonical_client_id, local_day, event_at, event_id);

CREATE TABLE IF NOT EXISTS history_daily_rollup_v1 (
    organization_id TEXT NOT NULL DEFAULT 'default',
    canonical_client_id TEXT NOT NULL,
    local_day TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    hostname_last TEXT NOT NULL DEFAULT '',
    sample_count INTEGER NOT NULL DEFAULT 0,
    download_bytes INTEGER NOT NULL DEFAULT 0,
    upload_bytes INTEGER NOT NULL DEFAULT 0,
    download_counter_resets INTEGER NOT NULL DEFAULT 0,
    upload_counter_resets INTEGER NOT NULL DEFAULT 0,
    online_seconds INTEGER NOT NULL DEFAULT 0,
    peak_download_mbps REAL,
    peak_upload_mbps REAL,
    avg_cpu_percent REAL,
    peak_cpu_percent REAL,
    avg_ram_percent REAL,
    peak_ram_percent REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(organization_id, canonical_client_id, local_day)
);

CREATE INDEX IF NOT EXISTS ix_history_daily_rollup_day
ON history_daily_rollup_v1(organization_id, local_day, canonical_client_id);

CREATE TABLE IF NOT EXISTS history_alias_merge_audit_v1 (
    merge_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL DEFAULT 'default',
    source_canonical_client_id TEXT NOT NULL,
    target_canonical_client_id TEXT NOT NULL,
    affected_days_json TEXT NOT NULL,
    merged_at TEXT NOT NULL
);
