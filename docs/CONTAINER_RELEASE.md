# Versioned API/Console container release

Workflow `.github/workflows/modelops-images.yml` builds **two real
containers** on PR/main, starts each process, and checks its HTTP readiness.
On a release tag `v*`, the same workflow publishes OCI images
`ghcr.io/benjamindaoson/modelops-control-plane:<tag>` and
`ghcr.io/benjamindaoson/modelops-console:<tag>` with BuildKit provenance
and SBOM attestations. Production Helm/Kustomize should pin the resulting
image **digest** instead of a moving tag.

The control API image includes Alembic migrations, but never runs them on
startup. Execute `alembic upgrade head` in a separately authorized
migration Job with a pre-upgrade PostgreSQL backup.

The bundled CronJob sample points to a version tag that **must have been
published and verified** before deployment. Replacing the tag in a YAML file
does not create an image. Image-build smoke tests use development SQLite and
production-mode OIDC discovery configuration respectively, and neither
claims a real Kubernetes serving or training result.

For a release:
1. Require all control API, UI/browser, Go/Helm, container and kind checks green.
2. Confirm container SBOM, CVE scan and fixed image digests.
3. Tag an immutable release, e.g. `v0.1.0`; verify workflow publication.
4. Pin API/UI/recovery worker by digest in workload manifests.
5. Run schema migration, restore rehearsal and full CPU kind integration before
   any GPU experiments.

Release tags are not automatically created by this task.
