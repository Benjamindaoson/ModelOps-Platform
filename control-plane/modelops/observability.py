"""Tenant-scoped operational metrics; unavailable GPU readings are omitted."""
from __future__ import annotations
import subprocess
from prometheus_client import CollectorRegistry,Counter,Gauge,Histogram,generate_latest
from sqlalchemy import select
from .db import FineTuneJob,Deployment

class Telemetry:
    def __init__(self):
        self.registry=CollectorRegistry()
        self.inference=Histogram("modelops_inference_latency","Actual managed prediction wall time in seconds",
            ["tenant","model_type"],registry=self.registry)
    def observe(self,tenant,kind,seconds):
        self.inference.labels(tenant,kind).observe(seconds)
    def export(self,db,tenant):
        reg=CollectorRegistry()
        jobs=Counter("modelops_training_jobs_total","Persisted lifetime training jobs; restoration can reset",
            ["worker"],registry=reg)
        rows=db.scalars(select(FineTuneJob).where(FineTuneJob.tenant==tenant)).all()
        for worker in ("argo","linux"):jobs.labels(worker).inc(sum(r.worker==worker for r in rows))
        deployments=Gauge("modelops_deployment_status","Desired deployment intents, not model readiness",
            ["intent"],registry=reg)
        ds=db.scalars(select(Deployment).where(Deployment.tenant==tenant)).all()
        for intent in ("requested","deleted","runtime_unknown","updating"):
            deployments.labels(intent).set(sum(r.intent==intent for r in ds))
        # A fresh nvidia-smi sample, not a guessed or benchmark peak.
        gpu=Gauge("modelops_gpu_usage","Live GPU utilization percentage",["gpu"],registry=reg)
        try:
            p=subprocess.run(["nvidia-smi","--query-gpu=index,utilization.gpu","--format=csv,noheader,nounits"],
                capture_output=True,text=True,timeout=3,check=False)
            if p.returncode==0:
                for line in p.stdout.splitlines():
                    idx,value=line.split(",");gpu.labels(idx.strip()).set(float(value))
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
        # Export only this authenticated tenant's actual prediction observations.
        lines=generate_latest(self.registry).decode().splitlines()
        selected=[l for l in lines if l.startswith("#") or ('tenant="'+tenant+'"') in l]
        return generate_latest(reg)+("\n".join(selected)+"\n").encode()
