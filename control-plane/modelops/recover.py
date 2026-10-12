"""One-shot, tenant-scoped Kubernetes/PostgreSQL reconciliation worker.

Run once per tenant using a namespace-local service account and an externally
scheduled CronJob. Never escalates privileges or deletes foreign resources.
"""
from __future__ import annotations

import os
import re
import sys

from sqlalchemy import select

from .db import AuditEvent, Deployment, DeploymentRevision, FineTuneJob, ModelArtifact, DatasetVersion, make_session_factory
from .reconciliation import ensure_deployment, ensure_training, ensure_updated_deployment
from .runtime import KubernetesRuntime, RuntimeFailure


def recover_once(sessions, runtime, tenant: str, max_items: int = 100) -> dict:
    if not re.fullmatch(r"[a-z](?:[a-z0-9-]{0,38}[a-z0-9])?", tenant):
        raise ValueError("Recovery tenant must be a validated lower-case namespace slug")
    if max_items < 1 or max_items > 500:
        raise ValueError("Recovery batch limit must be in 1..500")
    summary = {"tenant": tenant, "recovered": 0, "still_unknown": 0, "examined": 0}
    # The intent record is durable and has immutable resource name/inputs.
    # A failed Kubernetes response is not proof that the CREATE did not occur.
    with sessions() as db:
        jobs = list(db.scalars(
            select(FineTuneJob).where(
                FineTuneJob.tenant == tenant,
                FineTuneJob.intent.in_(("submitting", "runtime_unknown")))
            .order_by(FineTuneJob.created_at).limit(max_items)).all())
        left = max_items - len(jobs)
        deployments = list(db.scalars(
            select(Deployment).where(
                Deployment.tenant == tenant,
                Deployment.intent.in_(("submitting", "updating", "runtime_unknown")))
            .order_by(Deployment.created_at).limit(left)).all())
        for kind, record in ([("training", job) for job in jobs] +
                             [("deployment", item) for item in deployments]):
            summary["examined"] += 1
            try:
                artifact = db.get(ModelArtifact, record.artifact_id)
                if artifact is None or artifact.tenant != tenant:
                    raise RuntimeFailure("Durable intent references a missing/foreign model")
                if kind == "training":
                    dataset = db.get(DatasetVersion, record.dataset_id)
                    if dataset is None or dataset.tenant != tenant:
                        raise RuntimeFailure("Durable intent references a missing/foreign dataset")
                    outcome = ensure_training(runtime, record, artifact, dataset)
                else:
                    latest = db.scalar(select(DeploymentRevision).where(
                        DeploymentRevision.deployment_id == record.id
                    ).order_by(DeploymentRevision.generation.desc()).limit(1))
                    if latest and latest.operation in ("scale", "promote", "rollback"):
                        outcome = ensure_updated_deployment(runtime, record, artifact)
                    else:
                        outcome = ensure_deployment(runtime, record, artifact)
                record.intent = "requested"
                db.add(AuditEvent(
                    tenant=tenant, actor="system:recovery-worker",
                    action=kind + ".recovered", object_kind=kind,
                    object_id=record.id,
                    detail='{"outcome":"' + outcome + '"}',
                ))
                db.commit()
                summary["recovered"] += 1
            except RuntimeFailure:
                # Avoid a flood of identical audit entries on every retry.
                if record.intent != "runtime_unknown":
                    record.intent = "runtime_unknown"
                    db.commit()
                summary["still_unknown"] += 1
            except Exception:
                db.rollback()
                raise
    return summary


def main() -> int:
    tenant = os.environ.get("MODELOPS_RECOVERY_TENANT", "")
    url = os.environ.get("MODELOPS_DATABASE_URL", "")
    if (os.environ.get("MODELOPS_RUNTIME") != "kubernetes" or
        not url.startswith("postgresql+") or not tenant):
        print("Recovery requires a tenant name, PostgreSQL and a live Kubernetes runtime",
              file=sys.stderr)
        return 2
    engine, sessions = make_session_factory(url)
    try:
        runtime = KubernetesRuntime(os.environ.get("MODELOPS_K8S_CONTEXT", ""))
        result = recover_once(sessions, runtime, tenant)
        print("ModelOps reconciliation:", {k: v for k, v in result.items() if k != "tenant"})
        return 0 if result["still_unknown"] == 0 else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
