# ModelOps durable resource recovery

**Risk addressed:** Kubernetes cannot join a PostgreSQL transaction.
If a CREATE succeeded but its HTTP response was lost, rolling back SQL
metadata would leave an unowned, untraceable Kubernetes resource. The platform
now commits immutable deployment/training identity and audit records before
submitting to Kubernetes. The response is only marked `requested` once
the matching resource is confirmed.

Both `POST /api/v1/deployments/{id}/recover` and
`POST /api/v1/train-jobs/{id}/recover` are editor-authorized repair actions.
They look up the same Kubernetes name and verify owner annotations or Argo
labels, source revision, dataset checksum, and immutable record IDs. Unknown
or foreign resources are **not** modified. They never return a fabricated
Ready or training Succeeded state.

### Periodic recovery worker

Run a single tenant-scoped recovery process with the same PostgreSQL database
and a restricted Kubernetes ServiceAccount (only get/create ModelDeployments
and Workflows in `modelops-<tenant>`). Example:

```bash
export MODELOPS_RUNTIME=kubernetes
export MODELOPS_RECOVERY_TENANT=tenant1
export MODELOPS_DATABASE_URL=postgresql+psycopg://...
python -m modelops.recover
```

A Kubernetes CronJob template is provided at
`ops/k8s/modelops-recovery-cronjob.yaml`. Set the image to the built and
signed Control API image and SecretRefs to a scoped PostgreSQL connection.
Do not mount cluster-admin credentials or share recovery workers across
tenant namespaces.

The worker scans only `submitting`/`runtime_unknown` records, at most 100
at a time, and only recreates genuinely absent objects. Existing matching
resources are adopted without a duplicate CREATE. Unreachable API servers
retain the intent for later recovery and return non-zero for operators.

### Boundaries

This is a **durable create/adopt workflow**, not a full distributed
transaction across Postgres and Kubernetes. Scale, rollout, Canary changes,
delete and release updates still need an outbox transaction log and
compensation logic; the worker deliberately does not rewrite them.
NetworkPolicy, Postgres backups, admission controls and real recovery
fault injection remain production acceptance gates.
