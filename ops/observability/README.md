# Streaming telemetry for existing vLLM

This is a loopback CPU proxy/exporter, not a replacement model server. It forwards actual completions and reports request/error counters, end-to-end latency, first nonempty content TTFT, final token usage and tokens/s. Missing usage is counted explicitly; it is not guessed from string length. GPU gauges describe the whole device, not an individual request's allocation.

```bash
.venv/bin/python -m ops.observability.server --upstream http://127.0.0.1:19782 --port 19780 --version trained
curl -fsS http://127.0.0.1:19780/metrics
```

The upstream must be a credential-free loopback HTTP origin. This diagnostic proxy has no external authentication gateway; do not expose it directly. Deploy private-network authentication and TLS before external access. A broken stream increments an error metric and does not become a successful model response.

See [Compose monitoring](../../deploy/monitoring/README.md), [actual native monitoring receipt](../../docs/evidence/llm-platform-finalization/monitoring-validation.json) and the CPU/GPU evidence separation in the final report.
