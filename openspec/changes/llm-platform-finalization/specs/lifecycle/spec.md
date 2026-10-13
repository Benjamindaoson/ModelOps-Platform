# Lifecycle Finalization
## ADDED Requirements
### Requirement: Honest GPU Docker validation
A probe MUST execute nvidia-smi, CUDA availability, vLLM readiness and an actual API request inside a real GPU container. Missing Docker/NVIDIA runtime MUST emit SKIPPED with null unobserved results. Host GPU availability alone MUST NOT pass the container gate.
#### Scenario: No authorized runtime
- **WHEN** Docker/host NVIDIA runtime is unavailable
- **THEN** preserve command/error evidence and continue independent phases without permission workarounds

### Requirement: Fail-closed model release
Input model name/version MUST resolve to actual MLflow version/run identity. Checkpoint and adapter bytes MUST match registered training hashes; heldout must be independent and unchanged quality thresholds pass. Health/model identity and hash-bound repeated benchmark evidence MUST meet declared thresholds. Missing, stale, nonfinite or mismatched evidence MUST yield FAIL. Decision includes policy and evidence hashes and is not an enterprise OIDC approval.
#### Scenario: Swapped or unhealthy serving
- **WHEN** health succeeds but loaded model differs
- **THEN** release fails

### Requirement: Observable streaming serving
A loopback proxy/exporter MUST preserve generated output while recording true request/error counts, duration, first nonempty token latency and usage-derived output token count. Unknown usage/GPU metrics MUST remain unknown. Compose must configure Prometheus, Grafana and provisioning without Kubernetes or public default credentials.
#### Scenario: Partial SSE events
- **WHEN** frames arrive fragmented or contain role-only/usage-only messages
- **THEN** accumulate frames and measure tokens without counting protocol frames as content tokens

### Requirement: Matched performance and evidence
Freeze FP16, workload 256/64, default server settings, concurrency4/16,128 requests,3 repeated paired seeds8400–8402 before executing base and trained models. Retain every attempt, raw timings and GPU samples; resume verified complete cells only. No quality/speedup/production-SLO claim follows automatically.
#### Scenario: Publish
- **WHEN** stages finish
- **THEN** persist independent status, versions/config/seeds/hash and runtime logs; distinguish CPU software checks from true GPU/container evidence
