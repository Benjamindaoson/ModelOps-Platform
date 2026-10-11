# JD-to-code traceability — ModelOps Platform

The user’s target role is an enterprise model-hosting, inference-optimization, fine-tuning and delivery lead. This matrix maps each responsibility to existing inherited code and the concrete ModelOps changes/evidence still required. **Inherited** does not mean production-validated.

| JD requirement | Existing source entry point | Actual gap / next change | Proof required |
|---|---|---|---|
| Multi-hardware model hosting | operator/internal/controller/modeldeployment_controller.go; operator/internal/builder/; charts/kube-llmops-stack/charts/vllm/ | API model/engine manifest validation, immutable revisions, GPU/CPU scheduling policy, unsupported-hardware errors | Live versioned model launch on a real node |
| Multiple model families (LLM, embedding, STT, TTS) | charts/kube-llmops-stack/charts/tei/; charts/kube-llmops-stack/charts/litellm/; charts/kube-llmops-stack/charts/vllm/ | ASR/TTS engine adapter and routing (not currently verified), each with model-type schema and smoke tests | One live endpoint per model type with distinct request/response contracts |
| vLLM / SGLang / TensorRT-LLM | charts/kube-llmops-stack/charts/vllm/; charts/kube-llmops-stack/charts/sglang/ | Compare backends on same model/hardware; TensorRT-LLM integration if compatible with target hardware | Engine startup logs, exact image revisions, measured comparison |
| Quantization / KV caching / batching | vLLM chart engineArgs; model-resolution logic; serving configuration | Controlled AWQ/GPTQ/INT4, continuous batching, prefix cache sweeps. FP8 only on supporting GPUs | TTFT, TPOT, latency tail, tokens/s, concurrency and quality tradeoffs |
| Serving observability | charts/kube-llmops-stack/charts/observability/; dashboards/; benchmarks/inference/run.py | Merge GPU telemetry, service metrics and request traces into a reproducible run ID; produce optimization reports | Raw Prometheus/DCGM/benchmark traces and replay steps |
| Reliability / scaling / security | charts/kube-llmops-stack/charts/keda/; charts/kube-llmops-stack/charts/security/; operator controllers | Replace development default credentials, add fault injection, canary/rollback test, SLOs, tenant quota enforcement | Health, recovery, rollback and access-control test evidence |
| Domain fine-tuning | operator/internal/controller/finetunerun_controller.go; charts/kube-llmops-stack/charts/finetune/templates/workflow.yaml | Actual LoRA/QLoRA GPU job, dataset contract and splits, resume, independent quality evaluation | Training run ID, model artifacts SHA, held-out eval and GPU utilization |
| Training → deployment promotion | finetune workflow's merge-upload / evaluate / quality-gate / deploy DAG | Explicit model registry state, version, quality acceptance and deployment promotion with rollback | New model or LoRA adapter served, smoke-verified, rollback exercised |
| Performance benchmark and incident response | tests/helm/; benchmarks/inference/; charts/observability/ | Stable SLO workload profiles, cold/warm consistency, TTR, OOM and degraded TTFT incident replay | Raw traces, baseline/variant deltas, signed source revisions |
| AI-native engineering | AGENTS.md and modelops implementation gates | Optional read-only Agent for diagnostics, recommending safe policy changes with approval | Root-cause and action correctness on held-out incidents |
| Team leadership and delivery ownership | docs/IMPLEMENTATION_PLAN.md and repository Git history | ADRs, delivery gates, release responsibilities, technical reviews; actual people-management experience cannot be inferred from code | Roadmap, ownership, PR reviews, release/incident retrospectives |

## Engineering evidence tiers

- **T0 import**: Git blobs and license verified.
- **T1 static**: Helm/YAML/test contracts passing on CI.
- **T2 integrated runtime**: CPU-only Kubernetes deployment and model gateway API working.
- **T3 GPU serving**: actual GPU server, workload, TTFT/TPOT, VRAM/throughput.
- **T4 GPU training**: real LoRA/QLoRA weights, held-out evaluation, registry and serving.
- **T5 cluster**: replicated/multi-GPU high availability and chaos recovery.
- **T6 product**: secure self-service workflows with independent user acceptance.

Never describe a T1 chart or controller test as T3–T5 proof.

## Next code change sequence

1. **M1** Secure service configuration, keep offline tests green, then reproduce CPU-kind deployment and live gateway smoke.
2. **M2** Finalize ModelDeployment model types/revisions, vLLM and SGLang service adapters, Helm values contract, and canary lifecycle.
3. **M3** Benchmark chat and embeddings against live endpoints, capture GPU utilization/DCGM alongside vLLM raw reports; add controlled quantization/cache/batch experiment grid.
4. **M4** Execute and verify real LLaMA-Factory LoRA/QLoRA in a GPU-enabled environment; publish adapter/model artifacts with evaluation and release gates.
5. **M5** Harden tenant isolation, quotas, SLOs, failure recovery and rollback; demonstrate separate small-node and multi-node tests where actually run.
6. **M6** Optionally build an explainable operations Agent only after trusted performance and failure signals exist.
