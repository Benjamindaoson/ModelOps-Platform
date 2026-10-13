# ModelOps inference observability
The existing vLLM API is wrapped by a CPU loopback streaming proxy. It preserves generated output, includes terminal usage for true output-token accounting, and measures first nonempty content as TTFT. No token counts are estimated from SSE frame count. Unknown GPU/usage values remain unknown.

```bash
.venv/bin/python -m ops.observability.server --upstream http://127.0.0.1:19782 --port 19780 --version MODEL_VERSION
export GRAFANA_ADMIN_PASSWORD=SET_A_STRONG_UNIQUE_VALUE
docker compose -f deploy/monitoring/docker-compose.yml up -d
```
Linux host networking is deliberately loopback-only: exporter19780,Prometheus19790,Grafana19791. Do not expose these services publicly without the existing authentication/tenant controls. No default public credentials or Kubernetes are introduced. Compose requires authorized Docker host access; if absent, native CPU runtime checks are reported separately.

Dashboard shows whole-device GPU utilization/memory/temperature, request/error rates, latency/TTFT histograms and actual output tokens/sec. Token throughput excludes missing usage rather than filling it with invented zeros. Proxy latency includes forwarding overhead. Fixed version labels avoid client-controlled label cardinality.

Official deployment sources: https://prometheus.io/docs/prometheus/latest/installation/ and https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/ . Pinned component versions: Prometheus3.15.0 and Grafana13.2.3; no claim of enterprise HA/SLO follows from a single-host run.
