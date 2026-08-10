# Sagar System Monitor — DORA + SOTA Hackathon Track

This directory contains the isolated hackathon/cloud-native implementation for the Sagar System Monitor project.

## Safety boundary

- Base: `commercial-v1`
- Hackathon branch: `hackathon/dora-sota-monitor-20260810`
- `workingcode` is production and is not modified or deployed by this track.
- Cloud/Kubernetes manifests, images, tests and demo data are isolated from the live Windows deployment.

## Own-project qualification

The hackathon deployment contains four explicit application components:

1. **UI** — System Monitor web dashboard.
2. **Backend API** — commercial monitoring API/server.
3. **Database** — persistent application data plus DORA event storage.
4. **AI Service** — AI Ops anomaly service for CPU, RAM, disk, latency, packet-loss and network telemetry analysis.

## Target platform

- AWS EKS
- Terraform for infrastructure
- GitHub Actions for CI and security gates
- Amazon ECR for OCI images
- Argo CD for GitOps reconciliation and visible deployment history
- Argo Rollouts for canary / progressive delivery
- Prometheus + Grafana for metrics and DORA dashboards
- Loki for logs
- Tempo + OpenTelemetry for traces
- Alertmanager for incident/rollback alerts
- Kyverno for admission policy and signed-image enforcement
- Trivy for vulnerability/configuration scanning and SBOM generation
- Cosign/Sigstore for keyless image signing and SBOM attestations
- cert-manager for HTTPS certificates

## Hackathon acceptance criteria

### 1. Deployment frequency and lead time

- CI builds and publishes immutable image digests.
- CI updates GitOps manifests rather than applying directly to the cluster.
- Argo CD auto-sync is enabled with self-heal.
- Deployment history is visible in Argo CD and emitted into the DORA event collector.
- Lead time is measured from source commit timestamp to successful production promotion timestamp.

### 2. Change failure rate and MTTR

- Canary health is evaluated with Prometheus AnalysisTemplates.
- Failed analysis aborts the rollout to the stable ReplicaSet.
- Alertmanager records an incident start and recovery event.
- The DORA collector computes failed changes / total changes and incident restore duration.

### 3. Progressive delivery

- Argo Rollouts canary strategy: 10% → 25% → 50% → 100%.
- Automated Prometheus analysis gates progression.
- A rollback window keeps recent stable revisions available for rapid restoration.

### 4. Policy as code

- Trivy blocks Critical/High vulnerabilities according to the documented CI policy.
- Kyverno enforces non-root execution, resource limits, immutable image digests and allowed registries.
- Kyverno verifies Cosign image identity/signature before admission.

### 5. Supply-chain security

- Images are pushed by digest.
- Trivy generates CycloneDX SBOMs.
- GitHub OIDC is used for short-lived cloud/signing identity where supported.
- Cosign signs images and attaches/verifies SBOM attestations.
- GitHub Actions stores scan/SBOM evidence as build artifacts.

### 6. DORA dashboard

Grafana displays:

- Deployment Frequency
- Median Lead Time for Changes
- Change Failure Rate
- Mean Time to Restore
- Successful vs failed rollouts
- Open/recovered incidents
- Deployment history with commit SHA and image digest

The DORA collector takes events from CI/CD, Argo Rollouts and incident/alert events rather than using manually entered numbers.

## Demo proof

The recorded/live demo must show both success and controlled failure:

1. Commit a safe change and show CI → signed image → GitOps commit → Argo CD sync → canary → healthy promotion.
2. Show Argo CD deployment history.
3. Deploy a deliberately unhealthy demo revision and show Prometheus analysis fail, Argo Rollouts abort and traffic return to stable.
4. Show Alertmanager/Grafana incident and recovery evidence.
5. Attempt an unsigned or policy-breaking image and show Kyverno deny it.
6. Show Trivy scan/SBOM/Cosign verification evidence.
7. Open the Grafana DORA dashboard and explain all four required DORA metrics.

## Submission artifacts

- Repository link
- Live application URL
- DORA + SOTA report
- Working recorded/live demo
- Grafana DORA dashboard screenshots/export
- Argo CD/Rollouts evidence
- CI security and supply-chain evidence
- Cost/teardown evidence
