# Production deployment gate

Before attempting any real cluster deployment, run:

\`\`\`bash
python -m pip install pyyaml
python ops/preflight.py --values charts/kube-llmops-stack/values-production.yaml
# This intentionally FAILS for the upstream example: illustrative model,
# empty passwords and enabled components that are not yet hardenened.
\`\`\`

Use the minimum required services, configure \`litellm.existingSecret\` referencing
a Kubernetes Secret with key \`master-key\` and \`litellm.postgresql.existingSecret\`
referencing key \`password\`. Do not commit these secrets. Disable extra database
creation and optional Keycloak/Langfuse until hardened for external secrets.

The preflight is an intentionally conservative **static gate**, not a guarantee
of cluster security. Check Secret existence, RBAC, NetworkPolicy, TLS,
audit logs, API rate-limit behavior and end-to-end rollback with actual K8s
before using a production label. At present the upstream operator RBAC binds
its ServiceAccount to \`cluster-admin\`, which is unacceptable for real
multi-tenant production; remedy this before deploying into a shared cluster.

A secure static pass **does not imply** the model endpoint, training workflow,
or GPU autoscaling works.
