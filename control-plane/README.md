# ModelOps Control API

The metadata database tracks immutable model/dataset artifacts, tenant ownership, deployment intentions/revisions, fine-tuning jobs, separately signed evaluation evidence, two-person approval and immutable audit events. **The Kubernetes API is the source of truth for runtime readiness.** An unconnected runtime refuses all deployment and training writes with HTTP 503; no success is simulated.

## Development (CPU/no cluster)

Install: `pip install -e '.[dev]'`. Set `MODELOPS_ENV=development`, `MODELOPS_AUTH_MODE=dev`, and a randomly generated `MODELOPS_JWT_SECRET` of at least 32 characters, then run `uvicorn modelops.main:app --host 127.0.0.1 --port 8080` from `control-plane/`.

Use `python -m modelops.devtoken --tenant demo --role admin --subject local-owner` (same secret env) for an expiring local developer token. This mode is explicitly forbidden in production. API docs at `/docs`.

`MODELOPS_RUNTIME=disabled` is a metadata-only mode; attempts to create deployments/train jobs return 503. Real Kubernetes operations require `MODELOPS_RUNTIME=kubernetes`, a configured kubeconfig or in-cluster ServiceAccount, CRDs, Argo Workflows, the `modelops-<tenant>` namespace and a `modelops-finetune-dynamic` WorkflowTemplate.

## Production security boundary

Only `MODELOPS_AUTH_MODE=oidc` is allowed in production, with configured HTTPS JWKS, issuer and audience. Bearer claims must contain a validated `sub`, `tenant`, and `role` (viewer/editor/admin). API roles and tenant filters are enforced server-side. A separate OIDC authentication proxy must secure the Next.js UI session.

For real release approvals, the evaluation service must submit a `modelops.heldout.v1` report signed with the secret `MODELOPS_ATTESTATION_KEY`. Reports are validated for digest alignment and quality thresholds; release approval requires a distinct admin. This is evidence provenance, **not independent proof of model performance**. Protect the key and record data lineage; actual model artifact digests must be verified by a trusted worker.

SQL storage: SQLite is development-only; production requires PostgreSQL. Schema migrations must run separately rather than relying on automatic `create_all`.

### Design limitations

- Runtime returns Kubernetes phase, never reports Succeeded from creating a CR.
- Deployment source pinning uses runtime engine revision arguments. Model source/digest is currently declared metadata; source artifact hashing requires a real trusted worker.
- K8s calls are not transactional with SQL. Failure/error compensation and reconciliation need further hardening for simultaneous clients, network partitions and cluster loss.
- Real multi-tenant security requires Kubernetes RBAC, namespace quotas, NetworkPolicies and separate cluster provisioning (not provided by a development JWT).
- ASR/TTS, TensorRT-LLM and training GPU performance are not validated.

## Database migrations

Use `alembic upgrade head` after setting `MODELOPS_DATABASE_URL`. Production startup intentionally never creates metadata tables automatically. The initial migration is versioned under `migrations/versions/`.
