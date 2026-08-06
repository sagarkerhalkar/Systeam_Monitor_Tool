# Identity Shadow Mode

Identity shadow mode calculates the commercial canonical client view without changing the current `latest` or `heartbeats` tables and without changing dashboard responses.

## Purpose

Before permanent identity becomes the live key, shadow mode must prove that:

- 106 raw current rows resolve to 100 physical clients;
- the physical operating-system count is 62 Windows and 38 Linux/Ubuntu;
- the exact online boundary is `age < 600 seconds` and `age >= 600 seconds` is offline;
- cloned UUIDs and shared board serials do not merge unrelated machines;
- confirmed stale alias families merge conservatively;
- a permanent agent installation ID survives hostname changes;
- no heartbeat history is deleted.

## Read-only command

```bash
cd commercial
PYTHONPATH=. python tools/identity_shadow_audit.py \
  --db /path/to/monitor.db \
  --offline-seconds 600 \
  --expect-physical 100 \
  --output identity-shadow-report.json
```

The default command opens SQLite in read-only mode.

## Optional evidence persistence

`--persist-shadow` writes only to `identity_shadow_runs` and `identity_shadow_members`. It does not update or delete production client or history rows. This option should be used only against a backed-up staging copy until the migration and rollback procedure is approved.

## Promotion gate

Permanent identity must not replace the existing machine key until repeated shadow runs agree with verified physical inventory, collision quarantine is reviewed, Windows and Ubuntu agents both persist `agent_install_id`, and upgrade/rollback tests pass.
