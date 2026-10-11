# ModelOps Platform -- CPU Development & Production Architecture

### Start local metadata/API/UI (no GPU, no Kubernetes)

```bash
cp .env.compose.example .env
# Fill MODELOPS_PG_PASSWORD and MODELOPS_JWT_SECRET with random values.
docker compose up --build -d postgres
# Run schema migration as a one-time explicit operation:
docker compose run --rm --no-deps api alembic upgrade head
docker compose up --build -d api console
```

The local console is at http://localhost:3000; API at http://127.0.0.1:8080. Generate local dev JWT using matching env values: `cd control-plane && python -m modelops.devtoken --tenant demo --role admin --subject local-operator`. Tokens expire after 30 minutes by default.

**Local mode deliberately refuses** create Deployment and TrainJob requests because no K8s runtime is connected. Model and Dataset registration is real persisted PostgreSQL metadata, and audit events are real database rows. No model-serving success is fabricated.

### Kubernetes / production deployment

Requires externally provisioned: PostgreSQL, namespaces `modelops-<tenant>`, Argo CRDs, ModelOps CRDs, real LiteLLM Gateway, K8s-authenticated Operator and OIDC identity provider. Run `alembic upgrade head` as a controlled migration job; disable dev JWT and SQLite; supply a read-only service account plus namespace-scoped RBAC where possible.

The API is not a cluster administrator, and the user interface does not possess model-serving gateway admin keys. Production readiness requires TLS ingress, network isolation, cluster RBAC, independent asset signature checks, state recovery, and backup/restore tests.

### Software evidence gate

`python -m pytest control-plane/tests` and `cd console && npm run build` pass on CI. These validate metadata workflows and UI compilation; they are not GPU workload tests. The dynamic Argo template is Helm-rendered/tested without executing a model. The GPU/HA issue trackers remain open until real independent evidence exists.
