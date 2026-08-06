# Sagar Monitor Commercial Physical Staging Certification V1

## Purpose

This runbook certifies a commercial release candidate on real Windows and Ubuntu hardware. Automated GitHub tests do not replace these steps. Production deployment remains blocked until one evidence ledger contains every required step as PASS and a second person finalizes it.

## Safety boundary

- Use a dedicated staging server and representative staging clients.
- Do not point certification agents at the live `workingcode` server.
- Do not use the live production database.
- Keep the release-candidate ZIP and its SHA-256 unchanged through the complete test.
- Store the evidence ledger and attachment directory on a protected admin share with daily backup.
- The original operator and final approver must be different people.

## Required machines

1. One clean Windows Server or Windows 11 staging server.
2. One clean Ubuntu Server 24.04 staging server.
3. At least two Windows staging clients.
4. At least two Ubuntu staging clients.
5. One separate restore machine with no existing Sagar Monitor database.
6. One admin workstation for the central evidence ledger.

The controlled pilot should use at least five representative clients and include both Windows and Ubuntu.

## Prepare the release candidate

Build and verify the deterministic package:

```text
python commercial/tools/build_commercial_server_package.py build --repository-root . --output Sagar-Monitor-Commercial-RC.zip --version rc1
python commercial/tools/build_commercial_server_package.py verify --package Sagar-Monitor-Commercial-RC.zip
```

Record the package SHA-256 in the evidence metadata and do not rebuild the ZIP during certification.

## Start the central evidence ledger

Windows:

```powershell
$env:PYTHONPATH = 'commercial'
python commercial/tools/run_physical_certification.py init `
  --evidence D:\SagarMonitorCertification\rc1-evidence.json `
  --release-candidate rc1 `
  --site 'Bhopal staging lab' `
  --operator 'Operator Name' `
  --metadata '{"package_sha256":"PASTE_SHA256","change_ticket":"RC-001"}'
```

Ubuntu:

```bash
export PYTHONPATH=commercial
python commercial/tools/run_physical_certification.py init \
  --evidence /srv/sagar-certification/rc1-evidence.json \
  --release-candidate rc1 \
  --site 'Bhopal staging lab' \
  --operator 'Operator Name' \
  --metadata '{"package_sha256":"PASTE_SHA256","change_ticket":"RC-001"}'
```

Print the fixed plan:

```text
python commercial/tools/run_physical_certification.py plan
```

## Record every physical machine

Run `snapshot` on every server and client before testing. Keep all snapshots in the same central ledger.

Windows:

```powershell
commercial\server\windows\run-physical-certification.ps1 snapshot `
  --evidence D:\SagarMonitorCertification\rc1-evidence.json `
  --platform windows `
  --operator 'Operator Name' `
  --path C:\ProgramData
```

Ubuntu:

```bash
commercial/server/ubuntu/run-physical-certification.sh snapshot \
  --evidence /srv/sagar-certification/rc1-evidence.json \
  --platform ubuntu \
  --operator 'Operator Name' \
  --path /var/lib
```

## Clean server installation

Install the commercial server using the release-candidate installer and a trusted staging TLS certificate. Capture the complete terminal output into a text file.

After installation, record the automated server probe and attach the installation log.

Windows example:

```powershell
commercial\server\windows\run-physical-certification.ps1 probe-server `
  --evidence D:\SagarMonitorCertification\rc1-evidence.json `
  --step-id windows_server_clean_install `
  --platform windows `
  --operator 'Operator Name' `
  --server-url https://staging-monitor.example.com:8443 `
  --ca-bundle D:\SagarMonitorCertification\staging-ca.pem `
  --database 'C:\ProgramData\SagarMonitorCommercialServer\data\commercial.db' `
  --service-name SagarMonitorCommercialServer `
  --disk-path C:\ProgramData `
  --attachment D:\SagarMonitorCertification\windows-install.log
