# Base versus fine-tuned serving comparison

Actual RTX 3090, vLLM 0.10.2, FP16, identical telemetry proxy. Prefix cache **disabled for both**.
256 input / 64 forced output tokens; 128 requests per point; three repeats, seeds 8400–8402; 1,536 valid requests.
Each latency is the mean of three per-trial percentiles, not a pooled percentile. Throughput uses generated output tokens only.

| Model | Concurrency | Output tokens/s (mean ± sample SD) | TTFT P95 (ms) | E2E P95 (ms) | Peak GPU MiB (max) |
|---|---:|---:|---:|---:|---:|
| base | 4 | 292.02 ± 3.55 | 134.01 | 896.51 | 22743 |
| base | 16 | 816.76 ± 1.87 | 461.25 | 1348.24 | 22743 |
| trained | 4 | 283.17 ± 10.34 | 133.08 | 945.47 | 22743 |
| trained | 16 | 804.54 ± 14.33 | 451.68 | 1344.97 | 22743 |

The fine-tuned checkpoint is slightly slower on this matched workload. This is a serving measurement, not evidence of quality improvement.
The earlier 45-point optimization benchmark is retained separately; it uses a different cache/profile protocol and is not pooled here.

Failures before measurement (unsupported cache-reset route, missing CLI PATH) and a between-condition TIME_WAIT port check are retained privately. Completed base trials were reused after the port fix.
Every valid point retains its raw/status SHA, exact checkpoint identity and measured-source SHA. The Git revision identifies the base commit; the measured uncommitted source snapshots are archived separately.


## Reproduce / resume

```bash
python -m ops.run_model_comparison
python -m ops.summarize_model_comparison
```
Use the documented project-local CPU/GPU environments and the frozen private asset roots. Completed valid points are verified and reused.


## Evidence

[Machine-readable trial evidence](model-comparison.json). Original cloud records: `Evidence/llm-platform-finalization/comparison/`.
Model, data and weights licensing/access remain governed by the existing training evidence; no model weights are committed.
