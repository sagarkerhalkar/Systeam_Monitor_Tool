# Hackathon Cloud Architecture

## Deployment flow

```text
Developer
   |
   v
GitHub Pull Request
   |
   +--> unit / integration / syntax tests
   +--> Trivy filesystem + IaC scan
   |
   v
Merge to hackathon release branch
   |
   v
GitHub Actions (OIDC)
   |
   +--> build monitor-backend image
   +--> build monitor-ai image
   +--> build monitor-web image (when separated)
   +--> Trivy image vulnerability gate
   +--> CycloneDX SBOM
   +--> push image to ECR
   +--> Cosign keyless sign image digest
   +--> Cosign SBOM attestation
   +--> verify signature + attestation
   |
   v
GitOps manifest update (immutable digest)
   |
   v
Argo CD auto-sync
   |
   v
Argo Rollouts
   |
   +--> 10% canary
   +--> Prometheus analysis
   +--> 25% canary
   +--> Prometheus analysis
   +--> 50% canary
   +--> Prometheus analysis
   +--> 100% promotion
   |
   +--> failure --> abort --> stable ReplicaSet
   |
   v
EKS application namespace
```

## Runtime services

```text
Internet
  |
  v
AWS Load Balancer / Ingress
  |
  v
cert-manager TLS
  |
  +----------------------+----------------------+
  |                      |                      |
  v                      v                      v
Monitor Web          Monitor Backend       AI Ops Service
                                                   |
                                                   v
                                         anomaly/health scoring
  |
  v
Persistent application DB / DORA event store
```

Windows and Ubuntu monitoring agents remain external clients and talk only to the hackathon endpoint used for demo systems. The live production monitor endpoint is not redirected to this cluster.

## Observability

OpenTelemetry instrumentation and cluster collectors send:

- metrics to Prometheus
- logs to Loki
- traces to Tempo
- visualizations to Grafana
- alerts to Alertmanager

Prometheus metrics are also used by Argo Rollouts AnalysisTemplates so the same production health signals which operators observe are used to decide whether a canary may proceed.

## DORA event model

The hackathon `dora-collector` records normalized events:

```json
{
  "event_type": "deployment|incident_started|incident_recovered|rollback",
  "service": "monitor-backend",
  "commit_sha": "...",
  "image_digest": "sha256:...",
  "environment": "production",
  "occurred_at": "...",
  "source": "github-actions|argocd|argo-rollouts|alertmanager",
  "status": "success|failure|recovered"
}
```

Metrics are calculated from event timestamps rather than manually entered values.

### Deployment Frequency

Count successful production promotions during the selected Grafana time window.

### Lead Time for Changes

For each production deployment:

`successful promotion timestamp - source commit timestamp`

Grafana shows median and percentile trends.

### Change Failure Rate

`production changes that caused an aborted rollout, rollback, or qualifying incident / total production changes * 100`

### Mean Time to Restore

For each deployment-related incident:

`incident recovered timestamp - incident started timestamp`

Grafana shows the mean/median restoration time and individual incident durations.

## Automated rollback proof

A deliberately unhealthy demo image exposes a failing readiness/application metric. Argo Rollouts AnalysisTemplate queries Prometheus. When the configured failure threshold is reached, the Rollout aborts, the stable ReplicaSet receives traffic again, and incident/rollback events are sent to the DORA collector. This creates visible Change Failure Rate and MTTR evidence without intentionally damaging the production System Monitor deployment.

## Policy layers

### CI policy

Trivy scans source, configuration, IaC and built images. The release workflow fails when vulnerability severity exceeds the documented threshold.

### Cluster admission policy

Kyverno enforces:

- allowed image registry
- immutable digest references
- required CPU/memory requests and limits
- non-root containers
- no privilege escalation
- read-only root filesystem where compatible
- dropped Linux capabilities
- required probes
- Cosign signature/identity verification

## Supply-chain evidence

Every released container has:

- source commit SHA
- OCI image digest
- Trivy vulnerability report
- CycloneDX SBOM
- Cosign signature
- signed SBOM attestation
- GitHub Actions run evidence
- GitOps commit that promoted the digest
- Argo CD deployment record

This creates a traceable chain from source commit to the exact image admitted into EKS.

## Repository layout target

```text
hackathon/
  README.md
  ARCHITECTURE.md
  ai-service/
  dora-collector/
  docker/
  terraform/
  ansible/
  helm/
  gitops/
    base/
    overlays/prod/
  policies/kyverno/
  observability/
    prometheus/
    grafana/
    loki/
    tempo/
    otel/
  scripts/
  reports/
.github/workflows/
  hackathon-ci.yml
  hackathon-release.yml
  hackathon-gitops.yml
```