```

Ubuntu example:

```bash
commercial/server/ubuntu/run-physical-certification.sh probe-server \
  --evidence /srv/sagar-certification/rc1-evidence.json \
  --step-id ubuntu_server_clean_install \
  --platform ubuntu \
  --operator 'Operator Name' \
  --server-url https://staging-monitor.example.com:8443 \
  --ca-bundle /srv/sagar-certification/staging-ca.pem \
  --database /var/lib/sagar-monitor-commercial-server/commercial.db \
  --service-name sagar-monitor-commercial-server.service \
  --disk-path /var/lib/sagar-monitor-commercial-server \
  --attachment /srv/sagar-certification/ubuntu-install.log
```

A passing probe requires:

- HTTPS live endpoint returns 200 and `ok=true`.
- HTTPS readiness endpoint returns 200 and `ok=true`.
- TLS chain and hostname validation pass.
- Certificate fingerprint and expiry are captured.
- Service or scheduled task is running.
- SQLite `quick_check` and `integrity_check` return `ok`.
- Minimum free disk threshold is met.

## Agent installation and enrollment

Install one Windows and one Ubuntu agent using single-use enrollment tokens. Capture:

- Installer output.
- Permanent agent ID before and after reboot.
- Server-side canonical client ID.
- Successful heartbeat time.
- Agent credential file permissions.
- Message display and acknowledgement evidence.

Record `windows_agent_clean_install` and `ubuntu_agent_clean_install` with those logs attached.

## Failed-upgrade rollback

For each server platform:

1. Create a verified pre-upgrade backup.
2. Record current application version, database hash, configuration hash and TLS certificate fingerprint.
3. Introduce a controlled invalid release condition, such as an invalid health endpoint or deliberately mismatched test certificate.
4. Run the upgrade installer.
5. Confirm the installer fails.
6. Confirm the prior application pointer is restored.
7. Confirm the prior database, configuration and TLS files are restored.
8. Confirm the old server starts and both health endpoints pass.
9. Confirm existing agent credentials still authenticate.

Record `windows_failed_upgrade_rollback` and `ubuntu_failed_upgrade_rollback` with before/after hashes and complete installer logs.

## Abrupt restart recovery

This is a physical test. Do not simulate only by stopping a process.

1. Generate active agent heartbeats and a queued client message.
2. Abruptly power off or hard-reset the staging server.
3. Restart the machine.
4. Confirm automatic server startup.
5. Confirm SQLite integrity.
6. Confirm the previously queued message remains available.
7. Confirm agents reconnect without re-enrollment.
8. Confirm no duplicate history rows are created.

Record the Windows and Ubuntu steps separately with timestamps, photographs or console logs, database checks and agent status output.

## Offline queue replay

For each agent platform:

1. Confirm the agent is online.
2. Disconnect network access for at least ten minutes.
3. Generate multiple local heartbeat samples while offline.
4. Restore network access.
5. Confirm oldest-first replay.
6. Confirm every event ID is inserted once.
7. Confirm no queue loss after reboot while still offline.
8. Send a client message and confirm acknowledgement occurs only after actual display.

Record `windows_offline_queue_replay` and `ubuntu_offline_queue_replay` with local queue status, server row counts and timestamps.

## Disk-pressure recovery

Use a disposable staging volume. Do not fill the production operating-system disk.

1. Reduce free space gradually while heartbeats continue.
2. Confirm warnings are generated before exhaustion.
3. Confirm the server returns controlled errors rather than corrupting the database.
4. Confirm no automatic destructive VACUUM or retention action runs.
5. Free disk space.
6. Run SQLite integrity checks.
7. Confirm normal heartbeat and message processing resumes.

Record `server_disk_pressure_recovery` with free-space measurements, logs and database checks.

## Separate-hardware restore

1. Copy a verified backup and its manifest to a different staging machine.
2. Install the same release candidate cleanly.
3. Stop the service.
4. Restore using the supported restore command.
5. Start the service.
6. Verify database integrity and exact key table counts.
7. Confirm existing administrator login and agent credentials work.
8. Confirm no source machine configuration or private key is silently copied unless explicitly intended.

Record `separate_hardware_restore` with source and target hashes, counts and restore logs.

## TLS renewal and rejection

For renewal:

1. Record the original certificate SHA-256 and expiry.
2. Install a new trusted certificate with the same required hostname.
3. Restart using the supported installer or configuration process.
4. Confirm the new SHA-256 is served and agents reconnect.

For rejection:

1. Test an untrusted CA.
2. Test a hostname mismatch.
3. Test an expired test certificate when available.
4. Confirm agents and admin clients reject each invalid condition.
5. Confirm no option silently disables certificate verification.

Record `tls_certificate_renewal` and `invalid_tls_rejection` separately.

## Eight-hour and twenty-four-hour soak

The following command performs real HTTPS live/readiness checks and records exact duration, count, failures and latency percentiles. Keep representative agents active during the soak.

Eight hours:

```text
python commercial/tools/run_physical_certification.py soak --evidence rc1-evidence.json --step-id soak_8_hours --platform cross-platform --operator 'Operator Name' --server-url https://staging-monitor.example.com:8443 --ca-bundle staging-ca.pem --duration-hours 8 --interval-seconds 30
```

Twenty-four hours:

```text
python commercial/tools/run_physical_certification.py soak --evidence rc1-evidence.json --step-id soak_24_hours --platform cross-platform --operator 'Operator Name' --server-url https://staging-monitor.example.com:8443 --ca-bundle staging-ca.pem --duration-hours 24 --interval-seconds 30
```

During each soak, also collect operating-system CPU, RAM, disk, open handles or file descriptors, database size and WAL size at regular intervals. Attach those system logs to the step.

## Antivirus compatibility

On Windows:

1. Confirm the release ZIP and installed files are scanned by Windows Defender or the approved antivirus.
2. Confirm no exclusion is required for normal operation.
3. Confirm the server task and agent tasks start after reboot.
4. Confirm quarantine history is empty for product files.
5. Capture the antivirus version, signatures, scan result and any controlled allowlisting decision.

Record `windows_antivirus_compatibility` with the exported antivirus report.

## Controlled pilot

Use at least five staging clients, including Windows and Ubuntu, for at least eight hours. Validate:

- Stable physical client count.
- Exact ten-minute offline boundary.
- Correct hostname-change behavior.
- Correct day-history rollups.
- No duplicate messages.
- Real acknowledgement after display.
- Login and every dashboard page remain responsive.
- Assets, software, USB and peripheral data are accurate for the pilot machines.
- Backup succeeds during normal pilot load.
- No unexpected antivirus or firewall blocks.

Record `controlled_pilot` with duration, client list, issue log, screenshots, latency measurements and final operator decision.

## Manual record command

```text
python commercial/tools/run_physical_certification.py record --evidence rc1-evidence.json --step-id STEP_ID --status PASS --platform PLATFORM --operator 'Operator Name' --notes 'Exact result' --duration-seconds 0 --metrics metrics.json --attachment evidence.log
```

A required attachment cannot be replaced by notes alone.

## Verify progress

```text
python commercial/tools/run_physical_certification.py verify --evidence rc1-evidence.json
```

Before approval:

```text
python commercial/tools/run_physical_certification.py verify --evidence rc1-evidence.json --require-complete
```

## Final approval

A different person must finalize the completed ledger:

```text
python commercial/tools/run_physical_certification.py finalize --evidence rc1-evidence.json --approver 'Approver Name' --notes 'All physical release gates independently reviewed.'
```

After finalization, the ledger is immutable through the certification tool. Store the JSON ledger and its complete `*-attachments` directory together.

## Manual self-hosted preflight workflow

`.github/workflows/commercial-physical-certification.yml` is manual-only. It requires staging runners with these labels:

- Windows: `self-hosted`, `windows`, `x64`, `sagar-monitor-staging`
- Ubuntu: `self-hosted`, `linux`, `x64`, `sagar-monitor-staging`

Set repository secret `STAGING_CA_BUNDLE_PEM` when the staging certificate uses a private CA. The workflow captures partial clean-install evidence and retains artifacts for 90 days. It does not complete the remaining physical steps and cannot certify a release by itself.

## Production release rule

Production deployment is allowed only when:

- The deterministic release package is unchanged.
- All required physical steps have latest status PASS.
- Attachment and ledger hashes verify.
- The evidence is finalized by a different approver.
- No unresolved severity-1 or severity-2 pilot issue remains.
- A tested rollback package and verified backup are available.
