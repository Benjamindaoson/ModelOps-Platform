# Verified backup and restore (v2)

The older scripts allowed backup operations to fail while still printing success,
dumped namespace Kubernetes Secrets into plaintext YAML, and did not verify
PostgreSQL or object-storage artifacts before attempting restore. The new v2
scripts **fail closed** and create a sealed `manifest.json` with exact SHA-256
and byte-size entries for every backup file.

## Create a backup

Provision a PostgreSQL dump-only account, authenticated S3/AWS CLI profile,
and namespace-scoped K8s read permissions. Set `PGHOST`, `PGPORT`,
`PGUSER`, `PGDATABASE`, `PGPASSWORD`, `NAMESPACE` and
`MODELOPS_BACKUP_S3_BUCKET`. Then run:

```bash
bash ops/backup.sh
python3 ops/backup_integrity.py verify backups/modelops-<namespace>-<timestamp>
```

The backup is not considered complete until `pg_dump -Fc`, `pg_restore
--list`, `kubectl get modeldeployments`, `aws s3 sync` and the content
manifest verification all pass. Missing/empty object snapshots or truncated
PostgreSQL dumps fail. Kubernetes Secrets are **never** exported. ModelOps
objects are read-only metadata snapshots, not self-contained Kubernetes
production credentials or a runnable cluster. Encrypt snapshots at rest and
enable immutable retention off-cluster.

## Restore

Point the command at an already-sealed directory. Configuration must match
the saved namespace and S3 bucket exactly. It performs a **dry run by default**.

```bash
export MODELOPS_RESTORE_S3_BUCKET='<original source bucket>'
export MODELOPS_RESTORE_CONFIRM='restore:<namespace>'
bash ops/restore.sh '<sealed-directory>'             # verification ONLY
```

For an intentional **destructive** restore, perform a separate platform
snapshot, stop new writes to PostgreSQL and set:

```bash
MODELOPS_RESTORE_DRY_RUN=no MODELOPS_RESTORE_ALLOW_DESTRUCTIVE=YES \
  bash ops/restore.sh '<sealed-directory>'
```

`pg_restore --exit-on-error` must finish before S3 upload. This is not
transactional across PostgreSQL, S3 and Kubernetes. Independently restore
Kubernetes desired state through reviewed GitOps and verify model digests,
tenant isolation and API/Argo operational health before reopening traffic.
No backup or restore automatically establishes recovery time objectives.
