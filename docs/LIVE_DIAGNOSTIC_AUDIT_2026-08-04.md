# Live Diagnostic Audit — 4 August 2026

Repository: `sagarkerhalkar/Systeam_Monitor_Tool`  
Source baseline: `workingcode` / V24.1.1  
Commercial branch: `commercial-v1`  
Evidence: read-only diagnostic collected from the live Windows server at 2026-08-04 17:48:59 IST.

## Executive result

The live database is structurally healthy and the server's basic HTTP endpoints are responsive. The remaining problems are primarily application design problems:

1. current client identity grouping can merge unrelated machines when a cloned UUID or shared board serial appears;
2. Day History rebuilds and rewrites its full V20.6 rollup whenever live heartbeats change;
3. the SQLite WAL is 627.66 MB and there is no controlled checkpoint/maintenance policy;
4. Notifications and Change Events grow without a clear retention policy;
5. Assets contains large amounts of old data that have not yet been populated into the new Department, Hostname and Price fields;
6. the current monolithic server/UI and insecure credential fields block commercial release.

No production data was changed during this audit.

## Verified live facts

### Server and database

- Windows 11 server, Python 3.14.3, port 2278.
- `server.py` compilation: passed.
- `public/app.js` syntax: passed.
- `/api/health`: HTTP 200 in 41.03 ms.
- `/api/auth/status`: HTTP 200 in 7.00 ms.
- main page: HTTP 200 in 2.53 ms.
- SQLite quick check: passed.
- main database size: 2,733.06 MB.
- WAL size: 627.66 MB.
- database rows:
  - Heartbeats: 101,088
  - Notifications: 65,034
  - Change Events: 24,068
  - Assets: 461
  - Software Inventory: 2

The simple read-only SQL counts were fast. Therefore the user's slow screens are not explained by basic SQLite count speed; they are caused mainly by application-side parsing, full rollup rebuilds, large payload processing and browser rerendering.

## Correct current client calculation

The raw `latest` table contains 106 rows:

- 67 Windows
- 38 Linux/Ubuntu
- 1 invalid unknown row

The diagnostic found three confirmed stale alias families. Confirmation required the same hostname plus multiple matching hardware identifiers:

- one family with 4 machine IDs: 3 stale aliases;
- one family with 2 machine IDs: 1 stale alias;
- one family with 2 machine IDs: 1 stale alias.

Correct physical-client calculation:

`106 raw - 1 invalid - 5 stale alias rows = 100 physical clients`

Physical operating-system count:

- Windows: 62
- Linux/Ubuntu: 38
- Total: 100

Current physical online/offline count using the exact requested boundary:

- Online (`age < 10 minutes`): 68
- Offline (`age >= 10 minutes`): 32

The Heartbeats table showing 52 machine IDs in the last ten minutes is not an online-count contradiction. The current source intentionally stores compact history samples rather than every heartbeat. Online/offline must use `latest.updated_at`, not recent Heartbeats rows.

## P0: identity grouping can merge unrelated clients

The V20.6 `_v206_group` algorithm unions clients when any identity token matches. This is unsafe when hardware values are cloned or vendor-generic.

The live diagnostic found collision-prone values, including:

- one system UUID shared by 57 different hostnames;
- another system UUID shared by 6 different hostnames;
- motherboard serial values shared across 5 and 6 different hostnames.

Some known placeholders are already blocked, but the code does not dynamically reject a value after it is proven collision-prone in the current organization. It also unions transitively on board serial alone.

Required repair:

- permanent agent installation ID becomes the primary key;
- never merge on hostname, IP or MAC alone;
- never merge on motherboard serial alone;
- quarantine hardware tokens seen with conflicting secondary hardware identities;
- require one unique high-confidence token or at least two agreeing independent tokens;
- keep an explicit alias-to-canonical mapping;
- do not delete Heartbeats history.

## P0: Day History full rebuild is the main live performance defect

The current heartbeat path updates `day_history_alias_state_v206` and then deletes the V20.6 signature:

`DELETE FROM day_history_meta_v206 WHERE key='signature'`

The next Day History request runs `_v206_prepare_history`, which:

- reads the complete alias-state table;
- rebuilds all identity groups;
- deletes all rows from `day_history_rollup_v206`;
- deletes all rows from `day_history_alias_v206`;
- reinserts the complete rollup and alias mapping.

Live evidence:

- V20.6 alias-state rows: 1,033 through 4 August.
- V20.6 rollup rows: 954 only through 3 August.
- V20.6 alias rows: 132.
- V20.6 metadata rows: 0 at diagnostic time.
- Thirteen old/current Day History tables remain from V20, V20.2, V20.4 and V20.6.

