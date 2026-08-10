# TWS Phase 3 Hackathon — System Monitor Own Project

**Date:** 10 August 2026  
**Participant:** Sagar Kerhalkar  
**Track:** Own Project  
**Project:** System Monitor — DORA + SOTA

## Repository plan

Public hackathon repository:

`https://github.com/sagarkerhalkar/System-Monitor-DORA-SOTA-Hackathon`

The repository publisher is prepared. Until the standalone repo is published, active development is isolated on:

`https://github.com/sagarkerhalkar/Systeam_Monitor_Tool/tree/hackathon/dora-sota-monitor-20260810`

The production `workingcode` branch is not modified by hackathon work.

## Application qualification

The own-project implementation has all four required application components:

1. **UI** — System Monitor DORA + SOTA web dashboard.
2. **Backend** — the real commercial System Monitor API/server.
3. **Database** — commercial Monitor SQLite/WAL database plus persistent DORA event database.
4. **AI Service** — separate AI Ops anomaly-analysis service for CPU, RAM, disk, latency and packet-loss telemetry.

## Phase 1 implemented

- Containerized the real commercial System Monitor backend.
- Added a separate AI Ops service with robust anomaly scoring, health classification and remediation guidance.
- Added a DORA event collector that records deployment and incident/recovery events.
- DORA collector calculates:
  - deployment frequency,
  - median lead time,
  - change failure rate,
  - mean time to recovery.
- Added System Monitor hackathon UI showing service health, DORA metrics, deployment/incident history and AI analysis.
- Added Docker Compose for the complete four-service stack.
- Containers use non-root execution where applicable, dropped Linux capabilities, no-new-privileges and persistent volumes only where required.
- Added unit tests for AI Ops and DORA metric calculations.
- Added GitHub Actions Phase-1 CI to compile, test, build all four images, start the complete stack and smoke-test all components.

## DORA + SOTA implementation target

The final cloud-native architecture will use:

- AWS EKS
- Terraform
- GitHub Actions
- Amazon ECR
- Argo CD auto-sync
- Argo Rollouts canary progressive delivery
- Prometheus + Grafana
- Loki + Tempo + OpenTelemetry
- Alertmanager incident/rollback events
- Kyverno policy-as-code
- Trivy CI security gate
- CycloneDX SBOM
- Cosign/Sigstore image signing and verification
- AWS Secrets Manager with rotation
- cert-manager HTTPS

## Six checklist proofs planned

1. **Deployment frequency + lead time** — CI/GitOps deployment events feed DORA collector; Argo CD history shown in demo.
2. **Change failure rate + MTTR** — deliberately unhealthy canary, Prometheus analysis failure, automated rollback, incident/recovery timestamps.
3. **Progressive delivery** — Argo Rollouts 10% → 25% → 50% → 100% canary.
4. **Policy as code** — Kyverno admission policies plus Trivy High/Critical CI gate.
5. **Supply-chain security** — immutable image digests, CycloneDX SBOM, Cosign signing/verification and attestation.
6. **DORA dashboard** — Grafana dashboard populated from actual CI/CD and incident events, not static demo values.

## Safety boundary

- Live Windows production remains on `workingcode`.
- Hackathon deployment uses isolated containers/cloud resources.
- The private physical-certification repository remains private.
- No production database or secrets are copied to the hackathon project.

## Current status

Phase 1 code is implemented and under CI validation. Infrastructure, GitOps, progressive delivery, policy, supply-chain and observability phases are next.

**Deadline target:** before 15 August 2026, 11:59 PM IST.
