# Client Message Delivery V1

A message is not considered delivered when it is merely included in a heartbeat response. Commercial delivery uses an explicit state machine and a client acknowledgement receipt.

## States

```text
QUEUED -> DISPATCHED -> ACKNOWLEDGED
   |          |
   |          -> FAILED -> DISPATCHED (retry)
   -> EXPIRED
```

`ACKNOWLEDGED` means the client submitted a valid receipt after displaying or accepting the message. `FAILED` remains retryable until `max_attempts`; `EXPIRED` and `ACKNOWLEDGED` are terminal.

## Guarantees

- one delivery row per logical message and canonical client;
- organization and client scope enforced on claim, failure and acknowledgement;
- raw dispatch tokens are returned once and only token hashes are stored;
- acknowledgement requires a valid active dispatch lease;
- client receipt IDs are idempotent;
- unacknowledged leases retry the same delivery ID so the client can deduplicate locally;
- bounded attempts, retry backoff and TTL expiry;
- append-only transition events;
- aggregate status reporting performs no writes.

## Agent integration rule

Windows and Ubuntu agents must persist processed delivery IDs locally. After the popup is displayed, the agent sends `delivery_id`, `dispatch_token` and a unique `client_receipt_id` to the acknowledgement endpoint. A repeated dispatch with the same delivery ID must not display twice, but it may resend the acknowledgement safely.

## Production promotion gate

- API-level queue, claim, acknowledge, failure, expiry and authorization tests;
- Windows popup and Ubuntu notification integration tests;
- network interruption/retry tests;
- service restart and local receipt-cache tests;
- proof that one acknowledged delivery is never reissued;
- load test with concurrent client claims.
