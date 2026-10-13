# LLM validation execution plan — 2026-10-13

Authority: user attached Complete Delivery Task; OpenSpec change llm-production-validation. Existing isolated cloud worktree, new branch codex/llm-production-validation. Published base main c339aed19c5bc24f8751d75d109f68a876ba55cf; exact base source tree a4b2e5a1fa9057f3c0e479c8338727fc8667635b. No Windows project writes, no new repository, no parent research work.

1. Freeze official 3B model and factory versions; add managed factory selection, real worker receipt and recipe through RED/GREEN tests; run 32 bounded QLoRA updates on frozen 64/24 short-answer split (one epoch-equivalent, batch two).
2. Register true adapter/merged checkpoint automatically with training/evaluation lineage; verify all shard identities.
3. Evaluate frozen heldout, unchanged F1>=0.55 and delta>=-0.02; retain failures; no unbounded training or sample search.
4. Reuse native deployment controller, call actual chat API and rollback. Inspect authorized Kubernetes path; record actual external blocker if absent. Never remount cgroups or invent Pod evidence.
5. Reuse official vLLM benchmark and add resumable matrix 1/4/8/16/32, 128 requests per point, 3 repeats, fixed 256-input/64-output token workload. Persist GPU memory/utilization/power and per-request results.
6. Four matched profiles: FP16 default scheduling/KV settings (common loopback/model-context bounds), batching-budget tuning, GPU KV budget tuning, AWQ of the same trained checkpoint. Verify quantized outputs on heldout. No max-capacity/SLO claims from finite samples.
7. Generate public evidence reports and private full receipts with config/seed/version/hash; each phase independently committed.
8. Update README and README.zh-CN, architecture and precise implemented/validated/open status.
9. Publish all feature commits with safe non-force ancestry, create PR feat: add LLM production validation pipeline, run full CI; do not automatically merge this new PR.

Pre-flight interfaces: frozen files→factory worker→verified result.json→TrainingStateReconciler; heldout evaluation→existing registry/release gate; immutable candidate→existing vLLM runtime→official streamed benchmark; private raw artifacts→public aggregate export. Each producer/consumer keeps hashes and run IDs. Review focus: malformed metadata, shard omissions, false completion, disjoint data, workload drift, short output, state/precision mismatch, unknown process ownership, accidental credentials/public weights.
