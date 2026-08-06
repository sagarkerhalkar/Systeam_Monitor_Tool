-- Commercial V1 migration 0006: acknowledged client-message delivery lifecycle.

CREATE TABLE IF NOT EXISTS client_messages_v1 (
    message_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    created_by_user_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    created_at TEXT NOT NULL,
    not_before TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_client_messages_v1_org_created
ON client_messages_v1(organization_id, created_at, message_id);

CREATE TABLE IF NOT EXISTS client_message_deliveries_v1 (
    delivery_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    canonical_client_id TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    queued_at TEXT NOT NULL,
    next_attempt_at TEXT NOT NULL,
    dispatched_at TEXT,
    lease_expires_at TEXT,
    acknowledged_at TEXT,
    failed_at TEXT,
    expired_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    dispatch_token_hash TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 0,
    UNIQUE(message_id, canonical_client_id),
    FOREIGN KEY(message_id) REFERENCES client_messages_v1(message_id)
);

CREATE INDEX IF NOT EXISTS ix_client_message_deliveries_v1_claim
ON client_message_deliveries_v1(
    organization_id, canonical_client_id, state, next_attempt_at, lease_expires_at
);

CREATE INDEX IF NOT EXISTS ix_client_message_deliveries_v1_message
ON client_message_deliveries_v1(message_id, state);

CREATE TABLE IF NOT EXISTS client_message_receipts_v1 (
    receipt_id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    canonical_client_id TEXT NOT NULL,
    client_receipt_id TEXT NOT NULL,
    acknowledged_at TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(delivery_id, client_receipt_id),
    FOREIGN KEY(delivery_id) REFERENCES client_message_deliveries_v1(delivery_id)
);

CREATE INDEX IF NOT EXISTS ix_client_message_receipts_v1_delivery
ON client_message_receipts_v1(delivery_id, acknowledged_at);

CREATE TABLE IF NOT EXISTS client_message_delivery_events_v1 (
    event_id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    from_state TEXT NOT NULL DEFAULT '',
    to_state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(delivery_id) REFERENCES client_message_deliveries_v1(delivery_id)
);

CREATE INDEX IF NOT EXISTS ix_client_message_delivery_events_v1_delivery
ON client_message_delivery_events_v1(delivery_id, created_at, event_id);
