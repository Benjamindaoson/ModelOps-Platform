# LLM Production Validation

## ADDED Requirements

### Requirement: Real factory training
The existing ModelOps TrainingJob MUST execute official LLaMA-Factory QLoRA against pinned Qwen2.5-3B-Instruct weights, NF4, rank 8 and alpha 16. Dataset/source IDs, immutable weight hashes, optimizer updates, Adapter and Trainer state MUST be real and persisted. Existing VLA and v1 results MUST remain unchanged.

#### Scenario: Managed factory job
- **WHEN** an owned LLM QLoRA job selects framework llamafactory
- **THEN** its observed process runs the pinned CLI and completed state requires a verified real adapter receipt

### Requirement: Quality and deployment gates
Only a candidate passing the unchanged Token-F1 and baseline-delta gates MUST become a release candidate. A true Kubernetes deployment MUST have live cluster/Pod/CRD evidence. Native loopback serving MUST NOT be called a GPU Kubernetes deployment.

#### Scenario: No cluster authority
- **WHEN** no authorized GPU cluster or writable container runtime exists
- **THEN** the cluster gate remains INCOMPLETE while independent train/eval/serve/benchmark tasks proceed

### Requirement: Matched performance experiments
The benchmark MUST execute concurrency 1,4,8,16,32 with frozen workload, precision, tokenizer, seeds and repeated trials. Baseline, batching tuning, KV tuning and same-checkpoint AWQ MUST be distinguished. vLLM default continuous batching MUST NOT be presented as newly enabled. Raw failures, streamed timing and power/utilization/memory samples MUST be retained. Quantization output changes MUST be evaluated.

#### Scenario: Publish real evidence
- **WHEN** a benchmark or phase completes
- **THEN** persist config, versions, hashes, raw result and limitations; commit code and public-safe reports on the feature branch and create the requested PR
