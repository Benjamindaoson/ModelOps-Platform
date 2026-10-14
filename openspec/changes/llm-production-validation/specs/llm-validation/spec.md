# LLM Production Validation
## ADDED Requirements

### Requirement: Real managed training
The existing ModelOps TrainingJob MUST execute Transformers/PEFT QLoRA against hash-verified Qwen2.5-3B-Instruct revision aa8e72537993ba99e69dfaafa59ed015b17504d1. Frozen dataset/source IDs, 32 optimizer updates, adapter, checkpoint, optimizer and RNG state MUST be real and persisted. The batch-two replacement sampler MUST NOT be described as a deterministic full epoch.
#### Scenario: Managed GPU job
- **WHEN** an owned job selects transformers and qlora
- **THEN** completion requires a verified adapter/checkpoint receipt; historical results remain unchanged

### Requirement: Registry and quality-gated lifecycle
Actual training parameters and metrics MUST be attached to MLflow Tracking and a READY model version. Independent heldout evaluation MUST retain negative results. The existing F1 >= 0.55 and delta >= -0.02 gate MUST remain unchanged. Native base → trained → rollback serving MUST have actual OpenAI-compatible responses.
#### Scenario: Quality does not improve
- **WHEN** candidate scores decline within the existing engineering threshold
- **THEN** report the decline and limited acceptance scope, not model improvement

### Requirement: Matched inference measurements
Three FP16 profiles MUST execute three repeats at concurrency 1,4,8,16,32, with 128 requests per point, fixed 256-input/64-output workload and paired seeds. Retain per-request timing, outputs, GPU power/utilization/memory, exceptions and excluded attempts. Default continuous batching MUST NOT be described as newly enabled. Publish throughput, TTFT, TPOT and end-to-end latency with correct aggregation.
#### Scenario: Interrupted or contaminated measurement
- **WHEN** a completed measurement is valid
- **THEN** reuse it by its hash
- **WHEN** another request overlaps a point
- **THEN** retain/exclude that point and rerun only the affected cell

### Requirement: Container and delivery evidence
A real Docker image MUST be built from an immutable upstream digest, with a hash-checking inference entrypoint, non-root user, private weight mount and loopback exposure. CPU build/smoke and GPU Docker execution MUST be separated. Kubernetes, AWQ comparison and larger training are excluded from the revised scope.
#### Scenario: GPU Docker runtime unavailable
- **WHEN** this rented container lacks host container authority
- **THEN** publish the real image build and CPU startup evidence, document a GPU-host command and mark GPU-container inference unvalidated

### Requirement: Auditable GitHub delivery
README, Chinese README, public-safe reports, architecture, actual MLflow screenshots and reproducible scripts MUST be committed on the existing feature branch. Never commit model weights, credentials or private training data. Preserve Git ancestry, publish the requested PR without force-push, verify CI and leave merge for review.
