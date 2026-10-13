# ModelOps Platform v1 production readiness

## Intent
Integrate the existing main, SmolVLA Linux adapter and M06 gate histories. Extend the existing Control API, registry, jobs, deployment contracts, benchmark and operations modules without replacing their architecture.

## Acceptance
1. Preserve Git history and all private VLA assets.
2. Backward-compatible ModelArtifact fields and Alembic migration, tenant/API/migration tests.
3. Unified QUEUED/RUNNING/PAUSED/COMPLETED/FAILED/CANCELLED jobs with observed runtime/artifact reconciliation.
4. Real bounded GPU LLM LoRA/QLoRA training, checkpoint, held-out evaluation, registry, serving/API and rollback receipts.
5. LLM, VLA and embedding contracts; Kubernetes support is reported separately from single-host GPU validation.
6. Raw TTFT, TPOT, throughput, tail latency and GPU telemetry with pinned identities.
7. Existing OIDC/RBAC/audit/recovery enhanced with tested metrics and no fabricated production/HA claims.

## Scope
Authorized cloud server, isolated linked worktree in the existing repository. Native inline implementation; no subagents in this side conversation. Loopback validation and isolated private evidence only; do not interrupt VLA jobs.
