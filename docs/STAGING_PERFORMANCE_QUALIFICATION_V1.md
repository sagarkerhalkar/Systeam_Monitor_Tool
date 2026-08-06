# Commercial Staging and Performance Qualification V1

This phase qualifies the isolated commercial server and agent protocol. It does not deploy or modify `workingcode`, the live server, the current dashboard, current production agents, or production data.

## Automated qualification gates

### Agent-scale scenarios

The dedicated GitHub Actions workflow runs fresh-database scenarios for:

- 100 agents
- 500 agents
- 1,000 agents

Each scenario uses the real commercial API and SQLite schema. Windows and Ubuntu agents are alternated. The scenario performs:

1. First-run organization and administrator bootstrap.
2. WAL configuration and passive checkpoint capture.
3. One-time enrollment-token generation.
4. Concurrent permanent-agent registration.
5. Two concurrent heartbeat rounds for every registered agent.
6. Duplicate heartbeat replay using the same event IDs.
7. Authenticated administrator login and concurrent `/api/v1/auth/me` reads.
8. Message creation, heartbeat claim, and acknowledged display receipts.
9. Complete API-object restart over the same database.
10. A post-restart authenticated heartbeat.
11. Verified online backup.
12. SHA-256, size, and SQLite integrity verification.
13. Restore into a separate database path.
14. Exact source-versus-restored row-count comparison.
15. Passive WAL checkpoint and WAL-size reporting.
16. Peak traced-memory and file-descriptor reporting.
17. Canonical JSON evidence with an evidence SHA-256.

### Sustained workload probe

A second job runs:

- 100 agents
- 30 heartbeat rounds per agent
- 50 duplicate heartbeat replays
- 25 message deliveries and acknowledgements
- 500 authenticated administrator reads

This is a CI resource-growth and repeated-write probe. It is not a substitute for an eight-hour or twenty-four-hour physical staging soak.

### Forced process recovery

The cross-platform unit matrix starts the actual commercial server process on a loopback port, then:

1. Waits for readiness.
2. Enrolls a permanent agent through HTTP.
3. Writes one authenticated heartbeat through HTTP.
4. Terminates the server process.
5. Starts a new server process over the same database.
6. Uses the original agent token to read authenticated status.
7. Verifies credential, current-state, heartbeat, and history row continuity.
8. Runs SQLite `quick_check`.

This test executes on Windows and Ubuntu with Python 3.12 and Python 3.14 through Commercial CI.

## Release thresholds

The full-scale workflow currently blocks on:

- Error rate: `0%`
- Registration p95: `<= 5,000 ms`
- Heartbeat p95: `<= 2,000 ms`
- Authenticated administrator-read p95: `<= 300 ms`
- WAL size after passive checkpoint: `<= 512 MiB`
- Peak traced Python memory: `<= 512 MiB`
- Duplicate heartbeat insertions: `0`
- WAL checkpoint busy result: `0`
- Source and restored database row counts: exact match
- Every target message claimed and acknowledged exactly once

These are staging qualification ceilings, not final customer-facing service-level objectives. Production targets may be stricter after physical-hardware baseline results are available.

## Evidence files

The workflow uploads evidence for 30 days:

- `qualification-100-agents.json`
- `qualification-500-agents.json`
- `qualification-1000-agents.json`
- `qualification-summary.json`
- repeated-workload evidence under the soak artifact

Every evidence document contains:

- Environment and Python version
- Scenario configuration
- Operation count and failure count
- Throughput
- Minimum, p50, p95, p99, and maximum latency
- Database and WAL sizes
- Checkpoint results
- Source and restored row counts
- Peak traced memory
- File-descriptor counts where supported
- Invariant results
- Threshold results
- Overall pass/fail
- Canonical SHA-256 evidence hash

## Local or staging execution

From the repository root:

```bash
export PYTHONPATH=commercial
python commercial/tools/run_staging_qualification.py \
  --agents 100,500,1000 \
  --concurrency 12 \
  --heartbeat-rounds 2 \
  --output-dir qualification-evidence
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "commercial"
python commercial/tools/run_staging_qualification.py `
  --agents 100,500,1000 `
  --concurrency 12 `
  --heartbeat-rounds 2 `
  --output-dir qualification-evidence
```

The command exits with code `2` when any invariant or threshold fails.

## What a green result proves

A green automated result proves that the tested commit can:

- Register the requested number of permanent agents.
- Process concurrent heartbeats without lost or duplicate history rows.
- Preserve hostname-independent identity.
- Keep duplicate event replay idempotent.
- Serve authenticated administrator reads within the configured ceiling.
- Claim and acknowledge targeted client messages.
- Restart without losing authenticated agent state.
- Create and verify a consistent backup.
- Restore the backup into a separate database with exact row-count parity.
- Complete a passive WAL checkpoint without a busy result.
- Build machine-readable, tamper-evident qualification evidence.

## Remaining physical staging requirements

Automated CI cannot honestly prove every hardware and operating-system behaviour. Production remains blocked until physical staging also completes:

1. Clean Windows Server installation using the commercial installer.
2. Clean Ubuntu Server installation using the commercial installer.
3. Upgrade from the previous commercial package on both operating systems.
4. Deliberately failed upgrade with automatic application, database, configuration, and TLS rollback.
5. Eight-hour and twenty-four-hour soak on representative hardware.
6. Forced power loss and reboot recovery.
7. Disk-full and low-disk behaviour.
8. Network interruption and queued-agent replay from real Windows and Ubuntu clients.
9. Restore onto separate physical or virtual hardware.
10. Certificate renewal and invalid-certificate rejection.
11. Antivirus and endpoint-protection compatibility.
12. Pilot deployment before production promotion.

No automated green run authorizes direct replacement of the current live system.
