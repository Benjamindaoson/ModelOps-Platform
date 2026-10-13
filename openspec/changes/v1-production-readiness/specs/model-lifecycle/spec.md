## ADDED Requirements

### Requirement: Explicit model and runtime identity
The platform SHALL represent LLM, VLM, VLA and embedding metadata using immutable ModelArtifact versions and SHALL distinguish native Linux execution from Kubernetes execution.
#### Scenario: Native prediction
- **WHEN** a native worker serves a registered checkpoint
- **THEN** readiness includes matching model identity and the runtime is reported as Linux.

### Requirement: Real checkpoint completion
Training jobs SHALL use observed runtime state and SHALL verify an owned checkpoint and receipt before reporting COMPLETED.
#### Scenario: Receipt missing
- **WHEN** a worker reports completion without a valid checkpoint receipt
- **THEN** the job remains unverified and SHALL NOT be reported as validated completion.

### Requirement: Domain-specific release gates
The platform SHALL require independent valid evidence before candidate promotion and SHALL NOT apply text Token-F1 to continuous-action policy qualification.
#### Scenario: Signed text score for VLA
- **WHEN** a client submits a text heldout report for a VLA artifact
- **THEN** the text attestation API rejects it and directs the client to the robotics gate.

### Requirement: Honest acceptance scope
Reports SHALL retain failures and SHALL distinguish GPU experiments, software contracts, metadata restoration and production cluster validation.
#### Scenario: Unavailable cluster
- **WHEN** the server lacks an executable Kubernetes workload runtime
- **THEN** native serving and envtest results SHALL NOT be labeled a passed GPU Kubernetes deployment.
