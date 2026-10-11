#!/usr/bin/env bash
# =============================================================================
# ModelOps Platform Backup Script
# Backs up PostgreSQL databases, MinIO model store, and Kubernetes resources
# =============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-modelops}"
BACKUP_ROOT="${BACKUP_ROOT:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/backup_${TIMESTAMP}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-modelops-backups}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

mkdir -p "${BACKUP_DIR}"

log_info "Starting ModelOps Platform backup..."
log_info "Backup directory: ${BACKUP_DIR}"

# -----------------------------------------------------------------------------
# 1. Backup Kubernetes Resources
# -----------------------------------------------------------------------------
log_info "Backing up Kubernetes resources..."

K8S_BACKUP_DIR="${BACKUP_DIR}/kubernetes"
mkdir -p "${K8S_BACKUP_DIR}"

# Backup CRDs
if kubectl api-resources --namespaced=false -o name 2>/dev/null | grep -q "modeldeployments"; then
    kubectl get crd modeldeployments.llmops.kubellmops.io llmplatforms.llmops.kubellmops.io finetuneruns.llmops.kubellmops.io \
        -o yaml > "${K8S_BACKUP_DIR}/crds.yaml" 2>/dev/null || true
fi

# Backup namespace resources
kubectl get all,configmaps,secrets,persistentvolumeclaims \
    -n "${NAMESPACE}" \
    -o yaml > "${K8S_BACKUP_DIR}/namespace_resources.yaml" 2>/dev/null || true

# Backup custom resources
kubectl get modeldeployments,llmplatforms,finetuneruns \
    -n "${NAMESPACE}" \
    -o yaml > "${K8S_BACKUP_DIR}/custom_resources.yaml" 2>/dev/null || true

# Backup Helm releases
if command -v helm &> /dev/null; then
    helm list -n "${NAMESPACE}" -o json > "${K8S_BACKUP_DIR}/helm_releases.json" 2>/dev/null || true
fi

# Backup ingresses and services
kubectl get ingress,svc -n "${NAMESPACE}" -o yaml > "${K8S_BACKUP_DIR}/services_ingresses.yaml" 2>/dev/null || true

log_info "Kubernetes resources backed up to ${K8S_BACKUP_DIR}"

# -----------------------------------------------------------------------------
# 2. Backup PostgreSQL Databases
# -----------------------------------------------------------------------------
log_info "Backing up PostgreSQL databases..."

PG_BACKUP_DIR="${BACKUP_DIR}/postgresql"
mkdir -p "${PG_BACKUP_DIR}"

PG_POD=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "${PG_POD}" ]; then
    DATABASES=("litellm" "langfuse" "dify" "dify_plugin" "mlflow")

    for DB in "${DATABASES[@]}"; do
        log_info "Backing up database: ${DB}"
        BACKUP_FILE="${PG_BACKUP_DIR}/${DB}_${TIMESTAMP}.sql.gz"

        kubectl exec -n "${NAMESPACE}" "${PG_POD}" -- \
            pg_dump -U postgres -d "${DB}" 2>/dev/null | \
            gzip > "${BACKUP_FILE}" || true

        if [ -f "${BACKUP_FILE}" ] && [ -s "${BACKUP_FILE}" ]; then
            log_info "Database ${DB} backed up: ${BACKUP_FILE}"
        else
            log_warn "Failed to backup database ${DB}"
        fi
    done
else
    log_warn "PostgreSQL pod not found, skipping database backup"
fi

# -----------------------------------------------------------------------------
# 3. Backup MinIO Model Store
# -----------------------------------------------------------------------------
log_info "Backing up MinIO model store..."

MINIO_BACKUP_DIR="${BACKUP_DIR}/minio"
mkdir -p "${MINIO_BACKUP_DIR}"

