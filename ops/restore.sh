#!/usr/bin/env bash
# ModelOps restore v2: destructive operations require explicit approval and
# SHA-256 verification before accessing PostgreSQL or cloud storage.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP="${1:?Usage: ops/restore.sh <sealed-directory>}"
: "${NAMESPACE:?Target namespace is required}"
: "${MODELOPS_RESTORE_CONFIRM:?Set MODELOPS_RESTORE_CONFIRM=restore:<namespace>}"
: "${MODELOPS_RESTORE_S3_BUCKET:?Set explicit destination S3 bucket}"
: "${PGHOST:?Configure target PostgreSQL host}"
: "${PGPORT:?Configure target PostgreSQL port}"
: "${PGUSER:?Configure target PostgreSQL user}"
: "${PGDATABASE:?Configure target PostgreSQL database}"
: "${PGPASSWORD:?Inject PostgreSQL credentials through the environment}"

if [[ "$MODELOPS_RESTORE_CONFIRM" != "restore:$NAMESPACE" ]]; then
  echo "Explicit restore confirmation does not match target namespace" >&2
  exit 2
fi
command -v python3 >/dev/null
command -v pg_restore >/dev/null
command -v aws >/dev/null

python3 "$SCRIPT_DIR/backup_integrity.py" verify "$BACKUP"

BACKUP_NS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["namespace"])' "$BACKUP/manifest.json")"
if [[ "$BACKUP_NS" != "$NAMESPACE" ]]; then
  echo "Backup namespace does not match explicitly requested target" >&2
  exit 2
fi
SOURCE_BUCKET="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_bucket"])' "$BACKUP/manifest.json")"
if [[ "$SOURCE_BUCKET" != "$MODELOPS_RESTORE_S3_BUCKET" ]]; then
  echo "Destination bucket differs from sealed source; manual migration process required" >&2
  exit 2
fi
pg_restore --list "$BACKUP/postgresql/modelops.dump" >/dev/null

if [[ "${MODELOPS_RESTORE_DRY_RUN:-yes}" == "yes" ]]; then
  echo "DRY RUN: backup is integrity verified; no mutation performed."
  echo "Set MODELOPS_RESTORE_DRY_RUN=no and maintain an independently verified database snapshot."
  exit 0
fi
if [[ "${MODELOPS_RESTORE_ALLOW_DESTRUCTIVE:-}" != "YES" ]]; then
  echo "Refusing destructive restore without MODELOPS_RESTORE_ALLOW_DESTRUCTIVE=YES" >&2
  exit 2
fi

# Restore SQL metadata first. A failed restore aborts; never silently mark
# the process successful or continue with object-store mutations.
pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error \
  --dbname="$PGDATABASE" "$BACKUP/postgresql/modelops.dump"

# Upload only after the database restore succeeds. No sync --delete.
aws s3 sync "$BACKUP/objects/" "s3://$MODELOPS_RESTORE_S3_BUCKET/" \
  --exclude ".objects-marker" --no-progress --only-show-errors

# Kubernetes desired state is intentionally restored separately through GitOps
# or a reviewed kubectl apply. Auto-applying captured Secrets, ServiceAccount
# tokens, resourceVersion and status fields is unsafe and inconsistent.
echo "Data restored and object upload completed."
echo "Kubernetes resource reconciliation and API checks are REQUIRED before cutover."
echo "This command does not assert healthy model serving or a valid RTO."
