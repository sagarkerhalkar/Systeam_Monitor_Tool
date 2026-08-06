# Incremental History V1

The commercial history engine updates one `(organization, canonical client, local day)` rollup at a time. Dashboard GET requests only read rollups and never rebuild or rewrite history.

## Guarantees

- duplicate event IDs are idempotent;
- counter growth is accumulated once;
- counter restart/reset begins a new counter segment;
- late events recalculate only the affected client/day;
- hostname changes remain under the canonical client ID;
- alias merges retain raw samples and rebuild only affected days;
- local-day boundaries use an explicit IANA timezone;
- raw samples and alias-merge audit evidence are retained;
- migration is additive and repeatable.

## Data flow

```text
heartbeat/worker
  -> canonical identity
  -> HistoryEvent
  -> INSERT OR IGNORE one sample
  -> rebuild/upsert one client-day rollup

GET history/report
  -> SELECT rollup rows only
```

## Production promotion gate

Before integrating into the live heartbeat path:

1. backfill a staging database one day at a time;
2. compare rollups against verified client counter samples;
3. run concurrency, WAL and load tests;
4. prove backup and rollback;
5. keep the existing history tables read-only during shadow comparison;
6. switch report reads only after parity evidence passes.
