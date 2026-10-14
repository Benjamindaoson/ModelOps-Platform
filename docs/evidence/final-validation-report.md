# ModelOps LLM production validation — final evidence report

**Result: single-host LLM lifecycle and software validation passed; GPU Docker execution is SKIPPED on the current host.** This is a reproducible production-validation platform, with an explicit remaining runtime gate. It is not a claim of completed enterprise production deployment.

## 1. Completed features

- Preserved the actual Qwen2.5-3B-Instruct QLoRA run, checkpoint, adapter, MLflow version, independent heldout evaluation and native rollback receipts.
- Added a version-resolved, fail-closed release gate for artifact integrity, evaluation, serving identity and repeated benchmark thresholds.
- Implemented a digest-pinned non-root GPU Docker image, GPU Compose entrypoint and real CUDA/API probe. Actual GPU Docker execution remains unavailable on this rented container.
- Added streaming telemetry, GPU gauges, Prometheus/Grafana configuration and actual native runtime checks.
- Ran a matched Base versus fine-tuned model comparison: 12 trials and 1,536 genuine GPU inference requests.
- Extended default CPU validation coverage and verified the Next.js production build against an actual isolated FastAPI browser flow.
- Added GitHub Actions for software checks, actual monitoring Compose contracts, image build/startup and evidence uploads.
- Updated English/Chinese positioning, source-backed architecture and changelog while preserving upstream documentation.

## 2. Evidence matrix

| Capability | Evidence | Result / scope |
|---|---|---|
| GPU QLoRA | [Training metrics](../../experiments/training/metrics.json) | Prior genuine RTX3090 run reused; 32 updates, 14,966,784 trainable parameters. No new training. |
| Registry | [MLflow receipts](llm-validation/) | ModelOps run 7859def0-8be7-4931-a099-1193b790e709; MLflow b127f8d1474b414db0025df3a611d5c7; ModelOps-Qwen2.5-3B v1 READY. |
| Independent evaluation | [Prior full report](../modelops-validation-report.md) | 24 source-disjoint examples; F1 0.763198 → 0.749309; delta −0.013889. Unchanged gate passed; quality declined. |
| Version release | [Actual decision](llm-platform-finalization/release_decision.json) | PASS: checkpoint/adapter hashes, training/evaluation lineage, live loaded-model identity and three repeated C4 measurements. |
| Native serving / rollback | [Prior evidence](llm-validation/) | Actual base → trained → base API responses. Preserved rather than repeated. |
| Matched performance | [Comparison report](../../benchmark/model-comparison.md) / [raw summary](../../benchmark/model-comparison.json) | 1,536 requests, FP16, equal cache-disabled configuration, C4/C16, three repeats. |
| Live GPU monitoring | [Actual native receipt](llm-platform-finalization/monitoring-validation.json) | Two genuine model requests, Prometheus scrape/query results, GPU gauges, loaded Grafana dashboard. |
| Monitoring binaries | [Official hash receipts](llm-platform-finalization/monitoring-binaries.json) | Prometheus 3.15.0 and Grafana OSS 13.2.3, verified archives and executables. |
| GPU Docker | [Host/probe receipt](gpu-runtime-validation/validation-report.md) | **SKIPPED**, no Docker host/runtime. Native vLLM is not a substitute. |
| Python software | [Original log hashes/tails](llm-platform-finalization/test-evidence.json) | 467 pytest passed, 2 optional tests skipped, 4 unittest subtests; 62 unittest tests passed. |
| Frontend runtime | [Console receipt](llm-platform-finalization/console-validation.json) | Typecheck, production build and 3 Playwright tests passed against real isolated metadata API. |
| Architecture | [Source-pinned receipt](llm-platform-finalization/architecture-receipt.json) | 9/9 checks, zero composition errors/warnings; browser checks and visual inspection. |
| GitHub CI / Docker build | [Workflow](../../.github/workflows/modelops-validation.yml) | Run 38389379022 **PASS**, actual image digest 18acfc415630…54b96 and Compose contract. See [downloaded CI receipts](llm-platform-finalization/ci-validation.json); GPU execution remains SKIPPED. |

### Actual matched performance

| Model | Concurrency | Output tokens/s | TTFT P95 ms | E2E P95 ms | Peak GPU MiB |
|---|---:|---:|---:|---:|---:|
| Base | 4 | 292.02 | 134.01 | 896.51 | 22,743 |
| Fine-tuned | 4 | 283.17 | 133.08 | 945.47 | 22,743 |
| Base | 16 | 816.76 | 461.25 | 1,348.24 | 22,743 |
| Fine-tuned | 16 | 804.54 | 451.68 | 1,344.97 | 22,743 |

