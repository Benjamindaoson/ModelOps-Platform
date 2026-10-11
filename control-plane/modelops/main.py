"""Tenant-isolated ModelOps API. Never reports runtime PASS without Kubernetes evidence."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Generator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Principal, Verifier, require_principal
from .config import Settings
from .db import (Base, TenantRecord, ModelArtifact, DatasetVersion, Deployment,
                 DeploymentRevision, FineTuneJob, EvaluationRecord, ReleaseApproval,
                 AuditEvent, make_session_factory)
from .evidence import EvidenceError, digest_report, verify_report
from .runtime import (DisabledRuntime, KubernetesRuntime, RuntimeFailure,
                      RuntimeUnavailable, namespace_for)
from .schemas import (ApprovalIn, ArtifactIn, DatasetIn, DeploymentIn,
                      EvaluationIn, FineTuneIn, ReleaseIn, ScaleIn)


def render(obj, *fields) -> dict:
    out = {k: getattr(obj, k) for k in fields}
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


MODEL_FIELDS = ("id", "name", "version", "family", "source", "revision", "digest",
                "digest_verified", "created_by", "created_at")
DATASET_FIELDS = ("id", "name", "version", "uri", "digest", "train_count",
                  "heldout_count", "created_by", "created_at")
DEPLOY_FIELDS = ("id", "name", "artifact_id", "engine", "replicas", "gpu",
                 "generation", "intent", "created_by", "created_at")
RUN_FIELDS = ("id", "name", "artifact_id", "dataset_id", "method",
              "workflow_name", "intent", "created_by", "created_at")


def fetch_owned(db: Session, klass, tenant: str, key: str):
    obj = db.get(klass, key)
    if obj is None or obj.tenant != tenant:
        # Identical 404 for missing and foreign tenant prevents object enumeration.
        raise HTTPException(status_code=404, detail="Resource not found")
    return obj


def ensure_tenant(db: Session, tenant: str) -> None:
    if db.get(TenantRecord, tenant) is None:
        db.add(TenantRecord(slug=tenant))
        flush_record(db)


def audit(db: Session, principal: Principal, action: str, kind: str, key: str, detail: dict | None = None):
    db.add(AuditEvent(tenant=principal.tenant, actor=principal.subject, action=action,
                      object_kind=kind, object_id=key, detail=json.dumps(detail or {})))


def flush_record(db: Session):
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate name/version or conflicting update") from exc


def commit(db: Session):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate name/version or conflicting update") from exc


def get_db(request: Request) -> Generator[Session, None, None]:
    db = request.app.state.sessions()
    try:
        yield db
    finally:
        db.close()


def require_role(principal: Principal, role: str):
    principal.require(role)
    return principal


def with_runtime_state(runtime, dep: Deployment, data: dict):
    if not runtime.connected:
        return {**data, "observed_phase": "RuntimeDisconnected", "ready_replicas": None,
                "runtime_verified": False}
    try:
        observed = runtime.get_deployment(dep)
        status = observed.get("status", {})
        return {**data, "observed_phase": status.get("phase", "Pending"),
                "ready_replicas": status.get("readyReplicas", 0),
                "runtime_verified": True}
    except RuntimeFailure:
        return {**data, "observed_phase": "RuntimeUnreachable",
                "ready_replicas": None, "runtime_verified": False}


def create_app(settings: Settings | None = None, runtime=None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    engine, session_factory = make_session_factory(settings.database_url)
    if settings.environment != "production":
        Base.metadata.create_all(engine)
    app = FastAPI(title="ModelOps Control API", version="0.1.0",
                  docs_url="/docs" if settings.environment != "production" else None)
    app.state.settings = settings
    app.state.verifier = Verifier(settings)
    app.state.sessions = session_factory
    app.state.runtime = runtime if runtime is not None else (
        KubernetesRuntime(settings.k8s_context)
        if settings.runtime == "kubernetes" else DisabledRuntime())

    @app.exception_handler(RuntimeUnavailable)
    async def runtime_unavailable(_, exc: RuntimeUnavailable):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(RuntimeFailure)
    async def runtime_failed(_, exc: RuntimeFailure):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.get("/healthz")
    def health():
        return {"service": "modelops-control", "alive": True}

    @app.get("/readyz")
    def ready(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(status_code=503, detail="Metadata database unavailable")
        return {"metadata_database": "ready", "runtime_connected": app.state.runtime.connected,
                "note": "This is not a GPU or model-serving health signal"}

    @app.get("/api/v1/me")
    def me(p: Principal = Depends(require_principal)):
        return asdict(p)

    @app.get("/api/v1/overview")
    def overview(p: Principal = Depends(require_principal), db: Session = Depends(get_db)):
        result = {"runtime_connected": app.state.runtime.connected,
                  "platform_state": "kubernetes" if app.state.runtime.connected else "development_metadata_only"}
        for key, entity in (("models", ModelArtifact), ("datasets", DatasetVersion),
                            ("deployments", Deployment), ("training_jobs", FineTuneJob),
                            ("audit_events", AuditEvent)):
            result[key] = db.scalar(select(func.count()).select_from(entity).where(entity.tenant == p.tenant))
        result["runtime_proven"] = False  # Only individual workload checks prove model quality.
        return result

    @app.get("/api/v1/models")
    def models(limit: int = 50, offset: int = 0, p: Principal = Depends(require_principal),
               db: Session = Depends(get_db)):
        if limit < 1 or limit > 100 or offset < 0:
            raise HTTPException(422, detail="Invalid pagination")
        rows = db.scalars(select(ModelArtifact).where(ModelArtifact.tenant == p.tenant)
                          .order_by(ModelArtifact.created_at.desc()).limit(limit).offset(offset)).all()
        return [render(x, *MODEL_FIELDS) for x in rows]

    @app.post("/api/v1/models", status_code=201)
    def create_model(req: ArtifactIn, p: Principal = Depends(require_principal),
                     db: Session = Depends(get_db)):
        require_role(p, "editor")
        ensure_tenant(db, p.tenant)
        record = ModelArtifact(tenant=p.tenant, created_by=p.subject, **req.model_dump())
        db.add(record)
        flush_record(db)
        audit(db, p, "artifact.register", "model", record.id,
              {"name": record.name, "version": record.version, "digest_verified": False})
        commit(db)
        return render(record, *MODEL_FIELDS)

    @app.get("/api/v1/datasets")
    def datasets(limit: int = 50, offset: int = 0, p: Principal = Depends(require_principal),
                 db: Session = Depends(get_db)):
        if limit < 1 or limit > 100 or offset < 0:
            raise HTTPException(422, detail="Invalid pagination")
        rows = db.scalars(select(DatasetVersion).where(DatasetVersion.tenant == p.tenant)
                          .order_by(DatasetVersion.created_at.desc()).limit(limit).offset(offset)).all()
        return [render(x, *DATASET_FIELDS) for x in rows]

    @app.post("/api/v1/datasets", status_code=201)
    def create_dataset(req: DatasetIn, p: Principal = Depends(require_principal),
                       db: Session = Depends(get_db)):
        require_role(p, "editor")
        ensure_tenant(db, p.tenant)
        record = DatasetVersion(tenant=p.tenant, created_by=p.subject, **req.model_dump())
        db.add(record)
        flush_record(db)
        audit(db, p, "dataset.register", "dataset", record.id, {"name": record.name, "version": record.version})
        commit(db)
        return render(record, *DATASET_FIELDS)

    @app.get("/api/v1/deployments")
    def deployments(p: Principal = Depends(require_principal), db: Session = Depends(get_db)):
        rows = db.scalars(select(Deployment).where(Deployment.tenant == p.tenant)
                          .order_by(Deployment.created_at.desc()).limit(100)).all()
        return [with_runtime_state(app.state.runtime, d, render(d, *DEPLOY_FIELDS)) for d in rows]

    @app.post("/api/v1/deployments", status_code=201)
    def create_deployment(req: DeploymentIn, p: Principal = Depends(require_principal),
                          db: Session = Depends(get_db)):
        require_role(p, "editor")
        artifact = fetch_owned(db, ModelArtifact, p.tenant, req.artifact_id)
        if artifact.family in ("asr", "tts"):
            raise HTTPException(422, detail="ASR/TTS engines not yet implemented; no fake deployment")
        if artifact.family == "embedding" and req.engine != "tei":
            raise HTTPException(422, detail="Embedding model requires TEI engine in this release")
        if not app.state.runtime.connected:
            raise RuntimeUnavailable("Kubernetes disconnected; model deployment was not created")
        row = Deployment(tenant=p.tenant, name=req.name, artifact_id=artifact.id,
                         engine=req.engine, replicas=req.replicas, gpu=req.gpu,
                         created_by=p.subject)
        db.add(row)
        flush_record(db)
        app.state.runtime.create_deployment(row, artifact)
        db.add(DeploymentRevision(deployment_id=row.id, generation=1, artifact_id=artifact.id,
                                  operation="create", requested_by=p.subject))
        audit(db, p, "deployment.create", "deployment", row.id,
              {"engine": row.engine, "generation": row.generation})
        commit(db)
        return with_runtime_state(app.state.runtime, row, render(row, *DEPLOY_FIELDS))

    @app.get("/api/v1/deployments/{key}")
    def get_deployment(key: str, p: Principal = Depends(require_principal),
                       db: Session = Depends(get_db)):
        row = fetch_owned(db, Deployment, p.tenant, key)
        return with_runtime_state(app.state.runtime, row, render(row, *DEPLOY_FIELDS))

    @app.get("/api/v1/deployments/{key}/revisions")
    def deployment_revisions(key: str, p: Principal = Depends(require_principal),
                             db: Session = Depends(get_db)):
        row = fetch_owned(db, Deployment, p.tenant, key)
        revs = db.scalars(select(DeploymentRevision)
                          .where(DeploymentRevision.deployment_id == row.id)
                          .order_by(DeploymentRevision.generation.desc())).all()
        return [render(r, "id", "generation", "artifact_id", "operation",
                       "requested_by", "created_at") for r in revs]

    @app.patch("/api/v1/deployments/{key}/scale")
    def scale(key: str, req: ScaleIn, p: Principal = Depends(require_principal),
              db: Session = Depends(get_db)):
        require_role(p, "editor")
        row = fetch_owned(db, Deployment, p.tenant, key)
        if row.generation != req.expected_generation:
            raise HTTPException(409, detail="Deployment generation changed; refresh first")
        if row.intent == "deleted":
            raise HTTPException(409, detail="Deployment deleted")
        row.replicas = req.replicas
        row.generation += 1
        artifact = fetch_owned(db, ModelArtifact, p.tenant, row.artifact_id)
        app.state.runtime.patch_deployment(row, artifact)
        db.add(DeploymentRevision(deployment_id=row.id, generation=row.generation,
                                  artifact_id=artifact.id, operation="scale",
                                  requested_by=p.subject))
        audit(db, p, "deployment.scale", "deployment", row.id,
              {"replicas": row.replicas, "generation": row.generation})
        commit(db)
        return with_runtime_state(app.state.runtime, row, render(row, *DEPLOY_FIELDS))

    @app.post("/api/v1/evaluations/attest", status_code=201)
    def attest(req: dict, request: Request, p: Principal = Depends(require_principal),
               db: Session = Depends(get_db)):
        require_role(p, "editor")
        artifact_id, dataset_id = req.get("artifact_id"), req.get("dataset_id")
        artifact = fetch_owned(db, ModelArtifact, p.tenant, artifact_id)
        dataset = fetch_owned(db, DatasetVersion, p.tenant, dataset_id)
        report = req.get("report")
        if not isinstance(report, dict):
            raise HTTPException(422, detail="Report must be an object")
        try:
            passed, metrics = verify_report(report,
                request.headers.get("X-ModelOps-Attestation", ""),
                os.getenv("MODELOPS_ATTESTATION_KEY", ""), artifact, dataset)
        except (EvidenceError, ValueError) as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        row = EvaluationRecord(tenant=p.tenant, artifact_id=artifact.id, dataset_id=dataset.id,
                               report_sha256=digest_report(report),
                               metrics_json=json.dumps(metrics), verified=True,
                               passed=passed, submitted_by=p.subject)
        db.add(row)
        flush_record(db)
        audit(db, p, "evaluation.attest", "evaluation", row.id,
              {"passed": row.passed, "report_sha256": row.report_sha256})
        commit(db)
        return {"id": row.id, "verified": row.verified, "passed": row.passed,
                "report_sha256": row.report_sha256, "metrics": metrics}

    @app.get("/api/v1/evaluations")
    def evaluations(p: Principal = Depends(require_principal), db: Session = Depends(get_db)):
        rows = db.scalars(select(EvaluationRecord).where(EvaluationRecord.tenant == p.tenant)
                          .order_by(EvaluationRecord.created_at.desc()).limit(100)).all()
        return [{"id": r.id, "artifact_id": r.artifact_id, "dataset_id": r.dataset_id,
                 "verified": r.verified, "passed": r.passed,
                 "metrics": json.loads(r.metrics_json), "created_at": r.created_at.isoformat()}
                for r in rows]

    @app.post("/api/v1/approvals", status_code=201)
    def approve(req: ApprovalIn, p: Principal = Depends(require_principal),
                db: Session = Depends(get_db)):
        require_role(p, "admin")
        artifact = fetch_owned(db, ModelArtifact, p.tenant, req.artifact_id)
        eval_record = fetch_owned(db, EvaluationRecord, p.tenant, req.evaluation_id)
        if not eval_record.verified or not eval_record.passed or eval_record.artifact_id != artifact.id:
            raise HTTPException(409, detail="Independent verified passing evaluation required")
        if eval_record.submitted_by == p.subject:
            raise HTTPException(409, detail="Release approver must be independent from report submitter")
        row = ReleaseApproval(tenant=p.tenant, artifact_id=artifact.id,
                              evaluation_id=eval_record.id, approver=p.subject, reason=req.reason)
        db.add(row)
        flush_record(db)
        audit(db, p, "release.approve", "approval", row.id, {"artifact_id": artifact.id})
        commit(db)
        return {"id": row.id, "artifact_id": row.artifact_id,
                "approver": row.approver, "reason": row.reason}

    @app.post("/api/v1/deployments/{key}/promote")
    def promote(key: str, req: ReleaseIn, p: Principal = Depends(require_principal),
                db: Session = Depends(get_db)):
        require_role(p, "editor")
        row = fetch_owned(db, Deployment, p.tenant, key)
        artifact = fetch_owned(db, ModelArtifact, p.tenant, req.artifact_id)
        approval = fetch_owned(db, ReleaseApproval, p.tenant, req.approval_id)
        if approval.artifact_id != artifact.id:
            raise HTTPException(409, detail="Approval does not cover requested artifact")
        if req.expected_generation != row.generation or row.intent == "deleted":
            raise HTTPException(409, detail="Stale generation/deleted deployment")
        if artifact.family in ("asr", "tts") or (artifact.family == "embedding") != (row.engine == "tei"):
            raise HTTPException(422, detail="Artifact and engine are incompatible")
        row.artifact_id = artifact.id
        row.generation += 1
        row.intent = "updating"
        app.state.runtime.patch_deployment(row, artifact)
        db.add(DeploymentRevision(deployment_id=row.id, generation=row.generation,
                                  artifact_id=artifact.id, operation="promote",
                                  requested_by=p.subject))
        audit(db, p, "deployment.promote", "deployment", row.id,
              {"artifact_id": artifact.id, "approval_id": approval.id})
        commit(db)
        return with_runtime_state(app.state.runtime, row, render(row, *DEPLOY_FIELDS))

    @app.post("/api/v1/deployments/{key}/rollback")
    def rollback(key: str, req: ScaleIn, p: Principal = Depends(require_principal),
                 db: Session = Depends(get_db)):
        require_role(p, "editor")
        row = fetch_owned(db, Deployment, p.tenant, key)
        if row.generation != req.expected_generation:
            raise HTTPException(409, detail="Stale generation")
        history = db.scalars(select(DeploymentRevision)
                             .where(DeploymentRevision.deployment_id == row.id,
                                    DeploymentRevision.artifact_id != row.artifact_id)
                             .order_by(DeploymentRevision.generation.desc()).limit(1)).all()
        if not history:
            raise HTTPException(409, detail="No previously deployed different model version")
        artifact = fetch_owned(db, ModelArtifact, p.tenant, history[0].artifact_id)
        row.artifact_id = artifact.id
        row.generation += 1
        row.intent = "rolling_back"
        app.state.runtime.patch_deployment(row, artifact)
        db.add(DeploymentRevision(deployment_id=row.id, generation=row.generation,
                                  artifact_id=artifact.id, operation="rollback",
                                  requested_by=p.subject))
        audit(db, p, "deployment.rollback", "deployment", row.id, {"artifact_id": artifact.id})
        commit(db)
        return with_runtime_state(app.state.runtime, row, render(row, *DEPLOY_FIELDS))

    @app.delete("/api/v1/deployments/{key}")
    def delete_deployment(key: str, p: Principal = Depends(require_principal),
                          db: Session = Depends(get_db)):
        require_role(p, "editor")
        row = fetch_owned(db, Deployment, p.tenant, key)
        if row.intent != "deleted":
            app.state.runtime.delete_deployment(row)
            row.intent = "deleted"
            row.generation += 1
            audit(db, p, "deployment.delete", "deployment", row.id)
            commit(db)
        return {"status": "deletion_requested", "id": row.id}

    @app.get("/api/v1/train-jobs")
    def train_jobs(p: Principal = Depends(require_principal), db: Session = Depends(get_db)):
        rows = db.scalars(select(FineTuneJob).where(FineTuneJob.tenant == p.tenant)
                          .order_by(FineTuneJob.created_at.desc()).limit(100)).all()
        result = []
        for row in rows:
            data = render(row, *RUN_FIELDS)
            data["parameters"] = json.loads(row.parameters_json)
            if app.state.runtime.connected:
                try:
                    data["observed_phase"] = app.state.runtime.get_finetune(row).get("status", {}).get("phase", "Pending")
                except RuntimeFailure:
                    data["observed_phase"] = "RuntimeUnreachable"
            else:
                data["observed_phase"] = "RuntimeDisconnected"
            result.append(data)
        return result

    @app.post("/api/v1/train-jobs", status_code=201)
    def submit_train_job(req: FineTuneIn, p: Principal = Depends(require_principal),
                         db: Session = Depends(get_db)):
        require_role(p, "editor")
        artifact = fetch_owned(db, ModelArtifact, p.tenant, req.artifact_id)
        dataset = fetch_owned(db, DatasetVersion, p.tenant, req.dataset_id)
        if artifact.family != "llm":
            raise HTTPException(422, detail="Fine-tuning this model family not supported")
        if not app.state.runtime.connected:
            raise RuntimeUnavailable("Kubernetes/Argo disconnected; no training job created")
        row = FineTuneJob(tenant=p.tenant, name=req.name,
                         artifact_id=artifact.id, dataset_id=dataset.id, method=req.method,
                         parameters_json=req.model_dump_json(), workflow_name=req.name + "-ft",
                         created_by=p.subject)
        db.add(row)
        flush_record(db)
        app.state.runtime.submit_finetune(row, artifact, dataset, req.model_dump())
        audit(db, p, "training.submit", "train_job", row.id,
              {"method": req.method, "dataset_id": dataset.id})
        commit(db)
        return {**render(row, *RUN_FIELDS), "parameters": req.model_dump(),
                "observed_phase": "Pending", "runtime_verified": False}

    @app.get("/api/v1/audit")
    def audit_events(p: Principal = Depends(require_principal), db: Session = Depends(get_db)):
        rows = db.scalars(select(AuditEvent).where(AuditEvent.tenant == p.tenant)
                          .order_by(AuditEvent.at.desc()).limit(100)).all()
        return [render(x, "id", "actor", "action", "object_kind", "object_id", "at") for x in rows]

    return app


app = create_app()
