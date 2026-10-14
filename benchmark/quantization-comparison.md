# Actual INT4 conversion: quality and performance

Same official Qwen2.5-3B revision,64 frozen calibration records, FP16 serving activations. Benchmark runs fix KV memory at3GiB. Statistics use three repeats/96 requests per point; peak GPU memory is NVML whole-device memory, while training allocation uses Torch separately.

|Package|Weights GB|Conversion s|Load readiness s|A C1 output tokens/s|C C32 output tokens/s|Peak MiB|QA128 F1/EM|Quality policy|
|---|---:|---:|---:|---:|---:|---:|---|---|
|fp16|6.172|Original|33.27|91.61|1903.93|10161|0.81546/0.67188|PASS|
|gptq|2.676|358.91145080800015|50.32|169.89|2988.09|6163|0.81335/0.67188|PASS|
|awq|2.676|112.78128905199992|35.24|168.41|2983.67|6173|0.73045/0.54688|FAIL|

Measured recommendations: GPTQ passes the fixed2-percentage-point F1/EM policy on both the128 QA and24 smoke groups. It is faster and uses less visible memory in the observed short/decode points. AWQ runs successfully but fails quality, so it is not a publishable candidate under this policy.

Long-context caveat: inspect B-C16/C32 TTFT/TPOT/P95/P99 in [full JSON](../docs/evidence/inference-hardening/quantization_comparison.json); quantization does not remove prefill latency, and some latency values regress. Largest tested concurrency is32; physical capacity/production SLO is not established. Startup time includes hashing/initialization/compile/readiness, not weight read time alone.

Source-pinned SQuAD128 uses48 validation article groups, revision7b6d24c440a36b6815f21b70d25016731768db1f, CC-BY-SA4.0. Existing normalized token-overlap F1/EM differs from official SQuAD scoring. Dolly24 is a separate small smoke check, not a broad non-inferiority result. Raw text and all weights remain private.
