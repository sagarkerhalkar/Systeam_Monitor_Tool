-- Commercial V1 migration 0007: authenticated agent enrollment and heartbeat state.
-- Raw agent tokens are never stored.

CREATE TABLE IF NOT EXISTS agent_credentials_v1 (
    agent_install_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    canonical_client_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 1,
    platform TEXT NOT NULL,
    current_hostname TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    rotated_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(organization_id, canonical_client_id),
    FOREIGN KEY(organization_id) REFERENCES organizations_v1(organization_id)
);

CREATE INDEX IF NOT EXISTS ix_agent_credentials_v1_org_status
ON agent_credentials_v1(organization_id, status, last_seen_at);

CREATE TABLE IF NOT EXISTS agent_heartbeat_events_v1 (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL UNIQUE,
    client_event_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    canonical_client_id TEXT NOT NULL,
    agent_install_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    hostname TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(agent_install_id, client_event_id),
    FOREIGN KEY(agent_install_id) REFERENCES agent_credentials_v1(agent_install_id)
);

CREATE INDEX IF NOT EXISTS ix_agent_heartbeat_events_v1_client_time
ON agent_heartbeat_events_v1(
    organization_id, canonical_client_id, received_at, sequence_id
);

CREATE TABLE IF NOT EXISTS agent_current_v1 (
    organization_id TEXT NOT NULL,
    canonical_client_id TEXT NOT NULL,
    agent_install_id TEXT NOT NULL,
    hostname TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(organization_id, canonical_client_id),
    UNIQUE(agent_install_id),
    FOREIGN KEY(agent_install_id) REFERENCES agent_credentials_v1(agent_install_id)
);

CREATE INDEX IF NOT EXISTS ix_agent_current_v1_org_updated
ON agent_current_v1(organization_id, updated_at, canonical_client_id);

CREATE TABLE IF NOT EXISTS agent_token_rotation_events_v1 (
    rotation_id TEXT PRIMARY KEY,
    agent_install_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    old_version INTEGER NOT NULL,
    new_version INTEGER NOT NULL,
    rotated_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(agent_install_id) REFERENCES agent_credentials_v1(agent_install_id)
);
