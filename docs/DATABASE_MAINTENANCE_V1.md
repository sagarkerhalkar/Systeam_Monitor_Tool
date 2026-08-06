# Database Maintenance V1

The commercial maintenance layer provides explicit, audited controls for SQLite WAL health and retention. It does not run `VACUUM` automatically and it does not prune data without backup and archive evidence.

## WAL policy

- set a bounded `wal_autocheckpoint` value;
- use `PRAGMA wal_checkpoint(PASSIVE)` for routine non-blocking maintenance;
- expose database, WAL, SHM, page, freelist and quick-check health;
- allow `TRUNCATE` checkpoint only with an explicit maintenance-window confirmation;
- never run a checkpoint inside an active application transaction.

## Retention policy

Retention supports an allowlisted set of operational tables and their trusted timestamp columns. Planning is read-only. Execution requires:

1. a verified backup;
2. an archive path when archive is required;
3. bounded batches;
4. durable archive commit;
5. per-row archive hash verification;
6. source deletion only after verification;
7. a maintenance run audit record.

If a process stops after archival but before deletion, rerunning is safe because archive rows are deduplicated by their source-row hash.

## Production promotion gate

- test on a restored staging copy of the live database;
- prove passive checkpoint under active heartbeat load;
- define approved retention periods;
- verify archive restore;
- schedule TRUNCATE checkpoint only in a controlled window;
- perform any one-time compaction offline after retention and backup verification.
