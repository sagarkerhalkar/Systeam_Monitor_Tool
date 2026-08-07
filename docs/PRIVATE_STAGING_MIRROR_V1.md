# Private Staging Mirror V1

## Purpose

The commercial physical-certification workflow must never dispatch a self-hosted runner from the public source repository. This handoff creates or synchronizes a separate private staging repository from one exact, already-certified `commercial-v1` commit.

This process does **not** deploy production, copy production data, copy production secrets, or authorize production deployment.

## Current certified source

Source repository: `sagarkerhalkar/Systeam_Monitor_Tool`

Source branch: `commercial-v1`

The operator must supply the exact 40-character merge commit that is approved for staging. The mirror command fetches `commercial-v1` from `origin` and refuses to continue if `FETCH_HEAD` differs from that exact commit.

## Safety rules

1. The source checkout must be a real Git checkout with a clean working tree.
2. `origin` must resolve to the expected `github.com` source repository.
3. The target must be a different `owner/name` repository.
4. An existing target must be `PRIVATE`.
5. If the target does not exist, the bootstrap creates it as private with issues and wiki disabled.
6. The exact certified commit is pushed to target branch `commercial-v1`.
7. The private target default branch is set to `commercial-v1`.
8. Environment `commercial-staging-certification` is created in the private target.
9. The target branch SHA is read back from GitHub and must exactly equal the certified source SHA.
10. A runner registration token is issued only after the target is verified private.
11. Runner token files are refused when their path is inside the source checkout.
12. Token values are never printed by the staging CLI or wrappers.
13. Production port 2278 and production paths remain outside this process.

## Prerequisites on the operator machine

- Git installed.
- GitHub CLI (`gh`) installed.
- `gh auth login` already completed with access to create/manage the private target repository.
- A clean clone of `sagarkerhalkar/Systeam_Monitor_Tool` with `origin` pointing to GitHub.
- Checkout may be any branch, but the bootstrap always fetches and verifies remote `commercial-v1`.

## Windows: create or synchronize the private mirror

Open PowerShell in the source repository and run:

```powershell
& .\commercial\staging\windows\bootstrap-private-staging.ps1 `
  -TargetRepository 'sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private' `
  -ExpectedSourceCommit '<40-character-certified-commercial-v1-sha>'
```

A verification report is written under `%ProgramData%\SagarMonitorStaging` by default.

A no-write prerequisite check can be run first:

```powershell
& .\commercial\staging\windows\bootstrap-private-staging.ps1 `
  -TargetRepository 'sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private' `
  -ExpectedSourceCommit '<40-character-certified-commercial-v1-sha>' `
  -DryRun
```

## Ubuntu: create or synchronize the private mirror

```bash
sudo mkdir -p /var/lib/sagar-monitor-staging
sudo chown "$USER" /var/lib/sagar-monitor-staging
./commercial/staging/ubuntu/bootstrap-private-staging.sh \
  sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private \
  '<40-character-certified-commercial-v1-sha>'
```

For a no-write check:

```bash
DRY_RUN=1 ./commercial/staging/ubuntu/bootstrap-private-staging.sh \
  sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private \
  '<40-character-certified-commercial-v1-sha>'
```

## Issue an ephemeral-runner registration token

Create the token only immediately before registering one staging runner. Store it outside the repository checkout.

Windows example:

```powershell
& .\commercial\staging\windows\issue-private-runner-token.ps1 `
  -TargetRepository 'sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private' `
  -OutputPath 'C:\ProgramData\SagarMonitorStaging\runner-token.txt'
```

Ubuntu example:

```bash
./commercial/staging/ubuntu/issue-private-runner-token.sh \
  sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private \
  /var/lib/sagar-monitor-staging/runner-token.txt
```

Then pass that file to the existing checksum-verified ephemeral-runner installer. The installer deletes the token file after registration.

## Staging runner sequence

For each Windows or Ubuntu staging machine:

1. Run the clean-host preparation script and create its signed host marker.
2. Obtain the official GitHub Actions runner archive separately.
3. Verify its published SHA-256 before use.
4. Create a runner-registration token file with the private-target token command above.
5. Run `install-ephemeral-runner.ps1` or `install-ephemeral-runner.sh` with the local runner archive, expected SHA-256 and token file.
6. Confirm the generated runner receipt verifies against the host marker and private repository.
7. Dispatch exactly one physical-certification job.
8. The ephemeral runner unregisters after its job; reinstall before the next physical job.

## Human GitHub settings that remain required

The bootstrap creates the private repository and `commercial-staging-certification` environment, but GitHub account policy can vary. Before physical dispatch, an administrator must review the private target in GitHub and configure the desired environment approver/reviewer rules supported by the account. Do not weaken the repository-private requirement to bypass an unavailable environment feature.

## Verification commands

Print the mirror plan:

```bash
PYTHONPATH=commercial python commercial/tools/run_staging_lab.py private-mirror-plan \
  --target-repository sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private \
  --expected-source-commit '<40-character-certified-commercial-v1-sha>'
```

Verify that a repository is private:

```bash
PYTHONPATH=commercial python commercial/tools/run_staging_lab.py repository-check \
  --repository sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private
```

## Production boundary

A private staging mirror is only an isolated execution boundary for physical qualification. It is not a production release approval. Production remains blocked until the complete physical evidence ledger is PASS, attachment hashes verify, the long soak requirements are complete, and a second independent approver finalizes certification.