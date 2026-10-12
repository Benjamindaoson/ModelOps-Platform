#!/usr/bin/env bash
# Authorized cluster-bootstrap operation, NOT invoked from a tenant Web/API pod.
set -euo pipefail

TENANT="$1"
if [[ ! "$TENANT" =~ ^[a-z][a-z0-9-]{0,38}[a-z0-9]$ ]]; then
  echo "Tenant must be a lowercase Kubernetes-safe 2-40 character slug" >&2
  exit 2
fi
NAMESPACE="modelops-$TENANT"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHART="$ROOT/charts/kube-llmops-stack/charts/finetune"
: "$MODELOPS_MLFLOW_URI"
if [[ ! "$MODELOPS_MLFLOW_URI" =~ ^https?://[a-zA-Z0-9.-]+(:[0-9]{2,5})?$ ]]; then
  echo "Provide an explicit HTTP(S) external MLflow service origin" >&2
  exit 2
fi

command -v kubectl >/dev/null
command -v helm >/dev/null
kubectl get crd workflows.argoproj.io >/dev/null
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n "$NAMESPACE" -f - <<'YAML'
apiVersion: v1
kind: ResourceQuota
metadata:
  name: modelops-tenant-quota
spec:
  hard:
    pods: "20"
    requests.cpu: "24"
    requests.memory: "128Gi"
    limits.memory: "256Gi"
    requests.storage: "300Gi"
    persistentvolumeclaims: "12"
    requests.nvidia.com/gpu: "4"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: modelops-resource-limits
spec:
  limits:
    - type: Container
      defaultRequest: {cpu: 250m, memory: 256Mi}
      default: {cpu: "4", memory: 8Gi}
YAML

# Provision these through an External Secrets controller. Never accept keys
# on the command line, store them in Helm values or print their contents.
if ! kubectl -n "$NAMESPACE" get secret modelops-objectstore >/dev/null 2>&1; then
  echo "Required Secret modelops-objectstore not provisioned" >&2
  exit 3
fi
for KEY in endpoint accessKey secretKey; do
  if ! kubectl -n "$NAMESPACE" get secret modelops-objectstore \
      -o "jsonpath={.data.$KEY}" | grep -q .; then
    echo "Required object store key is missing: $KEY" >&2
    exit 3
  fi
done

helm upgrade --install modelops "$CHART" \
  --namespace "$NAMESPACE" \
  --set staticTemplate.enabled=false \
  --set dynamicTemplate.enabled=true \
  --set mlflow.enabled=false \
  --set pdb.enabled=false \
  --set renderWorkflowsWithoutCRD=true \
  --set-string dynamicTemplate.mlflowTrackingURI="$MODELOPS_MLFLOW_URI" \
  --wait --timeout 5m

kubectl -n "$NAMESPACE" get workflowtemplate modelops-finetune-dynamic >/dev/null
kubectl -n "$NAMESPACE" get serviceaccount modelops-finetune >/dev/null
SERVICE_ACCOUNT="system:serviceaccount:$NAMESPACE:modelops-finetune"
if kubectl auth can-i create deployments --as="$SERVICE_ACCOUNT" -n kube-system --quiet; then
  echo "SECURITY FAILURE: tenant trainer can modify another namespace" >&2
  exit 4
fi
if kubectl auth can-i get secrets --as="$SERVICE_ACCOUNT" -n "$NAMESPACE" --quiet; then
  echo "SECURITY FAILURE: trainer may list tenant credentials" >&2
  exit 4
fi
echo "Tenant $TENANT: Argo WorkflowTemplate, Role and quota ready."
echo "No claim of real GPU model training or MLflow publication is made."
