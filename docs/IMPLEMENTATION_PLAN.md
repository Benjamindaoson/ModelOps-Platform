# ModelOps Platform — Implementation Plan

## 0. Strategy and source provenance

**One upstream source of truth**: `GaeaRuiW/kube-llmops`, pinned to commit `74f8db47fa2690a4e71ae31532f36b35a587d266` (Apache-2.0). Import upstream as a clean snapshot into a feature branch with its LICENSE and file-level notices intact. Document all divergence. No upstream runtime script is executed by the import process. Upstream GitHub Actions workflows are archived, not activated.

The goal is an enterprise **Model Hosting + Inference Optimization + Fine-tuning** control plane with an AI-assisted SRE copilot. Do not misrepresent rebranded upstream features as novel implementation.

### JD coverage

| Domain | Upstream starting point | Our deliverables | Evidence required |
|---|---|---|---|
| Multi-model hosting | Helm/Operator, LiteLLM, vLLM/llama.cpp/TEI | Model registry, lifecycle, vLLM/SGLang, embedding, ASR/TTS routing | Live endpoints, versioned deploys, multi-backend probes |
| Inference optimization | vLLM settings, KEDA, dashboards | Prefix/KV-cache/continuous batching/quantization A/B sweeps | P50/P95 TTFT, TPOT, tokens/s, VRAM, concurrency-goodput |
| Fine-tune workflows | FineTuneRun CRD, Argo, LLaMA-Factory, MLflow | Actual GPU LoRA/QLoRA job with evaluation, model registration and promotion | Before/after held-out metrics, checkpoints, artifact SHA, rollout |
| Reliability | K8s probes, metrics, alerts | Fault injection, rollback, rate limits, tenant policies, recovery | Deployment logs, health SLOs, restart and rollback timings |
| Operations & delivery | CLI, dashboards | Project-level roadmap, CI gates, architecture decisions, resource/cost reports | CI, release notes, incident drills, architecture records |

## 1. Ground rules

1. First reproduce one known-good upstream deployment without modifying the deployed charts. Never claim it passed until verified on hardware.
2. Distinguish `static` (lint/template), `integration` (CPU-only Kubernetes), `gpu-serving`, `gpu-training`, and `cluster-ha` tests in CI and dashboards.
3. Benchmark identical model weights, tokenizer, prompt distribution, max-output length, concurrency, warmup policy, and hardware. Report quality as well as speed.
4. Capture machine metadata: CPU, RAM, GPU model, SM capability, driver, CUDA, kernel, library/runtime/container versions and exact SHA.
5. Require artifact checksums, dataset versions, evaluation thresholds, deploy approval gates, immutable model revisions, and rollback.
6. Never record real access tokens, input prompts containing personal data, or credentials in committed logs.
7. Keep expensive multi-node/distributed training and high-availability claims explicitly unverified until measured. RTX 3090 24 GB is suited to small-model single-GPU baselines, not a proof of distributed scalability.

## 2. Milestones and acceptance gates

### M0 — Clean upstream import
- Copy pinned Apache-2.0 snapshot; retain license, AUTHORS/NOTICE files if present, and file-level headers.
- Archive upstream CI workflows under `docs/upstream-workflows/`; create project-specific gated workflows later.
- Record full upstream SHA and import metadata.
- **Gate**: imported code paths are byte-preserved except for excludes and documented provenance; verify source tree inventory.

### M1 — Baseline and trustworthy CI
- Fix install commands, container images, known dependency/Helm incompatibilities, and secure development secrets.
- CPU-only checks: Helm lint/template, operator Go tests, API mock tests, service discovery and dashboard smoke.
- Optional GPU: deploy a small open-weights model and record hardware/version metadata.
- **Gate**: CI green; Helm install/uninstall and one live OpenAI-compatible request. Clearly tag mock vs live evidence.

### M2 — Enterprise inference control plane
- Unify model records (`ModelArtifact`, `ModelDeployment`, `EngineConfig`, `DeploymentRevision`) and typed API.
- Engine adapters: vLLM / SGLang as first-class; retain TEI and llama.cpp. Embedding first, ASR/TTS adapters next.
- Implement canary, drain, authorization/tenant quotas, readiness gates, and immutable rollback.
- **Gate**: two inference engines (or clearly marked fallback to one until hardware available) with reproducible deployment and switch tests.

### M3 — Inference optimization workbench
- Build standardized loadgen and A/B benchmark scripts: input/output tokens, concurrent streams, request rates, warm/cold runs, streaming support.
- Metrics: TTFT, TPOT, E2E P50/P95/P99; request/token throughput, goodput under SLO, GPU memory, KV-cache use/hit, OOM, GPU utilization.
- Compare vLLM and SGLang where compatible; continuous batching, prefix caching, max-num-seqs, quantization AWQ/GPTQ/INT4; FP8 only when hardware truly supports it.
- **Gate**: signed JSONL/raw traces and a reproducible comparison report; wins may be negative and must not be predeclared.

### M4 — Real fine-tune-to-serve loop
- Dataset manifest, train/validation separation, data contracts, tokenization statistics, and PII/quality filters.
- LLaMA-Factory LoRA/QLoRA SFT with checkpoints/resume, gradient accumulation, seed and full parameter logging.
- Run a **real** GPU training job; register base model + adapter + validation metrics + hashes in registry/MLflow.
- On success, evaluate held-out domain tasks and promote to serving using a LoRA adapter where supported. Canary and rollback on regression.
- **Gate**: training loss + held-out quality metrics + actual trained artifact and inference smoke; no training-success claims from template-only CI.

### M5 — Availability, troubleshooting, hardening
- Prometheus + Grafana/GPU DCGM + OpenTelemetry, alerting by SLO; structured deployment/training logs.
- Inject failures (worker crash, OOM, broken model location, degraded TTFT, API key denied, rollout regression), measure detect/restore time.
- Resolve default credentials, non-root permissions, NetworkPolicy, image scanning, per-tenant quotas and secret management.
- **Gate**: failure runbooks, replayable injection tests and rollback/availability evidence. Multi-node HA is a separate optional gate.

### M6 — ModelOps Assistant (optional differentiator)
- AI-based diagnostics with read-only tracing by default, explainable recommendations, bounded changes and explicit human approval.
- Evaluate on a fixed incident corpus with verified root causes; report precision, false positives, rollback and inference overhead.
- **Gate**: agent must not autonomously alter production routing or secrets without approval; compare to rule-based baseline.

## 3. Suggested repo ownership

- `operator/`: Kubernetes reconciliation and ModelDeployment/FineTuneRun lifecycle.
- `charts/`: deployable inference/training gateway and observability components.
- `images/`: versioned operator/model-loader/resolver/training images.
- `plugins/`: dashboard (avoid UI first, prioritize actual runtime).
- `benchmarks/` (new): reproducible model serving / quality / cost measurement.
- `tests/`: unit, integration, hardware-gated end-to-end; clearly isolated.
- `docs/`: ADRs, provenance, runbooks, JD requirements mapping.
- `apps/` (later, new): typed web/API control plane if existing plugin is insufficient.

## 4. Priorities

**P0** M0/M1 (integrity and real runtime). **P1** M2/M3 (highest JD weight: inference). **P1** M4 (fine-tune and deployment integration). **P2** M5 (production reliability). **P3** M6 (AI-native differentiation).

A green Helm-template CI is NOT evidence of inference on GPU, model quality, or real fine-tuning. All claims in resume/interviews must be backed by source and reproducible measurements.
