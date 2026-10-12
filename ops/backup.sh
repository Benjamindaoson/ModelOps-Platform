#!/usr/bin/env bash
# ModelOps backup v2: no swallowed errors, clear provenance, no Kubernetes
# Secret export and no "success" without real PostgreSQL/S3 bytes.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
: "${NAMESPACE:?Set the target Kubernetes namespace}"
: "${MODELOPS_BACKUP_S3_BUCKET:?Set an existing S3 bucket with model artifacts}"
: "${PGHOST:?Configure the PostgreSQL host}"
: "${PGPORT:?Configure the PostgreSQL port}"
: "${PGUSER:?Configure the PostgreSQL user}"
: "${PGDATABASE:?Configure the ModelOps database}"
: "${PGPASSWORD:?Inject PostgreSQL credentials through the environment}"

if [[ ! "$NAMESPACE" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]]; then
  echo "Invalid namespace" >&2
  exit 2
fi
command -v kubectl >/dev/null
command -v pg_dump >/dev/null
command -v pg_restore >/dev/null
command -v aws >/dev/null
command -v python3 >/dev/null

BACKUP_BASE="${MODELOPS_BACKUP_ROOT:-./backups}"
mkdir -p "$BACKUP_BASE"
BACKUP_BASE="$(cd "$BACKUP_BASE" && pwd)"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FINAL="$BACKUP_BASE/modelops-$NAMESPACE-$TIMESTAMP"
if [[ -e "$FINAL" ]]; then echo "Backup destination already exists" >&2; exit 3; fi
STAGING="$(mktemp -d "$BACKUP_BASE/.modelops-incomplete.XXXXXX")"
cleanup() { if [[ -n "${STAGING:-}" && -d "$STAGING" ]]; then rm -rf -- "$STAGING"; fi; }
trap cleanup EXIT

mkdir -p "$STAGING"/{postgresql,kubernetes,objects}
echo "Exporting the PostgreSQL custom-format dump..."
pg_dump --format=custom --no-owner --no-acl --file="$STAGING/postgresql/modelops.dump"
pg_restore --list "$STAGING/postgresql/modelops.dump" >/dev/null

echo "Snapshotting ModelDeployment CRDs (not Secrets, not static admin tokens)..."
kubectl get modeldeployments.llmops.kubellmops.io -n "$NAMESPACE" -o json \
  > "$STAGING/kubernetes/modeldeployments.json"
test -s "$STAGING/kubernetes/modeldeployments.json"

echo "Downloading real model objects from configured S3 bucket..."
PREFIX="${MODELOPS_BACKUP_S3_PREFIX:-}"
if [[ "$PREFIX" == *".."* || "$PREFIX" == /* ]]; then
  echo "Unsafe S3 prefix" >&2
  exit 2
fi
SOURCE="s3://$MODELOPS_BACKUP_S3_BUCKET"
if [[ -n "$PREFIX" ]]; then SOURCE="$SOURCE/$PREFIX"; fi
aws s3 sync "$SOURCE/" "$STAGING/objects/" --no-progress --only-show-errors
printf 'origin=%s\n' "$SOURCE" > "$STAGING/objects/.objects-marker"

python3 "$SCRIPT_DIR/backup_integrity.py" seal "$STAGING" \
 --namespace "$NAMESPACE" --source-bucket "$MODELOPS_BACKUP_S3_BUCKET"
python3 "$SCRIPT_DIR/backup_integrity.py" verify "$STAGING"

# Only a complete and internally verified directory is published as a backup.
mv -- "$STAGING" "$FINAL"
STAGING=""
echo "ModelOps backup verified and sealed: $FINAL"
echo "Store this directory on an encrypted offline/immutable medium."
