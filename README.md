# ModelOps Platform

**Enterprise model hosting, inference optimization, and fine-tuning platform**

A Kubernetes-native engineering project for the complete **model lifecycle**: register, deploy, benchmark, fine-tune, evaluate, release, observe, and roll back AI models.

> **Engineering Preview — NOT a completed enterprise platform.** The upstream foundation is imported; static CI and CPU Kubernetes/LiteLLM health checks passed. SGLang Operator support, fine-tune validation, inference measurement tools and P0 correctness fixes are merged. **Independent platform audit estimates about 40% non-GPU platform completeness** (heuristic rubric, not an automated metric). The product UI, unified model registry/API, per-job fine-tuning parameters, least-privilege RBAC and complete Operator/Canary E2E are still missing. **GPU serving, GPU training and multi-node HA are unverified.** Derived from [GaeaRuiW/kube-llmops](https://github.com/GaeaRuiW/kube-llmops) (Apache-2.0).

## Architecture at a glance

```text
ModelOps Control Plane        Registry / revisions / rollout policies / quotas
        |
Inference Plane              vLLM | SGLang | llama.cpp | TEI
                             (Helm configs; live models not yet validated)
                             ASR / TTS first-class adapters (planned)
        |
Training Plane               FineTuneRun -> Argo -> LLaMA-Factory -> MLflow
        |                    (upstream pipeline; real GPU E2E validation pending)
        |
Observability                 Prometheus | Grafana | Langfuse | logs
        |
Kubernetes Operator + Helm   Reconcile | deploy (partial)
                             Canary/rollback consistency (in progress)
```

## What exists today

The imported baseline already contains:
- **Operator + CLI:** Kubernetes `LLMPlatform`, `ModelDeployment` and `FineTuneRun` resource types with controllers and `kubectl-llmops` command implementation.
- **Inference packaging:** vLLM, llama.cpp and TEI Helm components, LiteLLM gateway, Kubernetes resources and prebuilt dashboards.
- **Training scaffolding:** Argo workflow + LLaMA-Factory + MLflow components. ModelOps changes use the real WorkflowTemplate, verify dataset separation, merge actual checkpoints and evaluate real weights with a fail-closed quality gate (GPU job not yet exercised).
- **Observability:** Prometheus/Grafana/Langfuse components, example dashboards and alerting.
- **Management UI:** Headlamp integration via an upstream plugin.

**Evidence boundary:** upstream CI's scheduled fine-tuning E2E checks Helm templates and script syntax; it does *not* execute an actual GPU training run. Hardware-specific claims, multi-node high availability and inference optimizations are not proven until our own run artifacts are committed.

## Development priorities

| Gate | Outcome | Evidence |
|---|---|---|
| M0 | License-preserved upstream import | 473/473 source Git blobs verified, source SHA documented |
| M1 | Trustworthy installation and CI | Go/Helm/Python tests, Argo DAG render, real CPU-kind LiteLLM health check: verified |
| M2 | Serving lifecycle | Versioned model deployment, gateway routing, health/rollback |
| M3 | Optimization bench | TTFT, TPOT, p95/p99 latency, tokens/s, VRAM, KV, concurrency A/B |
| M4 | Real fine-tune → serving | Dataset, LoRA/QLoRA, held-out eval, MLflow artifacts, release gate |
| M5 | Reliability and security | Failure injection, fault recovery, runbooks, SLOs, tenant isolation |
| M6 | AI-assisted operations | Audited diagnosis and human-approved changes |

See the [full platform audit and weighted completion rubric](docs/PLATFORM_AUDIT_2026-10-11.md), [implementation plan](docs/IMPLEMENTATION_PLAN.md), and [prioritized platform milestones](https://github.com/Benjamindaoson/ModelOps-Platform/issues).

## Quick static check (no GPU required)

```bash
# Prerequisites: Helm 3 and Internet for chart dependencies
helm dependency update charts/kube-llmops-stack
helm lint charts/kube-llmops-stack -f charts/kube-llmops-stack/values-ci.yaml
helm template modelops charts/kube-llmops-stack -f charts/kube-llmops-stack/values-ci.yaml > /dev/null

# Operator/unit tests (Go 1.25+)
cd operator && go test ./api/v1alpha1 ./internal/engine ./internal/builder ./internal/gateway ./internal/helmbridge ./internal/cli/...
# Full controller envtest requires a separate Kubernetes API/etcd test environment.
```

These are static / CPU-oriented checks and do not constitute a working production deployment.

## Repository layout

- [`operator/`](operator/) — CRDs, reconciler controllers, CLI and deployment builders.
- [`charts/`](charts/) — Helm charts for model engines, gateway, fine-tuning, and monitoring.
- [`images/`](images/) — model resolver/loader and supporting Docker images.
- [`plugins/`](plugins/) — Headlamp plugin UI.
- [`tests/`](tests/) — existing integration and Helm template tests.
- [`docs/UPSTREAM_PROVENANCE.md`](docs/UPSTREAM_PROVENANCE.md) — pinned upstream source and license attribution.
- [`docs/PLATFORM_AUDIT_2026-10-11.md`](docs/PLATFORM_AUDIT_2026-10-11.md) — precise feature audit, JD fit, major blockers and acceptance roadmap.
- [`docs/DELIVERY_STATUS_2026-10-11.md`](docs/DELIVERY_STATUS_2026-10-11.md) — completed changes, real evidence and outstanding hardware/security requirements.
- [`benchmarks/inference/`](benchmarks/inference/) — live-load benchmarking and A/B evidence checks.
- [`pipelines/`](pipelines/) — real adapter merge, heldout dataset verification and fail-closed promotion.
- [`ops/`](ops/) — HTTP smoke probes and production preflight.
- [`docs/upstream/README.md`](docs/upstream/README.md) — unchanged original upstream README.

## Licensing & attribution

The initial codebase is derived from **GaeaRuiW/kube-llmops**, commit `74f8db47fa2690a4e71ae31532f36b35a587d266`, under **Apache License 2.0**. The upstream `LICENSE`, file headers and attribution are retained. Future changes are traceable in this repository's Git history. Dependencies may carry their own licenses; review them before redistribution or production deployment.

**Engineering policy:** do not present imported upstream features as independently built. Quantitative performance claims must include runnable configuration, raw measurements, hardware/environment provenance and a baseline.
