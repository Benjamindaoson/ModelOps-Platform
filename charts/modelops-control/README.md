# ModelOps Control Plane Helm Chart (production deployment contract)

This installs the **first-party** FastAPI API, Next.js Console, tenant RBAC,
recovery CronJobs, database migration Job, Ingress TLS, NetworkPolicies and
PodDisruptionBudgets. It does NOT bootstrap tenant namespaces, external
PostgreSQL, an OIDC identity provider, object storage, Argo, GPU nodes or the
namespace-scoped serving Operators. Those are independent deployment prerequisites.

**Never run the render-only values-ci.yaml in a live cluster.**

## External prerequisites (required)

1. Provision an HA PostgreSQL cluster and a namespaced Kubernetes Secret with
   key \`database-url\`, containing a \`postgresql+psycopg://...\` URL. Set
   its permissions for the platform's namespace; use an external secrets manager.
2. Provision a separate evaluation-worker **Ed25519 private signing key**
   that is NEVER mounted into API/Console Pods. In the API namespace provide
   only the 32-byte PUBLIC key (base64 encoded), via external Secret with
   key \`public-key\` (values field \`secrets.evaluationVerify\`). Require
   independently signed heldout/checkpoint evidence and two-person approval.
3. Deploy and validate HTTPS OIDC, obtain issuer, JWKS, client ID/audience.
   Client credentials stay in a Secret (optional for public PKCE clients).
4. Build API and Console images from reviewed commits, scan them and publish
   OCI digests with SBOM/provenance. Set \`api.image.digest\` and
   \`console.image.digest\` to immutable \`sha256:<64 hex>\` values.
5. Bootstrap CRDs, namespace \`modelops-<tenant>\`, tenant ResourceQuota,
   operator, Argo WorkflowTemplate, OIDC role claims, and Gateway separately.
6. Provision a real TLS certificate and ingress controller. Configure egress
   CIDRs to include the *actual* API server, Postgres and OIDC endpoints,
   not a broad 0.0.0.0/0. Your CNI must enforce NetworkPolicy.

## Render validation (not a deployment)

\`\`\`bash
helm lint charts/modelops-control -f charts/modelops-control/values-ci.yaml
helm template modelops charts/modelops-control \\
  --namespace modelops-system \\
  -f charts/modelops-control/values-ci.yaml > /tmp/modelops-control-render.yaml
\`\`\`

## Actual install after prerequisites

Copy \`values.yaml\` into an access-controlled deployment repository and fill
all mandatory non-secret configuration. Reference already-provisioned Secrets,
never copy secret values into Helm files. Then from an approved **bootstrap**
identity with Role/RoleBinding creation privileges:

\`\`\`bash
helm upgrade --install modelops charts/modelops-control \\
  --namespace modelops-system --create-namespace \\
  -f /secure/deployment-values.yaml --wait --atomic --timeout 15m
\`\`\`

Migration is a separate pre-install/pre-upgrade **Job**; a failed migration
blocks rollout rather than silently starting mismatched API replicas.
**Back up PostgreSQL before upgrading.** Rollback of an image is not the
same as a safe reverse database migration.

For each tenant the chart only grants \`modeldeployments\` CRUD and Argo
\`workflows\` get/create/patch in the tenant namespace, with no Secret access
or ClusterRoleBinding. Confirm \`kubectl auth can-i\` checks with your actual
service account and test cross-namespace denial. Runtime Pods do not run
\`cluster-admin\` or use development JWT mode.

The CronJob runs the same idempotent recovery worker for one tenant every
five minutes; its exit remains nonzero while a deletion finalizer is pending
or a mutation cannot be confirmed. Watch job history and alert on repeated
failures. The Console receives no Kubernetes service-account token.

Readiness probes check the *process and metadata database*, **not** GPU
model serving, replica HA, OIDC connectivity or throughput. Real release
acceptance also requires an external OIDC login, PostgreSQL/S3 restore drill,
API-to-Operator-to-LiteLLM lifecycle, canary traffic and actual model
training/serving benchmarks. This chart is not a production certification.
