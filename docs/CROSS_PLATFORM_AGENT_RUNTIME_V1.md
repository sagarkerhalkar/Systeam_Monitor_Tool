# Cross-Platform Commercial Agent Runtime V1

## Scope

This phase adds a real shared Windows and Ubuntu agent runtime for the commercial API. It is additive and does not replace the current production agents or `workingcode` branch.

This is a **pilot installer phase**, not the final signed MSI or DEB release.

## Runtime guarantees

- One permanent UUID `agent_install_id` survives hostname changes, restarts and upgrades.
- The one-time enrollment token is kept in a separate protected file and removed after successful registration.
- The long-lived agent token is stored only in the restricted local credential file and is never written to SQLite, logs, configuration or command lines.
- HTTPS is mandatory. Plain HTTP is accepted only for explicitly enabled loopback development.
- Heartbeats have stable client event IDs and are stored in a durable SQLite queue before transmission.
- Network errors and reboots do not lose pending heartbeats.
- Server idempotency protects duplicate retries.
- OS cumulative network counters are converted to persistent local-day counters before transmission, preventing boot-time totals from corrupting Day History.
- Counter resets after a reboot are handled as a new local segment.
- Message dispatches are staged in a durable local inbox.
- A server acknowledgement is created only after the interactive notifier successfully submits the notification to the operating system.
- Failed or headless notification attempts remain unacknowledged.
- Renewed server leases update the dispatch token without showing the same popup twice.
- Token rotation is atomic and survives restart.
- Queue sizes are bounded and old overflow events are recorded in local audit events.

## Windows pilot

Files are under `commercial/agents/windows`.

The elevated installer:

1. validates Python 3.12 or newer;
2. builds a staged virtual environment from the hash-locked dependency file;
3. writes the application into a new staging directory;
4. preserves the prior application as `.rollback`;
5. keeps mutable state under `%ProgramData%`;
6. protects state with SYSTEM and Administrators ACLs;
7. creates a startup SYSTEM task for the agent;
8. creates an at-logon SYSTEM notifier task;
9. uses `msg.exe /TIME:120` for interactive two-minute messages;
10. restores the previous application if installation fails.

Example:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\commercial\agents\windows\install-commercial-agent.ps1 `
  -ServerUrl "https://monitor.example.com" `
  -EnrollmentTokenFile "C:\Secure\agent-enrollment.txt"
```

Uninstall while preserving identity and queue:

```powershell
.\commercial\agents\windows\uninstall-commercial-agent.ps1
```

Use `-RemoveState` only for intentional permanent de-registration.

## Ubuntu pilot

Files are under `commercial/agents/ubuntu`.

The root installer:

1. validates Python 3.12 or newer and `notify-send`;
2. creates dedicated system and notifier groups;
3. builds a staged virtual environment from the hash-locked dependency file;
4. keeps the previous application in `/opt/sagar-monitor-agent.rollback`;
5. keeps mutable state in `/var/lib/sagar-monitor-agent`;
6. protects credentials as owner-only;
7. shares only the message inbox with the selected desktop notifier user;
8. installs a hardened systemd service;
9. installs an XDG desktop autostart notifier;
10. performs registration and one heartbeat as the final service user before promotion;
11. restores the previous application and configuration on failure.

Example:

```bash
sudo ./commercial/agents/ubuntu/install-commercial-agent.sh \
  --server-url https://monitor.example.com \
  --enrollment-token-file /root/agent-enrollment.txt \
  --notifier-user sagar
```

The notifier user must sign out and sign in once when group membership is newly added.

Uninstall while preserving identity and queue:

```bash
sudo ./commercial/agents/ubuntu/uninstall-commercial-agent.sh
```

Use `--remove-state` only for intentional permanent de-registration.

## CLI

The shared launcher is `commercial/tools/run_edge_agent.py`.

Commands:

- `once`: collect and flush one cycle;
- `service`: continuous system-agent loop;
- `notifier`: interactive message notifier loop;
- `status`: authenticated server status;
- `rotate-token`: rotate and atomically replace the local agent token.

## CI and promotion gates

The branch must pass:

- Python 3.12 and 3.14 on Windows and Ubuntu;
- the full accumulated commercial test suite;
- PowerShell parser validation for all Windows pilot scripts;
- Bash syntax validation for all Ubuntu pilot scripts;
- dashboard JavaScript syntax;
- existing Final V2 CI;
- commercial release-foundation verification.

Production promotion remains blocked until:

- pilot installation is tested on real Windows 11 and Ubuntu clients;
- desktop notifications are verified in active and locked sessions;
- sleep, reboot, network loss and server outage tests pass;
- 100/500/1000-agent load simulation passes;
- signed MSI and DEB packages are built;
- upgrade, repair, uninstall and rollback evidence is recorded;
- staged server HTTPS deployment and backup/restore are proven.
