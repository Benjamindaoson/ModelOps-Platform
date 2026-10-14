# Pinned native GPU experiments

Run on the authorized Linux GPU host, from the existing ModelOps checkout. This is a native process adapter, not GPU Docker or Kubernetes validation.

Create independent project environments with Python3.12: .venv for the control-plane/MLflow/HTTP coordinator; .gpu-venv for vLLM plus PEFT training; .sglang-venv for SGLang; .quant-venv for conversion. Install each supplied requirements file only in its matching environment. The control plane uses its existing editable control-plane[dev,robotics] install plus MLflow. Do not mix the two Torch versions.

For SGLang0.4.10, the published wheel omits the eagerly compiled hf3fs_utils.cpp. The source fetch helper restores the exact official tagged file and verifies SHA256. No hf3fs filesystem is enabled. g++ and ninja are required; the adapter prepends the isolated environment's bin directory and constrains MAX_JOBS=2. This packaging repair is not a new inference kernel.

Prerequisites: the existing official Qwen2.5-3B package and Dolly64/24 manifest must verify. Base recovery uses ops.bootstrap_llm_validation_assets with docs/evidence/llm-validation/training/official-source.json. Original data selection is ops.freeze_shortqa_v1: pinned Dolly revision, selectionseed1702, closed QA, original answers<=12 tokens, original pinned qwen-base tokenizer. Verify the expected manifest SHA71a383c9cd4a77204ba0d1c65b6fd10966e6c8ba6f98c04d35ca1641e242b687 before advanced runs; never substitute a different split.

The new SQuAD validation archive is pinned to revision7b6d24c440a36b6815f21b70d25016731768db1f, size1819889 and official LFS SHA8c6646d36bd5a95061e076788cf3161d11f6f3e7d625dac7a83bbed0a49f69f7. The first observed download was truncated despite a success response; only the fully hashed and decoded archive was used. A trusted memory-only relay can transfer this same verified archive when the cloud endpoint times out, but must preserve the official hash.

Run bash deploy/llm-validation/native-hardening/reproduce.sh. Or use .venv/bin/python -m ops.run_inference_hardening --stage engines|tuning|profiling|faults|quantization|training|report. Use --stage all for the sequential GPU queue. Completed points are resumed only after content hashes match; controller and GPU leases reject duplicate workers. Never delete failed trials to improve the summary.

Exact raw prompts, outputs, samples, traces and optimizer/RNG states remain private under Evidence/inference-hardening. Public docs contain only aggregates, metadata and hashes. Current driver reports RTX4080 SUPER/CC8.9 with roughly32GiB available; older RTX3090 results are not mixed into comparisons. Results do not certify arbitrary GPU capacity, broad task quality or production business SLOs.
