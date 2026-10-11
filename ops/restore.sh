#!/usr/bin/env bash
# =============================================================================
# ModelOps Platform Restore Script
# Restores PostgreSQL databases, MinIO model store, and Kubernetes resources
# =============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-modelops}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-modelops-backups}"
BACKUP_DIR="${1:-}"

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

# Check arguments
if [ -z "${BACKUP_DIR}" ]; then
    echo "Usage: $0 <backup_directory_or_s3_uri> [options]"
    echo ""
    echo "Arguments:"
    echo "  backup_directory_or_s3_uri  Local backup directory or S3 URI (s3://bucket/path)"
    echo ""
    echo "Environment variables:"
    echo "  NAMESPACE     Kubernetes namespace (default: modelops)"
    echo "  S3_BUCKET     S3 bucket for remote backups"
    echo "  S3_PREFIX     S3 prefix for backups"
    echo ""
    echo "Examples:"
    echo "  $0 ./backups/backup_20241011"
    echo "  $0 s3://my-bucket/modelops-backups/backup_20241011"
    exit 1
fi

# Handle S3 URIs
if [[ "${BACKUP_DIR}" == s3://* ]]; then
    log_info "Downloading backup from S3..."
    TEMP_DIR=$(mktemp -d)
    if command -v aws &> /dev/null; then
        aws s3 sync "${BACKUP_DIR}" "${TEMP_DIR}/"
        BACKUP_DIR="${TEMP_DIR}"
    else
        log_error "AWS CLI not found. Cannot download from S3."
        exit 1
    fi
fi

# Verify backup directory exists
if [ ! -d "${BACKUP_DIR}" ]; then
    log_error "Backup directory not found: ${BACKUP_DIR}"
    exit 1
fi

# Check for manifest
MANIFEST="${BACKUP_DIR}/manifest.json"
if [ ! -f "${MANIFEST}" ]; then
    log_warn "Manifest not found. Attempting manual restore..."
else
    log_info "Reading manifest..."
    cat "${MANIFEST}"
fi

log_info "Starting ModelOps Platform restore..."
log_info "Backup directory: ${BACKUP_DIR}"
log_info "Target namespace: ${NAMESPACE}"

# Confirmation prompt
read -p "This will restore resources to namespace '${NAMESPACE}'. Continue? (yes/no) " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    log_info "Restore cancelled."
    exit 0
fi

# -----------------------------------------------------------------------------
# 1. Restore Kubernetes Resources
# -----------------------------------------------------------------------------
log_info "Restoring Kubernetes resources..."

K8S_BACKUP="${BACKUP_DIR}/kubernetes"
if [ -d "${K8S_BACKUP}" ]; then
    # Restore CRDs (if they don't exist)
    if [ -f "${K8S_BACKUP}/crds.yaml" ]; then
        log_info "Restoring CRDs..."
        kubectl apply -f "${K8S_BACKUP}/crds.yaml" --server-side 2>/dev/null || true
    fi

    # Restore custom resources
    if [ -f "${K8S_BACKUP}/custom_resources.yaml" ]; then
        log_info "Restoring custom resources (ModelDeployments, LLMPlatforms, FineTuneRuns)..."
        kubectl apply -f "${K8S_BACKUP}/custom_resources.yaml" -n "${NAMESPACE}" 2>/dev/null || true
    fi

    # Restore namespace resources (configmaps, secrets, pvcs)
    if [ -f "${K8S_BACKUP}/namespace_resources.yaml" ]; then
        log_info "Restoring namespace resources..."
        kubectl apply -f "${K8S_BACKUP}/namespace_resources.yaml" -n "${NAMESPACE}" 2>/dev/null || true
    fi

    log_info "Kubernetes resources restored"
else
    log_warn "Kubernetes backup directory not found, skipping..."
fi

# -----------------------------------------------------------------------------
# 2. Restore PostgreSQL Databases
# -----------------------------------------------------------------------------
log_info "Restoring PostgreSQL databases..."

PG_BACKUP="${BACKUP_DIR}/postgresql"
if [ -d "${PG_BACKUP}" ]; then
    PG_POD=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=postgresql -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -n "${PG_POD}" ]; then
        for DUMP_FILE in "${PG_BACKUP}"/*.sql.gz; do
            if [ -f "${DUMP_FILE}" ]; then
                DB_NAME=$(basename "${DUMP_FILE}" | sed 's/_[0-9]*_[0-9]*\.sql\.gz$//')
                log_info "Restoring database: ${DB_NAME}"

                # Create database if it doesn't exist
                kubectl exec -n "${NAMESPACE}" "${PG_POD}" -- \
                    psql -U postgres -c "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | \
                    grep -q 1 || \
                    kubectl exec -n "${NAMESPACE}" "${PG_POD}" -- \
                        psql -U postgres -c "CREATE DATABASE ${DB_NAME}" 2>/dev/null || true

                # Restore data
                gunzip -c "${DUMP_FILE}" | \
                    kubectl exec -i -n "${NAMESPACE}" "${PG_POD}" -- \
                    psql -U postgres -d "${DB_NAME}" 2>/dev/null || true

                log_info "Database ${DB_NAME} restored"
            fi
        done
    else
        log_warn "PostgreSQL pod not found, skipping database restore"
    fi
else
    log_warn "PostgreSQL backup directory not found, skipping..."
fi

# -----------------------------------------------------------------------------
# 3. Restore MinIO Model Store
# -----------------------------------------------------------------------------
log_info "Restoring MinIO model store..."

MINIO_BACKUP="${BACKUP_DIR}/minio"
if [ -d "${MINIO_BACKUP}" ] && [ "$(ls -A "${MINIO_BACKUP}" 2>/dev/null)" ]; then
    MINIO_POD=$(kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [ -n "${MINIO_POD}" ]; then
        MINIO_USER=$(kubectl get secret -n "${NAMESPACE}" -l app.kubernetes.io/name=minio \
            -o jsonpath='{.data.MINIO_ROOT_USER}' 2>/dev/null | base64 -d || echo "minioadmin")
        MINIO_PASS=$(kubectl get secret -n "${NAMESPACE}" -l app.kubernetes.io/name=minio \
            -o jsonpath='{.data.MINIO_ROOT_PASSWORD}' 2>/dev/null | base64 -d || echo "minioadmin")

        kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- \
            mc alias set local http://localhost:9000 "${MINIO_USER}" "${MINIO_PASS}" 2>/dev/null || true

        for BUCKET_DIR in "${MINIO_BACKUP}"/*; do
            if [ -d "${BUCKET_DIR}" ]; then
                BUCKET_NAME=$(basename "${BUCKET_DIR}")
                log_info "Restoring bucket: ${BUCKET_NAME}"

                kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- \
                    mc mb local/"${BUCKET_NAME}" 2>/dev/null || true

                kubectl exec -n "${NAMESPACE}" "${MINIO_POD}" -- \
                    mc cp --recursive "${BUCKET_DIR}/" "local/${BUCKET_NAME}/" 2>/dev/null || true

                log_info "Bucket ${BUCKET_NAME} restored"
            fi
        done
    else
        log_warn "MinIO pod not found, skipping model store restore"
    fi
else
    log_warn "MinIO backup directory not found or empty, skipping..."
fi

# -----------------------------------------------------------------------------
# 4. Restore Helm Releases (if helm is available)
# -----------------------------------------------------------------------------
log_info "Checking Helm releases..."

HELM_BACKUP="${BACKUP_DIR}/kubernetes/helm_releases.json"
if [ -f "${HELM_BACKUP}" ] && command -v helm &> /dev/null; then
    log_info "Helm releases backup found. Please manually restore with:"
    echo "  helm values <release> -n ${NAMESPACE} > values.yaml"
    echo "  helm upgrade <release> <chart> -n ${NAMESPACE} -f values.yaml"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
log_info "=========================================="
log_info "Restore completed!"
log_info "=========================================="
log_info "Please verify the following:"
log_info "1. All pods are running: kubectl get pods -n ${NAMESPACE}"
log_info "2. Custom resources are ready: kubectl get md,lp,ftr -n ${NAMESPACE}"
log_info "3. Database connections are working"
log_info "4. MinIO data is accessible"

# Cleanup temp directory if created from S3
if [[ "${BACKUP_DIR}" == /tmp/* ]] && [[ "${BACKUP_DIR}" != ./backups/* ]]; then
    log_info "Cleaning up temporary directory..."
    rm -rf "${BACKUP_DIR}"
fi

log_info "Done!"