Because every heartbeat invalidates the signature, every Day History refresh can perform a full write rebuild. This explains slow Day History, write amplification and WAL growth.

Required repair:

- update only the affected `(day, canonical_client)` rollup row;
- keep rollup generation outside GET requests;
- use a background worker or heartbeat-side idempotent upsert;
- store a schema migration version;
- retain one canonical history schema after migration verification;
- add deterministic tests for counter restart, hostname change and alias merge.

## P0: WAL and database maintenance

Live WAL: 627.66 MB.

Required repair:

- configure `wal_autocheckpoint`;
- schedule safe `PRAGMA wal_checkpoint(PASSIVE)` maintenance;
- expose WAL/checkpoint health in diagnostics;
- perform `TRUNCATE` checkpoint only during a controlled maintenance window;
- never run `VACUUM` automatically while the live server is active;
- add retention and archival before any one-time database compaction.

## P1: unbounded operational tables

The database contains:

- 65,034 Notifications in about fourteen days;
- 24,068 Change Events in about fourteen days;
- 101,088 Heartbeats.

Notifications currently have no indexes in the live schema. Heartbeats have multiple duplicate indexes created by prior patches.

Required repair:

- notification indexes on `created_at`, `machine_id`, and `rule_id`;
- configurable retention for notifications, changes and raw history;
- daily aggregate retained longer than raw events;
- remove redundant indexes only through a migration after query-plan verification;
- alert deduplication must use canonical physical client identity.

## Client Messages

Current evidence is internally consistent:

- 5 targeted messages;
- all 5 marked delivered;
- no delivered message without a receipt;
- no pending message with a receipt.

However, the current server marks a message delivered when it is returned in a heartbeat response. A commercial system needs separate states:

- Queued
- Dispatched
- Displayed/Acknowledged
- Failed
- Expired

The existing delivery-once protection should remain, but a client acknowledgement endpoint is required.

## Assets Inventory

Live rows: 461.

Data quality:

- Tagname populated: 461.
- Hostname missing: 431.
- Department missing: 431.
- Base/GST/Total price missing: 431.
- Serial number missing: 284.
- Warranty Active: 67.
- Warranty Expired: 20.
- Warranty Unknown: 373.
- Audited/Verified: 89.
- Audit blank: 372.
- Live asset links: 5; no orphan links.

Duplicate groups from the requested rules:

- Tagname duplicate groups: 152, covering 376 rows.
- Serial duplicate groups: 24, covering 62 rows.
- Largest Tagname group: 24 rows.
- Largest Serial group: 10 rows.

The duplicate screen is exposing a real data-quality problem; it is not only a UI bug. Do not auto-delete or auto-merge. Add a review workflow that lets an admin correct generic/reused Tagnames and serial placeholders.

Price validation:

- no negative Base Price;
- no invalid GST percent;
- no Total Price formula mismatch.

Only 30 Assets currently contain the new Hostname/Department/Price data. Existing rows must remain blank until an authorized import or edit populates them.

## Software Inventory

- 2 rows.
- both Active.
- both Audited/Verified.
- Base Price, GST and Total Price are populated.
- no price formula mismatch.
- no duplicate groups.

Commercial blocker: the schema still contains `password_value`, `license_key` and `mfa_recovery` as ordinary fields. Credentials must not be stored or exported as plaintext.

## Security and commercial blockers

Before sale:

- remove default administrator password fallback;
- stop printing password information at startup;
- replace plaintext Software credential storage;
- add durable server-side sessions and revocation;
- add CSRF protection and request limits;
- use a production HTTP application server behind HTTPS;
- add organization isolation, enrollment keys and licensing;
- create versioned database migrations;
- pin and hash dependencies;
- add Windows and Ubuntu Server packages;
- add Windows and Ubuntu Agent packages;
- digitally sign installers and update packages;
- add automated install, upgrade, rollback, API, identity, history and load tests.

## Approved implementation order for `commercial-v1`

1. Identity v1: permanent agent ID and collision-aware canonicalization.
2. History v1: incremental rollup, no writes in GET routes.
3. Database maintenance: WAL checkpoint, retention and migration framework.
4. Security foundation: credentials, sessions, CSRF, HTTPS assumptions.
5. API/UI modularization and server-side pagination.
6. Windows Agent service and MSI.
7. Ubuntu Agent systemd service and DEB.
8. Windows Server installer.
9. Ubuntu Server DEB.
10. Pilot and load testing.

## Safety decision

`workingcode` remains the internal-use branch.  
All commercial engineering starts in `commercial-v1`.  
No production source or database migration should be deployed until the first three P0 items have automated tests and rollback evidence.
