# Commercial Staging Lab Bootstrap V1

## Status

This package prepares the real Windows and Ubuntu staging machines required by the physical certification gate.

It does **not** deploy to production and it does **not** claim that any physical test has passed.

The repository `sagarkerhalkar/Systeam_Monitor_Tool` is currently public. Self-hosted runner registration is therefore blocked by design. GitHub recommends self-hosted runners only for private repositories because untrusted workflow changes can expose the runner machine.

The staging tools remain fully usable in offline/local mode while the repository is public.

## Required isolated machines

The fixed plan requires seven staging roles:

1. `windows_server`
2. `ubuntu_server`
3. `windows_client_1`
4. `windows_client_2`
5. `ubuntu_client_1`
6. `ubuntu_client_2`
7. `restore_host`

Minimum server requirements are 4 CPU cores, 8 GiB RAM and 50 GiB free disk. The separate restore host requires 100 GiB free disk. Client hosts require 2 CPU cores, 4 GiB RAM and 20 GiB free disk.

All staging machines must be isolated from production credentials and production network access. Port `2278` must be unused during clean-host preparation.

## Security model

- Known production paths are rejected.
- Port `2278` must not already be listening on a clean host.
- A successful preflight creates a SHA-256-bound host marker.
- The marker records role, platform, hostname, site, operator and preflight identity.
- Runner packages must be supplied locally with an expected SHA-256.
- Runner packages are never downloaded by the bootstrap scripts.
- Registration tokens are read from temporary files and removed after use.
- GitHub CLI must confirm that the repository visibility is `PRIVATE`.
- Runners are always registered with `--ephemeral`.
- A runner receipt is bound to the host marker and verified before the physical workflow starts.
- The physical workflow can run only from `commercial-v1`.
- The physical workflow requires the protected environment `commercial-staging-certification`.
- The current public repository causes the hosted safety job to fail before any self-hosted job is dispatched.

## Build a deterministic staging release candidate

From the repository root:

```bash
export PYTHONPATH=commercial
python commercial/tools/run_staging_lab.py build-rc \
  --repository-root . \
  --output sagar-monitor-staging-1.0.0-rc1.zip \
  --version 1.0.0-rc1 \
  --source-commit <COMMERCIAL_V1_COMMIT_SHA>

python commercial/tools/run_staging_lab.py verify-rc \
  --package sagar-monitor-staging-1.0.0-rc1.zip
```

The RC contains:

- The deterministic commercial-server source package.
- The fixed staging plan.
- An RC manifest containing the source commit and SHA-256 values.
- A declaration that the archive contains no secrets.
- A declaration that the archive does not authorize production deployment.

The workflow `.github/workflows/commercial-staging-rc.yml` builds and uploads the verified RC automatically after a merge to `commercial-v1`.

## Windows clean-host preparation

Open PowerShell as Administrator from the extracted commercial package:

```powershell
Set-ExecutionPolicy -Scope Process Bypass

& .\commercial\staging\windows\prepare-staging-host.ps1 `
  -Role windows_server `
  -Site "Bhopal isolated staging lab" `
  -Operator "Operator Name"
```

The command creates:

```text
C:\ProgramData\SagarMonitorStaging\host-preflight.json
C:\ProgramData\SagarMonitorStaging\host-marker.json
```

The directory ACL grants full access to SYSTEM and local Administrators, modify access to the preparing operator and read access to the service account.

## Ubuntu clean-host preparation

Run as root:

```bash
sudo bash commercial/staging/ubuntu/prepare-staging-host.sh \
  ubuntu_server \
  "Bhopal isolated staging lab" \
  "Operator Name"
```

The command creates:

```text
/var/lib/sagar-monitor-staging/host-preflight.json
/var/lib/sagar-monitor-staging/host-marker.json
```

The directory is protected by the `sagar-monitor-staging` system group.

## Offline physical certification

Offline/local execution is the approved path while the repository remains public.

Use the existing operating-system wrappers:

```text
commercial/server/windows/run-physical-certification.ps1
commercial/server/ubuntu/run-physical-certification.sh
```

Record every physical action in the tamper-evident certification ledger. Do not mark a step PASS without its required attachment and real duration.

## Private repository transition

Before connecting any self-hosted runner:

1. Change this repository to private, or create a separate private staging repository containing the exact `commercial-v1` commit.
2. Install and authenticate GitHub CLI on the staging host.
3. Create the protected GitHub environment `commercial-staging-certification`.
4. Add the trusted staging CA certificate as environment secret `STAGING_CA_BUNDLE_PEM`.
5. Download the official GitHub Actions runner archive using GitHub's repository runner setup page.
6. Save the runner registration token in a temporary file. GitHub registration tokens are time limited.
7. Record the official archive SHA-256 separately.

The bootstrap intentionally has no override for a public repository.

## Windows ephemeral runner registration

```powershell
& .\commercial\staging\windows\install-ephemeral-runner.ps1 `
  -Repository "sagarkerhalkar/Systeam_Monitor_Tool" `
  -RegistrationTokenFile "C:\SecureTemp\runner-token.txt" `
  -RunnerArchivePath "C:\SecureTemp\actions-runner-win-x64.zip" `
  -RunnerArchiveSha256 "<OFFICIAL_64_CHARACTER_SHA256>"
```

The registration token file is removed in a `finally` block. The runner unregisters after one workflow job.

Remove the local runner service and files with:

```powershell
& .\commercial\staging\windows\remove-staging-runner.ps1
```

Host markers and physical evidence are preserved.

## Ubuntu ephemeral runner registration

```bash
sudo bash commercial/staging/ubuntu/install-ephemeral-runner.sh \
  sagarkerhalkar/Systeam_Monitor_Tool \
  /root/runner-token.txt \
  /root/actions-runner-linux-x64.tar.gz \
  <OFFICIAL_64_CHARACTER_SHA256>
```

The installer creates the dedicated user `sagar-staging-runner`, installs the official service, configures the Debian/Ubuntu `needrestart` exclusion recommended by GitHub, removes the token file and writes a signed runner receipt.

Remove the local service and runner files with:

```bash
sudo bash commercial/staging/ubuntu/remove-staging-runner.sh
```

Host markers and physical evidence are preserved.

## Run the protected physical workflow

After both ephemeral runners are online and the repository is private:

1. Open GitHub Actions.
2. Select **Commercial Physical Certification Preflight**.
3. Run the workflow from branch `commercial-v1` only.
4. Choose Windows, Ubuntu or both.
5. Enter the exact RC identifier, staging site, operator and HTTPS staging URL.
6. Approve the protected `commercial-staging-certification` environment.
7. Download the 90-day evidence artifacts.
8. Reinstall an ephemeral runner before a later physical workflow job.

## Production block

A green staging preflight is not a production release approval.

Production remains blocked until the complete physical ledger contains all required PASS results, all attachment hashes verify, the 8-hour and 24-hour soak durations are real, the controlled pilot is completed and a different approver finalizes the evidence.
