# Advanced ModelOps execution

Use current worktree/branch/PR25. Inline TDD, actual sequential GPU experiments, per-trial immutable receipts and resume. Preserve all historical checkpoints and negative results. No subagents in this side conversation. Existing architecture reused; no new UI/diagram/K8s. Separate .gpu-venv / .sglang-venv / .quant-venv dependencies.

Frozen serving baseline: Qwen2.5-3B-Instruct aa8e7253 package/tokenizer, FP16. Exact tokenized completions, no chat template transformation during throughput workload; quality uses frozen chat template. Workloads256->64,2048->128,512->512; concurrency1/4/8/16/32;3 repeats;32 requests/point;3 warmups. Same sampling seed and prompt manifest across engines, ignore EOS and validate actual input/output lengths. Prefix cache off baseline. Memory fractions0.70,context4096,max_sequences64. All deviations ledgered before measurements. No pooling old RTX3090 results.

Engineering-only matched quality thresholds: delta F1 and EM >= -0.02; no business SLO. Reject missing telemetry/error/changed source/hash. Training two controlled configs, genuine optimizer/scheduler/RNG resume checked against independent uninterrupted run. Public docs/evidence/inference-hardening; private Evidence/inference-hardening. Review manually, do not merge main.
