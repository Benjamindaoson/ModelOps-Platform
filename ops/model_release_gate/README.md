# Version-bound model release gate

The CLI resolves actual MLflow model/version/run identity, rehashes adapter and checkpoint, reuses the existing independent heldout quality gate including full-package/dataset hashes, verifies the actual loaded vLLM model ID and audits repeated benchmark raw files. Missing/invalid/mismatched evidence returns FAIL.

```bash
.venv/bin/python -m ops.model_release_gate --model ModelOps-Qwen2.5-3B --version 1 \
  --base-url http://127.0.0.1:19780 \
  --comparison Evidence/llm-platform-finalization/comparison/progress.json
```

Predeclared development thresholds: F1>=0.55,delta>=-0.02; C4,128 requests x3; output>=250 tokens/s,TTFT P95<=200ms,E2E P95<=1200ms. Performance uses means of independently measured trial percentiles, not a pooled percentile. No lowering after results. Decision includes policy and evidence hashes. PASS is development release eligibility; GPU Docker/OIDC/production SLA are separate gates. A CLI failure does not promote or deploy the model. Actual successful decision hash is attached to the MLflow version.
