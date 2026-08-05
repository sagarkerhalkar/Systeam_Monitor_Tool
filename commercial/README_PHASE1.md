# Commercial V1 — Phase 1 Identity Foundation

This package is intentionally **not connected to the live production routes yet**.

It adds:

- permanent `agent_install_id` model;
- conservative legacy resolver;
- collision quarantine for identifiers shared across different hostnames;
- additive/idempotent SQLite migration;
- a production-shaped 106-row automated test;
- automated proof that 106 raw rows resolve to 100 physical clients.

No production database row is deleted or rewritten.

## Test command

```bash
cd commercial
PYTHONPATH=. python -m unittest discover -s tests -v
```
