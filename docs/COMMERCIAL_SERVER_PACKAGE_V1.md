# Commercial Server Package V1

## Scope

This phase packages the green commercial APIs as a separate server product. It does not edit or deploy `server.py`, the `workingcode` branch, the current dashboard, current agents, or production data.

## Included

- One combined endpoint for organization/user administration and authenticated agents.
- Threaded HTTP request handling with fixed request framing.
- TLS 1.2 minimum and HTTP Strict Transport Security.
- Header and request-body limits.
- Live and readiness health endpoints.
- Checksum-verified, ordered SQL migrations.
- One-time first organization and administrator bootstrap.
- No default administrator, fallback password, or password command-line argument.
- Online SQLite backup using the SQLite backup API.
- Backup manifest with size, SHA-256 and `PRAGMA quick_check` evidence.
- Restore only after explicit service-stop confirmation.
- Automatic pre-restore preservation of the current database.
- Deterministic source ZIP with an internal per-file SHA-256 manifest.
- Versioned Windows and Ubuntu application directories.
- Pre-upgrade backup and automatic application pointer rollback.
- State-preserving uninstall by default.

## Directory separation

### Windows

- Application versions: `C:\Program Files\SagarMonitorCommercialServer\versions`
- Stable runner and version pointer: `C:\Program Files\SagarMonitorCommercialServer`
- Configuration and TLS: `C:\ProgramData\SagarMonitorCommercialServer\config`
- Database: `C:\ProgramData\SagarMonitorCommercialServer\data`
- Backups: `C:\ProgramData\SagarMonitorCommercialServer\backups`

The Windows pilot uses a protected SYSTEM startup task. The final signed MSI phase may replace this wrapper with a native Windows service host without changing the server protocol or database layout.

### Ubuntu

- Application versions: `/opt/sagar-monitor-commercial-server/versions`
- Stable current symlink and runner: `/opt/sagar-monitor-commercial-server`
- Configuration and TLS: `/etc/sagar-monitor-commercial-server`
- Database: `/var/lib/sagar-monitor-commercial-server`
- Backups: `/var/backups/sagar-monitor-commercial-server`

Ubuntu uses a dedicated `sagarmonitor-server` user and a hardened systemd service.

## First installation

A valid TLS certificate and private key are mandatory. The certificate must contain a SAN matching the hostname used by agents and administrators.

Create a password file readable only by the installing administrator. The password must meet the commercial password policy. The installers copy it to a protected temporary bootstrap file; the original operator file is not deleted.

### Windows example

```powershell
& .\commercial\server\windows\install-commercial-server.ps1 `
  -CertificateFile 'D:\TLS\fullchain.pem' `
  -PrivateKeyFile 'D:\TLS\private-key.pem' `
  -Port 8443 `
  -OrganizationName 'Next Toppers' `
  -AdminUsername 'commercial.admin' `
  -AdminPasswordFile 'D:\Secure\admin-password.txt' `
  -HealthUrl 'https://monitor.example.com:8443'
```

### Ubuntu example

```bash
sudo bash commercial/server/ubuntu/install-commercial-server.sh \
  --certificate /root/tls/fullchain.pem \
  --private-key /root/tls/private-key.pem \
  --port 8443 \
  --organization-name 'Next Toppers' \
  --admin-username commercial.admin \
  --admin-password-file /root/admin-password.txt \
  --health-url https://monitor.example.com:8443
```

## Upgrades

The installer performs these steps while the service is stopped:

1. Create a new immutable application version.
2. Install only hash-locked dependencies.
3. Copy and protect TLS/configuration files.
4. Create and verify a pre-upgrade database backup.
5. Apply checksum-verified migrations.
6. Run local database and administrator health checks.
7. Atomically move the current-version pointer.
8. Start the service.
9. Verify service/port or the configured HTTPS health URL.
10. Restore the prior pointer automatically if any step fails.

An upgrade does not delete old versions automatically. Retention of old versions will be added to the signed-release lifecycle after rollback testing.

## Backup and restore

```bash
python commercial/tools/run_commercial_server.py --config server.json backup
python commercial/tools/run_commercial_server.py --config server.json verify-backup --backup backup.db
python commercial/tools/run_commercial_server.py --config server.json restore --backup backup.db --confirm-service-stopped
```

Restore must never be run while the server process is active. The restore command verifies the manifest, SHA-256 and SQLite integrity, then creates a pre-restore backup of the existing database before atomic replacement.

## Health endpoints

- `GET /api/v1/health/live`: process/API routing is alive.
- `GET /api/v1/health/ready`: database integrity, migration state and active administrator are valid.

The CLI `health` command checks local files, database integrity, WAL size, migrations, TLS presence and backup-directory write access. `health --remote --url ...` additionally verifies the running HTTPS endpoint with normal certificate validation.

## Package generation

```bash
PYTHONPATH=commercial python commercial/tools/build_commercial_server_package.py build \
  --repository-root . \
  --output sagar-monitor-commercial-server.zip \
  --version 1.0.0-rc1
```

The resulting ZIP is deterministic for the same source, contains `MANIFEST.json`, and excludes the legacy production server and `workingcode` content.

## Remaining production gates

This phase is not permission to replace the live server. Promotion still requires:

- Native installation on a clean Windows Server test machine.
- Native installation on a clean Ubuntu Server test machine.
- Certificate-chain and hostname validation using the real customer hostname.
- Concurrent admin and agent API load tests.
- 100, 500 and 1,000-agent heartbeat simulations.
- Long-duration memory, file descriptor, database and WAL soak testing.
- Power interruption and process-kill recovery.
- Backup restoration onto separate hardware.
- Upgrade and rollback from a prior signed release candidate.
- Signed installer/release artifacts.
- Controlled pilot deployment before production.