MINIO_POD=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "${MINIO_POD}" ]; then
    MINIO_USER=$(kubectl get secret -n "${NAMESPACE}" -l app.kubernetes.io/name=minio \
        -o jsonpath='{.data.MINIO_ROOT_USER}' 2>/dev/null | base64 -d || echo "minioadmin")
    MINIO_PASS=$(kubectl get secret -n "${NAMESPACE}" -l app.kubernetes.io/name=minio \
        -o jsonpath='{.data.MINIO_ROOT_PASSWORD}' 2>/dev/null | base64 -d || echo "minioadmin")

    kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- \
        mc alias set local http://localhost:9000 "${MINIO_USER}" "${MINIO_PASS}" 2>/dev/null || true

    BUCKETS=$(kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- \
        mc ls local --json 2>/dev/null | jq -r '.[].key // empty' || echo "")

    for BUCKET in ${BUCKETS}; do
        log_info "Backing up bucket: ${BUCKET}"
        kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- \
            mc mirror local/"${BUCKET}" "/tmp/backup/${BUCKET}" 2>/dev/null || true
    done

    kubectl cp "${NAMESPACE}/${MINIO_POD}:/tmp/backup/" "${MINIO_BACKUP_DIR}/" 2>/dev/null || true
    kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- rm -rf /tmp/backup 2>/dev/null || true

    log_info "MinIO data backed up to ${MINIO_BACKUP_DIR}"
else
    log_warn "MinIO pod not found, skipping model store backup"
fi

# -----------------------------------------------------------------------------
# 4. Upload to S3 (if configured)
# -----------------------------------------------------------------------------
if [ -n "${S3_BUCKET}" ]; then
    log_info "Uploading backup to S3: ${S3_BUCKET}/${S3_PREFIX}/"

    if command -v aws &> /dev/null; then
        BACKUP_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
        log_info "Backup size: ${BACKUP_SIZE}"

        aws s3 sync "${BACKUP_DIR}/" "s3://${S3_BUCKET}/${S3_PREFIX}/${TIMESTAMP}/" --storage-class STANDARD_IA
        aws s3 sync "${BACKUP_DIR}/" "s3://${S3_BUCKET}/${S3_PREFIX}/latest/" --storage-class STANDARD_IA

        log_info "Backup uploaded to S3"
    else
        log_warn "AWS CLI not found, skipping S3 upload"
    fi
fi

# -----------------------------------------------------------------------------
# 5. Create backup manifest
# -----------------------------------------------------------------------------
cat > "${BACKUP_DIR}/manifest.json" <<EOF
{
    "backup_timestamp": "${TIMESTAMP}",
    "namespace": "${NAMESPACE}",
    "backup_root": "${BACKUP_DIR}",
    "components": {
        "kubernetes": {
            "crds": "kubernetes/crds.yaml",
            "resources": "kubernetes/namespace_resources.yaml",
            "custom_resources": "kubernetes/custom_resources.yaml",
            "helm_releases": "kubernetes/helm_releases.json"
        },
        "postgresql": {
            "directory": "postgresql"
        },
        "minio": {
            "directory": "minio"
        }
    }
}
EOF

# -----------------------------------------------------------------------------
# 6. Summary
# -----------------------------------------------------------------------------
log_info "=========================================="
log_info "Backup completed successfully!"
log_info "=========================================="
log_info "Backup location: ${BACKUP_DIR}"
log_info "Timestamp: ${TIMESTAMP}"

TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
log_info "Total backup size: ${TOTAL_SIZE}"

log_info "Backed up files:"
find "${BACKUP_DIR}" -type f -exec ls -lh {} \; | awk '{print "  - " $9 " (" $5 ")}'

# Cleanup old local backups (keep last 7)
if [ -d "${BACKUP_ROOT}" ]; then
    BACKUP_COUNT=$(ls -d "${BACKUP_ROOT}"/backup_* 2>/dev/null | wc -l)
    if [ "${BACKUP_COUNT}" -gt 7 ]; then
        log_info "Cleaning up old backups (keeping last 7)..."
        ls -dt "${BACKUP_ROOT}"/backup_* | tail -n +8 | xargs rm -rf 2>/dev/null || true
    fi
fi

log_info "Done!"
