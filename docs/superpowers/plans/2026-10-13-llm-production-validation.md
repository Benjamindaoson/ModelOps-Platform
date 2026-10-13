# LLM validation execution plan — 2026-10-13
Authority: latest explicit user scope replaces the original attached Kubernetes/LLaMA-Factory/AWQ requirements. Existing isolated cloud worktree and branch codex/llm-production-validation; public base main c339aed19c5bc24f8751d75d109f68a876ba55cf. No Windows project writes, no new repository, no parent robotics/research work.

1. Freeze official Qwen2.5-3B source files against Git/LFS hashes and use the existing Transformers/PEFT worker through ModelOps. Execute one bounded 32-update replacement-sampled QLoRA run, batch two, frozen 64/24 source-disjoint short-answer split.
2. Persist real adapter/merged checkpoint/optimizer/RNG/logs and register the actual MLflow version, parameters and metrics. Model files stay private.
3. Evaluate the same 24 heldout examples against base and trained models, keeping the unchanged F1/delta gate and all negative results.
4. Invoke native vLLM base, trained, rollback revisions and actual curl requests. No Kubernetes attempts. Distinguish single-file model identities from full-package identities.
5. Execute/resume official streamed vLLM measurements: default, token-budget and memory-budget FP16 profiles; concurrency 1/4/8/16/32, 128 requests, three repeats, fixed token workload/seeds. Audit exclusions and rehash completed raw evidence.
6. Build a real digest-pinned Docker image in authorized GitHub CI and run CPU startup smoke. Document the separate GPU Docker validation boundary and safe private model mount.
7. Export real aggregate metrics, hardware, versions, screenshots and report; update READMEs and OpenSpec status. Run relevant contracts, inspect owned process cleanup and author-review changes. Safely publish source snapshots with ancestry and correspondence, update the existing PR and verify CI. No automatic merge.

Evidence boundaries: small engineering train/heldout, not broad model quality; synthetic serving traffic, not production SLO/capacity; descriptive tuning measurements, not guaranteed acceleration; CPU image build, not GPU container execution; development authorization, not enterprise OIDC. No AWQ performance claim.
