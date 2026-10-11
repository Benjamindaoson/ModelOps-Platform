# ModelOps inference benchmark

**M3 bootstrap: reproducible real-endpoint experiments.** This launcher invokes the official vLLM benchmark CLI against an OpenAI-compatible endpoint. It supports completion, chat and embedding routes, so both vLLM and compatible SGLang deployments can be compared using the same load generator.

## CPU-only command validation (no inference)

~~~bash
python benchmarks/inference/run.py --base-url http://127.0.0.1:8000 --model Qwen/example --dry-run
python -m unittest discover -s benchmarks/inference -p 'test_*.py' -v
~~~

## Real GPU serving experiment

Start a model server separately, ensure the vLLM CLI is installed, then run:

~~~bash
python benchmarks/inference/run.py \
  --base-url http://127.0.0.1:8000 \
  --model YOUR_SERVED_MODEL \
  --backend openai-chat \
  --prompts 100 --concurrency 8 --request-rate 8 \
  --input-len 512 --output-len 128 \
  --run-id first_gpu_baseline
~~~

Results are written into benchmarks/results/<run-id>/:

- manifest.json: model, backend, request pattern, environment, source revision, optional GPU snapshot;
- raw-benchmark.json: real measurements emitted by the official benchmark;
- vllm-bench.log: process output/errors;
- status.json: explicit PASS/FAIL based on process exit code **and** raw result existence.

The launcher does not invent numbers. It exits with an error if the vLLM CLI is unavailable, and its dry-run does not write any fake measurements.

## Experimental validity and safety

- Random synthetic prompts are for engineering smoke/load tests, not business task quality evaluation.
- Keep the same weights, tokenizer, input/output lengths, request distribution, seed and hardware for every A/B comparison.
- Report TTFT, TPOT, E2E latency, throughput and concurrency distribution only from actual output JSON; do not infer runtime measurements from Helm manifest defaults.
- The optional GPU snapshot records name, driver and total memory, **not peak VRAM or utilization**; collect DCGM metrics separately for those.
- Sensitive prompts or outputs should not be recorded; the command intentionally omits the optional detailed response-saving flag.
- Protect access to externally reachable model endpoints. Never pass credentials inside the URL or log access tokens.

Reference: https://docs.vllm.ai/en/latest/cli/bench/serve/
