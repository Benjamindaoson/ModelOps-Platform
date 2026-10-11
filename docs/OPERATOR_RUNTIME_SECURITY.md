# Runtime Operator RBAC boundary

The ModelOps Operator chart has been changed to install a **namespace Role/RoleBinding**, not `cluster-admin`.

Operators are installed once **per isolated tenant namespace**. The manager restricts its controller-runtime cache to `WATCH_NAMESPACE` and must never watch cluster-wide resources by default. CRDs, Argo Workflows, StorageClasses, KEDA and umbrella Helm charts are bootstrapped separately by an authorized cluster administrator.

Mandatory setup before the runtime operator:
1. Provision namespace `modelops-<tenant>` and apply ResourceQuota/NetworkPolicy.
2. Install the ModelOps CRDs (and Argo CRDs) using a dedicated privileged bootstrap identity.
3. Deploy the minimal LiteLLM Gateway plus a Kubernetes Secret `kube-llmops-litellm-secret` with key `master-key`.
4. Install the namespace-scoped operator Helm chart in the same namespace.
5. Verify `kubectl auth can-i` for the operator ServiceAccount; cluster secret listing or namespace deletion must fail.

`MODELOPS_ENABLE_HELM_BOOTSTRAP=1` is an unsafe **development-only** option and is blocked by the Go binary when `MODELOPS_ENV=production`. The old Helm-managed LLMPlatform reconciler cannot be allowed to install arbitrary cluster-scoped resources from the namespace operator.

Serving Pod Ready is distinct from Gateway Ready. Registration failure now marks ModelDeployment `Degraded` and requeues reconciliation rather than silently presenting a successful endpoint. Actual runtime and admission behavior still need Kubernetes E2E beyond template unit tests.
