# Tenant provisioning

The FastAPI control plane submits dynamic Argo workflows into `modelops-<tenant>`.
The `modelops-finetune-dynamic` WorkflowTemplate and ServiceAccount must
therefore be installed **inside the same namespace**; a copy in `default` does not work.

This installer is deliberately an **out-of-band cluster bootstrap task**.
A platform administrator must already have installed Argo/ModelOps CRDs,
provisioned `modelops-objectstore` with keys `endpoint`, `accessKey`,
`secretKey` using a Secret manager, and deployed a real external MLflow
tracking server. No management API or browser route may invoke this script.

```bash
export MODELOPS_MLFLOW_URI=http://mlflow.platform.svc.cluster.local:5000
bash ops/provision-tenant.sh tenant1
kubectl -n modelops-tenant1 get workflowtemplate modelops-finetune-dynamic
```

The script installs only the dynamic Argo WorkflowTemplate and namespaced
Role/ServiceAccount from the finetune chart; it disables the legacy static
template and the bundled MLflow pod with insecure example credentials.
It creates ResourceQuota/LimitRange and verifies negative rights using
`kubectl auth can-i`. For production, additionally enforce NetworkPolicies,
OPA/Kyverno admission constraints, secret rotation and image pinning.
This is not proof that real LoRA/QLoRA/GPU training succeeded.
