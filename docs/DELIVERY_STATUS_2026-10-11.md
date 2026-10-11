# ModelOps Platform — delivery evidence (2026-10-11)

## Objective

Convert the Apache-2.0-licensed `GaeaRuiW/kube-llmops` foundation into a verifiable enterprise **model hosting, inference optimization and fine-tuning platform**. Source import is separately attributed in [UPSTREAM_PROVENANCE](UPSTREAM_PROVENANCE.md). This report distinguishes **committed software**, **offline tests**, and **real GPU/cluster proof**.

## Completed in this development branch

| Area | New/adapted code | Checkpoints |
|---|---|---|
| Serving | SGLang added as a Kubernetes ModelDeployment runtime; same operator can construct vLLM, TEI and llama.cpp Pods | Go builder unit test, CRD schema tests, operator CI |
| Invalid serving config | Unknown engine rejected before generating a blank container image / port | Go unit test; controller negative path |
| FineTuneRun | Replaced the previous six no-op Argo containers with `workflowTemplateRef` to the *real* Helm-installed DAG. Added chart identity and override contract validation; mismatches fail. | Go builder/controller contract tests |
| Training provenance | New heldout dataset validation BEFORE GPU allocation, training-vs-test exact normalized prompt-overlap rejection and >=20 test samples | Python unit tests, Argo template rendering |
| LoRA/QLoRA | New CPU-based actual PEFT merge, publishes merged full weights and tokenizer; refuses empty/duplicate artifacts. | Offline validation tests only; actual GPU-produced adapter remains untested |
| Checkpoint evaluation | Transformers greedy inference on baseline and candidate; lexical token-F1 and exact-match; full artifact SHA, dataset hashes and per-example metric consistency | Offline tests with explicit test-only predictor; real GPU run required |
| Promotion safety | Quality gate verifies real metric and artifact evidence; deploy step rechecks the gate before routing changes; manual approval mode is default | Helm DAG render and Python gate tests; live canary/rollback unverified |
| Inference benchmark | vLLM official loadgen wrapper; workload provenance, actual request counts/SLO checks, timeout and GPU telemetry CSV | CLI/JSON unit tests; real endpoint measurements absent |
| A/B analysis | Compares only equivalent model, workload, hardware and benchmark-commit conditions; does not invent statistics | Synthetic fixture tests only |
| API probes | Chat, embedding, ASR and TTS OpenAI-compatible HTTP checks with response schema validation | Loopback stub HTTP tests; real ASR/TTS engines not deployed |
| Production readiness | Fail-closed credentials/config preflight; LiteLLM gateway master key and PostgreSQL password via Secrets; extra K8s kind smoke CI | Offline security/Helm CI; production security not certified |
| Runtime artifact | Non-root PyYAML + Kubectl deployment runner Docker image and GHCR publishing workflow | Image build after merge must be independently verified |

## Independent CI and real hardware distinction

- **T0 (source)**: verified all 473 upstream original Git blobs, license and attribution preserved.
- **T1 (static)**: CI runs Helm render/lint, Go operator/builder tests, Python benchmark/training gate/ops unit tests and a full Argo WorkflowTemplate render. Verify [Actions](https://github.com/Benjamindaoson/ModelOps-Platform/actions) for the commit-specific verdict.
- **T2 (CPU Kubernetes)**: separate [kind smoke workflow](../.github/workflows/modelops-kind-e2e.yml) installs a real CPU-only LiteLLM gateway and tests health; status is whatever GitHub Actions actually reports.
- **T3 (GPU Serving)**: NOT VALIDATED. No true TTFT/TPOT/VRAM/goodput improvement has been measured here.
- **T4 (GPU Training)**: NOT VALIDATED. A training pipeline implementation does not prove training weights were produced or improved.
- **T5 (high availability)**: NOT VALIDATED. Single kind or single-GPU tests cannot prove a multi-GPU/high-availability service.
- **T6 (product/AI SRE)**: In progress. No claim of full tenant isolation, independent product acceptance or autonomously self-healing production agents.

## Severity 1 production blockers

1. **Operator grants cluster-admin** via `operator/charts/kube-llmops-operator/templates/rbac.yaml`. This requires dedicated least-privilege RBAC review. Do not deploy the upstream Operator into a shared cluster.
2. **Optional addons** may have sample/default secrets (Keycloak, Langfuse, MinIO). `ops/preflight.py` rejects the insecure production sample. Replace with externally managed Secrets and verify TLS/NetworkPolicy before real prod.
3. **FineTuneRun is bound to a configured Helm WorkflowTemplate.** A per-run override for a different model, dataset, GPU profile or hyperparameter is intentionally rejected; install distinct workflow template/releases or implement safe Argo parameterization to support multi-tenant dynamic workloads.
4. **No multi-node/GPU resources were connected to this session**. Hardware-dependent gates must be run separately with raw reports rather than simulated claims.
5. **Out-of-band model data**: fine-tuning requires `train.json` and an independently prepared `heldout.jsonl`. No evaluation may silently reuse training questions.
6. **Actual serving API models** (including ASR/TTS) require real models and/or additional engine adapters. Protocol tests are not evidence of model correctness or production deployment.
7. **Quality methodology**: lexical exact-match/token F1 works for tasks with stable reference strings. Domain-specific structured/economic/scientific metrics and semantic evaluation are separate work.

## Next reproducible gates

### CPU verification

```bash
python -m pip install pytest pyyaml
python -m unittest discover -s pipelines/evaluation -p 'test_*.py' -v
python -m unittest discover -s pipelines/training -p 'test_*.py' -v
python -m unittest discover -s benchmarks/inference -p 'test_*.py' -v
python -m unittest discover -s ops -p 'test_*.py' -v
helm dependency update charts/kube-llmops-stack
helm template modelops charts/kube-llmops-stack -f charts/kube-llmops-stack/values-ci-finetune.yaml --set finetune.renderWorkflowsWithoutCRD=true > /tmp/modelops-argo.yaml
cd operator && go test ./internal/engine ./internal/builder ./internal/gateway ./internal/helmbridge ./internal/cli/...
```

### Single RTX 3090 GPU

- Record precise hardware/software versions and model revision, use one small Qwen base and independent heldout dataset.
- Run vLLM/SGLang serving and `ops/smoke.py`.
- Run `benchmarks/inference/run.py` on identical prompt lengths, output lengths, request rate and concurrency. Record TTFT/TPOT/E2E tails, output tokens/s, request success, VRAM, utilization, raw traces.
- Run LoRA/QLoRA train → merged checkpoint → independent heldout eval → quality approval → real API smoke and rollback.
- FP8 is not a suitable RTX 3090 native Tensor Core experiment; use GPU-supported formats (e.g. BF16/FP16, AWQ/INT4) for realistic comparisons.
- For multi-node HA use separate hardware and explicit chaos/failure/recovery evidence.

## Claim policy

In job interviews and résumés, explicitly distinguish imported upstream functionality from independent new work, and **never claim** production throughput, fault tolerance or GPU training results without the corresponding reproducible real-run artifact.