Values are means of three independently measured trial summaries. P95 values are **means of per-trial percentiles**, not pooled request percentiles. The model comparison does not demonstrate throughput or quality improvement. The earlier 45-point optimization benchmark used a different cache/profile protocol and remains separate.

### Frozen release thresholds

F1 ≥ 0.55; F1 delta ≥ −0.02; 24 source-disjoint evaluation samples; trained C4, 3 × 128 completed requests; generated output ≥ 250 tokens/s; TTFT P95 ≤ 200 ms; E2E P95 ≤ 1,200 ms. These were fixed before new benchmark measurement. The release gate passed at the recorded live-check time. The GPU server was subsequently stopped to avoid idle occupancy.

## 3. Known limitations

1. Current host: RTX 3090 24GB, driver 580.173.02, 12 visible logical CPUs and approximately 47.10 GiB RAM. NVIDIA CUDA is available; Docker GPU runtime is absent and cgroup/node capabilities are restricted.
2. A Docker build and CPU startup contract are not GPU container validation. The remaining gate requires an already authorized NVIDIA Container Toolkit host; no Kubernetes cluster or new paid resource is created.
3. The short training run and 24-example heldout set prove lifecycle execution, not useful adaptation or generalization. The observed quality decline is retained.
4. Synthetic inference workload is not production traffic. Three sequential repeats on one GPU do not establish multi-host or cross-day stability.
5. Whole-device GPU utilization/memory are not per-request metrics. No financial savings or invoice-derived GPU cost is claimed.
6. Native diagnostic services are loopback-only. Native Grafana permits loopback Viewer inspection; production Compose disables anonymous access and requires a strong password. External TLS/OIDC, enterprise tenancy and HA need separate validation.
7. Legacy Dify/cluster deployment scripts were not imported as unit tests: they perform unrelated external operations and remain separate explicit workflows.
8. Original cloud source commits and API-published GitHub commits have different parent/author metadata but identical verified trees. The publication receipt records that mapping; no force-push or history rewrite was used.

## 4. Reproduction guide

From an authorized Linux checkout, use separate project-local CPU and GPU environments. Install CPU dependencies in `.venv`; keep torch/vLLM in `.gpu-venv`. Dataset, weights and caches remain private under project directories.

```bash
# CPU contracts and frontend
.venv/bin/python -m pytest -q --tb=short
.venv/bin/python -m unittest discover -s ops -p 'test_*.py'
cd console && npm ci && npm run typecheck && npm run build && cd ..

# Resume completed hash-bound comparison without duplicating valid points
.venv/bin/python -m ops.run_model_comparison
.venv/bin/python -m ops.summarize_model_comparison

# Native monitoring, after verifying official binaries
.venv/bin/python -m ops.bootstrap_monitoring
.venv/bin/python -m ops.native_monitoring
# Bounded real GPU probe; successful saved receipt is reused
.venv/bin/python -m ops.validate_live_monitoring

# GPU Docker: ONLY on an authorized NVIDIA Container Toolkit host
docker compose -f deploy/llm-validation/gpu-runtime/docker-compose.gpu.yml up --build
```

Supply the documented private model mount, exact checkpoint SHA and UID10001-writable evidence directory; see [GPU runtime guide](../../deploy/llm-validation/gpu-runtime/README.md). The runtime probe must actually pass nvidia-smi, CUDA, vLLM readiness and a real API request before that gate is reported PASS.

CPU CI uses a named synthetic API fixture to validate actual Compose monitoring. It is never included in the GPU inference totals or model-quality evidence.

## Durable locations

Cloud source: `/data/ModelOps-Platform/tmp/v1-production-readiness`.
Private original logs: `Evidence/llm-platform-finalization/`.
Prior immutable assets: `Evidence/llm-production-validation/`.
Public reports: `docs/evidence/` and `benchmark/`.
Credentials, weights, cache downloads and raw request logs are excluded from Git.

## Publication verification

Core source commit: [d37241eb](https://github.com/Benjamindaoson/ModelOps-Platform/commit/d37241eb32183afda7affa7ff4df525dee6ac2fb). Full CI: [38389379022](https://github.com/Benjamindaoson/ModelOps-Platform/actions/runs/38389379022). Exact downloaded artifact receipts and archive SHA-256 values are retained in ci-validation.json. Image sources are unchanged by the later documentation and CI cache-policy edit.
