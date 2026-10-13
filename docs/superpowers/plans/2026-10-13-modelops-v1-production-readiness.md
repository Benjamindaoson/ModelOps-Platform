# ModelOps v1 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Steps use checkbox syntax. No subagents in this side conversation.

**Goal:** Unify and verify the existing enterprise AI lifecycle platform with real GPU evidence.

**Architecture:** Preserve FastAPI/SQLAlchemy, Go Operator/CRDs, Helm/Argo and the Linux robotics adapter. Add backward-compatible artifact metadata and runtime-aware lifecycle reconciliation. Keep weights and raw measurements private and separate from tracked source.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, LeRobot/Transformers/PEFT, Go, Helm, PostgreSQL, MLflow.

**Spec:** openspec/changes/v1-production-readiness/proposal.md and the user-approved seven-phase sprint requirements.

## Global Constraints
No new repository or product redesign; preserve branch histories, licensing, private assets and checkpoint hashes. No fabricated experiments. Tests and raw GPU experiments are separate gates. All changes are cloud-local until safe reviewed GitHub synchronization.

## Review Focus
Tenant cross-access, stale terminal states, mismatched checkpoint/evaluation identities, missing/damaged artifacts, unsupported engine/model combinations and rollback safety.

## Tasks
- [ ] Phase 1: Audit branch ancestry; merge both robotics histories into the current main base; run baseline suites; update README and architecture evidence.
- [ ] Phase 2: Add ModelArtifact metadata to existing model-version storage with migration and backward-compatible API tests.
- [ ] Phase 3: Add TrainingStateReconciler and Linux worker binding; tests must reject false completion and reconcile stale states.
- [ ] Phase 4: Add bounded Qwen SFT/QLoRA configs and real training/evaluation/publication runner; freeze model/data/config/seed/checkpoint receipts.
- [ ] Phase 5: Extend existing CRD and engine contracts for custom VLA serving; run real loopback candidate API and rollback; validate LLM/VLA/embedding support separately.
- [ ] Phase 6: Extend existing inference harness to emit model/hardware/config/result/report with genuine streaming and GPU telemetry.
- [ ] Phase 7: Test OIDC/RBAC/tenant/audit/backup/restore/reconciliation and Prometheus metrics; run final runtime checks and commit all source.

Each behavior change follows RED -> GREEN -> project regression suite. Each phase records commands, exit codes, artifacts, hashes, limitations and commit in Evidence/v1 and docs/v1/ledger.md. Integrate to main only after final checks; never force-push.
