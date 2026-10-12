# ModelOps Training Job Lifecycle (Software Gate)

This implementation provides a **first-party tenant-scoped** API/UI for
training, cancellation, status polling, and immutable retry. Argo remains the
runtime authority; PostgreSQL persists job identity, immutable arguments,
attempt ancestry and audit events. It is not a GPU SFT/QLoRA proof.

## API and behavior

| Route | Operation | Validation |
|---|---|---|
| `POST /api/v1/train-jobs` | Create Argo Workflow from per-job model/dataset/LoRA parameters | editor role, owned model/dataset, live Kubernetes |
| `GET /api/v1/train-jobs` | Tenant's most recent training runs | authenticated, Kubernetes phase is observed, not fabricated |
| `GET /api/v1/train-jobs/{id}` | Detailed observed Argo status | exact tenant, namespace, UID/name labels |
| `POST /api/v1/train-jobs/{id}/cancel` | Request Argo `spec.shutdown=Terminate` | editor role, only non-terminal, resourceVersion supplied, repeats safe |
| `POST /api/v1/train-jobs/{id}/retry` | New immutable child job and Workflow | editor role, only Failed/Error/Terminated, max five attempts |

Cancellation does **not** claim instant success; Argo must independently
confirm the terminal state. Retry creates a fresh Workflow name/UID and records
`parent_job_id` and `attempt`; it does not overwrite the failed Workflow's
PVC/logs/checkpoints. Source model, dataset and training settings remain fixed.
A user needs separate, independently approved evaluation before promoting a
retry's output.

The browser displays observed phase, original/retry lineage, start/finish
timestamps, and only enables actions permitted by observed status. If
Kubernetes is unreachable, it shows `RuntimeUnreachable` rather than
converting a previously pending job into success.

## Database upgrade

```bash
export MODELOPS_DATABASE_URL=postgresql+psycopg://...
cd control-plane
alembic upgrade head  # adds parent_job_id / attempt columns
```

Migration `0002_train_job_lifecycle` upgrades existing installations while
also accommodating clean installations on which the inherited v1 initial
migration creates tables from current ORM metadata. Back up the database
before migration; do not treat schema upgrade as a model training operation.

## Remaining acceptance requirements

The current tests cover test-only runtime objects, Argo JSON contracts,
ownership enforcement, cancellation failures and a real API/browser offline
negative path. A production-like acceptance suite must separately prove an
Argo Workflow in kind/K3s: create, inspect nodes, terminate, observe terminal
status, retry with separate PVC and checkpoint, and recover after API/DB
restart. GPU performance and model quality require real model execution.
