# Authenticated Agent and Heartbeat V1

The commercial agent protocol separates enrollment, permanent installation identity, credentials, heartbeat events, current state, daily history and message acknowledgement. The existing live agent/server protocol is not changed by this phase.

## Enrollment

1. An administrator creates an organization-scoped, expiring and usage-limited enrollment token.
2. The agent creates and persists a UUID `agent_install_id` locally.
3. `POST /api/v1/agents/register` consumes one enrollment use atomically.
4. The server returns an opaque `agent_token` once and stores only its SHA-256 hash.
5. The server creates a stable canonical client ID from the permanent agent installation ID.

A failed credential insert rolls back the enrollment-token use. Reusing an exhausted, expired or revoked enrollment token is rejected.

## Authentication

Agent requests send:

```text
Authorization: Agent <opaque-agent-token>
X-Agent-ID: <permanent-agent-install-id>
```

TLS is mandatory outside local testing. Credentials can be disabled and rotated. Token rotation returns a new raw token once, stores only its hash and invalidates the old token immediately.

## Heartbeat processing

`POST /api/v1/agents/heartbeat` accepts a bounded JSON object containing a client-generated event ID and payload.

The server:

- resolves organization and canonical client from the authenticated credential;
- ignores client attempts to choose another organization/client identity;
- derives an event key from agent ID plus client event ID;
- inserts the heartbeat idempotently;
- updates one current-state row only for a new event;
- updates exactly one canonical-client/local-day history rollup;
- handles hostname changes without creating a new physical client;
- leases pending messages for that canonical client;
- returns dispatch tokens that must be acknowledged separately.

A repeated event ID never double-counts heartbeat or history data.

## Message acknowledgement

After display, the client calls:

```text
POST /api/v1/agents/messages/{delivery_id}/ack
```

with the dispatch token and a locally persistent receipt ID. Organization and canonical-client scope are taken from the agent credential. An agent cannot acknowledge another client’s or organization’s delivery.

## Implemented routes

- `POST /api/v1/agents/register`
- `POST /api/v1/agents/heartbeat`
- `GET /api/v1/agents/status`
- `POST /api/v1/agents/token/rotate`
- `POST /api/v1/agents/messages/{delivery_id}/ack`

## Production promotion gate

Before live agent rollout:

- update Windows and Ubuntu agents to persist installation ID and token safely;
- add local event/receipt queues that survive restart and network loss;
- package secure credential-file permissions;
- test registration, rotation, disablement, duplicate events and message acknowledgement on real operating systems;
- load test concurrent heartbeat writes and WAL checkpointing;
- prove upgrade and rollback from the current agent;
- deploy to a small pilot group before organization-wide rollout.
