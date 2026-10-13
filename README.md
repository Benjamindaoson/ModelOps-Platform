# ModelOps Platform

**AI Model Training, Serving & Lifecycle Infrastructure — v1.0 RC**

A Kubernetes-native, open-source engineering platform for managing the lifecycle of enterprise models: **register → train → evaluate → deploy → benchmark → observe → release/roll back**. ModelOps serves model-owning teams, not end-user chat applications. It supports a hybrid architecture in which self-hosted engines and external providers can be governed through a common gateway.

> **Engineering preview, not independently certified production infrastructure.** The repository contains a real FastAPI control plane, Next.js operator console, Kubernetes Operator, Argo training orchestration, gateway and monitoring integrations, and automation tests. A passing CPU test **does not prove** GPU-serving performance, model quality, multizone high availability or deployment into an enterprise production environment. See [evidence and gaps](#validation-and-evidence).

## v1.0 RC: implemented, validated, not yet validated

Model-owning teams need to know which dataset produced a checkpoint, whether that version passed the right evaluation, and how to load or roll it back. This repository proves that lifecycle with bounded real GPU jobs and keeps infrastructure acceptance separate from model-quality claims.

| Capability | Implemented | Validated in this sprint | Not yet validated |
|---|---|---|---|
| Model Registry | LLM/VLM/VLA/Embedding ModelArtifact, immutable model identities, lineage, migrations, ownership and observed deployment state | Reversible SQLite migrations; four legacy VLA versions imported by verified references | VLM native serving; production PostgreSQL runtime |
| Training | Argo/LLaMA-Factory contracts; native Transformers LoRA/QLoRA; retained SmolVLA/LeRobot Flow Matching adapter; six observed job states | Four real RTX 3090 jobs, 160 optimizer updates; Adapter/Checkpoint hashes; pause at step 2 and recovery to step 64 | New SmolVLA jobs through unified REST; Argo GPU scheduling and native full SFT |
| Lifecycle | Evaluation attestation, separate release principal, registered checkpoint, deployment revisions and rollback | Trained Qwen loaded into vLLM, invoked, promoted and rolled back; 384D CPU embedding; 50×7 frozen VLA prediction | GPU Kubernetes rollout, real enterprise OIDC sign-off, TEI/SGLang runtime |
| Inference | Official vLLM benchmark, GPU samples, explicit model/engine/quantization/cache/custom-policy CRD | 40/40 synthetic C4 requests; 6.43 req/s; 183.7 output tokens/s; TTFT P95 34.8 ms | Production workload SLO, hardware-matched acceleration gain and maximum capacity |
| Operations | Protected tenant metrics, audit, recovery/reconciliation, fail-closed production gates | 174 Python tests plus two optional runtime skips; Operator unit/envtest; Helm; Console types/build; real metadata backup/restore | Full object-store/cluster disaster recovery, real OIDC and multizone HA |

**Quality results remain visible:** broad LoRA/QLoRA Token-F1 0.254/0.267 failed the unchanged 0.55 threshold. One additional frozen short-answer task scored 0.561 for both base and trained model, passing the gate with **no observed quality improvement**. This validates a lifecycle, rather than general business-task quality.

See the [execution report](docs/v1/SPRINT_REPORT.md), [validation receipts](docs/v1/results/validation.json), [real training identities](docs/v1/results/training.json), [benchmark](docs/v1/results/benchmark-report.md), [status](docs/v1/status.json) and [reproduction guide](docs/v1/REPRODUCE.md). Weights, datasets and private robot observations remain in the owned cloud project and are excluded from Git.

**Architectural separation:** production metadata lives in PostgreSQL, Kubernetes/Argo own cluster workloads, and private object storage owns checkpoint bundles. The explicit Linux development backend owns observed processes and receipts and is rejected in production mode. Text Token-F1 cannot qualify a robot policy; robotics retains its own release gate.

## Repository layout

- `control-plane/` — Python/FastAPI management API, SQL models, migrations, tenant roles and reconciliation.
- `console/` — Next.js management UI with browser tests against the real API.
- `operator/` — Go Kubernetes controllers and deployment contracts.
- `charts/` — Helm stack, gateway, engines, training and observability.
- `pipelines/` — adapter/checkpoint processing, independent evaluation and evidence gates.
- `benchmarks/inference/` — real endpoint measurement harness and strict A/B reporting.
- `ops/` — preflight, recovery, safety scripts and real CPU Kubernetes checks.
- `docs/` — architecture, operation guides, provenance, audit and acceptance roadmaps.

## Run the local Control API + Console (no GPU)

Install Docker and Compose, then:

```bash
cp .env.compose.example .env
# Set strong unique MODELOPS_PG_PASSWORD and MODELOPS_JWT_SECRET in .env.
docker compose up --build -d postgres
docker compose run --rm --no-deps api alembic upgrade head
docker compose up --build -d api console
```

The local Console is at `http://localhost:3000`; API at `http://127.0.0.1:8080`. In development, an explicitly enabled dev token may be issued with `python -m modelops.devtoken`. **The default local metadata mode rejects execution without a real backend; the explicit Linux development worker is documented in the v1 reproduction guide**; a working UI does not imply a running model. See [setup guide](docs/LOCAL_AND_PRODUCTION_SETUP.md).

### Test without GPU

```bash
cd control-plane
python -m pip install -e ".[dev]"
python -m pytest -q
cd ..
python -m unittest discover -s benchmarks/inference -p 'test_*.py' -v
```

GitHub Actions additionally exercise Operator/Helm contracts, browser API E2E, container builds and CPU-kind checks. The **Control API → actual Kubernetes CRD → Operator → scale/delete** integration test is in `control-plane/tests/test_kind_runtime_e2e.py` and runs only when a real tenant-scoped kind Operator is bootstrapped by CI. This is a **CPU software acceptance gate**, not a model-serving test.

## Validation and evidence

| Evidence tier | What it proves | What it does not prove |
|---|---|---|
| T0 — source/provenance | Auditable upstream attribution and committed implementation | Code correctness |
| T1 — static/automated | Tests, Helm manifests and basic API/browser contract behavior | End-to-end production operation |
| T2 — real CPU Kubernetes | Actual namespaced resources, controllers and service checks | GPU decoding/training or high availability |
| T3 — GPU serving | Live TTFT, TPOT, p95/p99 latency, throughput, VRAM, controlled comparison | Improved business task quality |
| T4 — GPU training | Real LoRA/QLoRA weights, independent heldout and serving promotion | Production scale/HA |
| T5 — production-like cluster | Multi-node failover, tenant isolation, operational SLO and restore drills | Permanent availability guarantees |

No unsupported production uptime, speedup, cost, model quality or GPU utilization statistics are claimed. For an up-to-date run-specific judgment, inspect [Actions](https://github.com/Benjamindaoson/ModelOps-Platform/actions) and the commit SHA. Earlier [October 11 audit](docs/PLATFORM_AUDIT_2026-10-11.md) is a dated snapshot and **understates later control-plane and console work**. Live hardware and deployment readiness remain separate acceptance requirements.

## Next acceptance gates

1. Real CI kind API/Operator/Gateway lifecycle, concurrency/reconciliation, role isolation and failure propagation.
2. Parameterized Argo Run → actual checkpoint → heldout → signed quality gate → model release with rollback.
3. **RTX 3090** controlled vLLM/SGLang comparisons with identical weights/workload and attached raw telemetry.
4. Production OIDC, DB/S3 restore drill, immutable image digests and multi-node chaos testing.

See [integration gates](docs/INTEGRATION_ROADMAP_2026-10-12.md), [training lifecycle](docs/TRAINING_JOB_LIFECYCLE.md), [verified backup design](docs/BACKUP_RECOVERY_V2.md), and [benchmark guide](benchmarks/inference/README.md).

## Open-source foundation and licensing

This project is derived from [GaeaRuiW/kube-llmops](https://github.com/GaeaRuiW/kube-llmops), pinned to commit `74f8db47fa2690a4e71ae31532f36b35a587d266`, under Apache-2.0. The inherited Operator/Helm/observability architecture is **credited, not misrepresented as original work**. The added Control API, Console and reconciliation/evidence work are separately visible in Git history. See [upstream provenance](docs/UPSTREAM_PROVENANCE.md), [original upstream README](docs/upstream/README.md), and [LICENSE](LICENSE). Audit dependency-specific licenses before commercial deployments.
