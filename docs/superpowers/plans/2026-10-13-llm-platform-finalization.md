# LLM Platform finalization execution
Authority: user's seven-phase extension; existing cloud worktree/feature branch. No subagents in side conversation; author review plus actual tests/CI. Existing receipts stay frozen.

1. Probe current Docker/NVIDIA capabilities. Implement wrapper image/Compose and executable in-container validator; record actual SKIPPED if unavailable.
2. TDD release gate: actual MLflow version/run → registered adapter/checkpoint rehash → reuse heldout quality checks → loaded serving ID → hash-bound benchmark thresholds. Defaults frozen before comparison: candidate F1>=0.55,delta>=-0.02; C4 min250 output tokens/s,TTFT P95<=200ms,E2E P95<=1200ms;128 requests x3 repeats. No lowering after outcome.
3. TDD SSE telemetry: fragmented frames, role-only tokens, terminal usage, errors. Loopback streaming proxy, real GPU samples; supply Prometheus/Grafana Compose/provisioning. Native CPU runtime checks if Docker unavailable, clearly separate Docker skip.
4. Actions: real tests/lint, GPU-image build, controlled CPU service validation and archived evidence. Never publish test fixture output as GPU benchmark.
5. Acquire existing GPU lease; run same frozen weights in bounded paired FP16 C4/C16 x3 x128 requests, seeds8400–8402 through the same observable proxy. Verify real direct/proxy outputs; save every result and stop owned processes. No new training.
6. Reorganize first screen and architecture layers, preserve upstream attribution/negative results/old evidence. Add CHANGELOG and reports.
7. Bare pytest,unittest,Console type/build/E2E,compile/Compose checks,actual Docker build in CI and final scripts. Commit with requested feat message, fast-forward existing feature branch/PR safely. No force-push or auto-merge.

Interfaces: registry IDs and immutable training hashes feed release gate; existing benchmark read_trial feeds comparison/gate; proxy exposes existing OpenAI API to official benchmark plus Prometheus metrics; all artifacts scoped to Evidence/llm-platform-finalization. Unknown GPU Docker/Grafana states remain SKIPPED, not PASS. Ledger completion needs actual tests/results.
