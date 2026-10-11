#!/usr/bin/env python3
"""ModelOps production preflight: static fail-closed Helm-values gate.

Tests declared configuration, *not* successful K8s deployment.
Kubernetes Secret existence/permissions are runtime checks outside this tool.
Never prints secret values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Install PyYAML to run production configuration preflight") from exc


DANGEROUS = ("admin", "password", "secret", "default", "test", "example", "change-me", "your-")


def merge(base: dict, updates: dict) -> dict:
    result=base.copy()
    for key,value in updates.items():
        if isinstance(value,dict) and isinstance(result.get(key),dict):
            result[key]=merge(result[key],value)
        else:
            result[key]=value
    return result


def get(conf: dict, *keys, default=None):
    curr=conf
    for key in keys:
        if not isinstance(curr,dict):
            return default
        curr=curr.get(key)
    return default if curr is None else curr


def unsafe_secret(value: str) -> bool:
    if not isinstance(value,str) or len(value)<20:
        return True
    lowered=value.lower()
    return any(pattern in lowered for pattern in DANGEROUS)


def validate(conf: dict) -> list[str]:
    errors=[]
    models=get(conf,"models",default=[])
    if not isinstance(models,list) or not models:
        errors.append("at least one real production model is required")
    else:
        names=set()
        for row in models:
            if not isinstance(row,dict) or not row.get("name") or not row.get("source"):
                errors.append("model entry missing name or source")
                continue
            if row["name"] in names:
                errors.append("duplicate model name")
            names.add(row["name"])
            if any(token in str(row["source"]).lower() for token in ("your-org","your-model","example","placeholder")):
                errors.append("replace illustrative model source")
            if row.get("replicas",1)<1:
                errors.append("production model replicas must be positive")
    if get(conf,"litellm","enabled",default=True):
        master=get(conf,"litellm","masterKey",default="")
        secret=get(conf,"litellm","existingSecret",default="")
        if not secret:
            errors.append("LiteLLM requires existingSecret (never store masterKey in Helm values)")
        if master:
            errors.append("remove litellm.masterKey from values; use K8s Secret")
        if get(conf,"litellm","ui","password",default=""):
            errors.append("UI password must reference the shared K8s Secret, not plaintext values")
        if get(conf,"litellm","postgresql","enabled",default=True):
            db_secret=get(conf,"litellm","postgresql","existingSecret",default="")
            if not db_secret:
                errors.append("LiteLLM PostgreSQL requires postgresql.existingSecret")
            db_password=get(conf,"litellm","postgresql","auth","password",default="")
            if db_password:
                errors.append("remove inline PostgreSQL password in production")
            extras=get(conf,"litellm","postgresql","extraDatabases",default=[])
            if extras:
                errors.append("inline extraDatabases passwords not allowed in production (use external DB provisioner)")
    if get(conf,"security","enabled",default=False) is not True:
        errors.append("security.enabled must be true for production")
    if get(conf,"keycloak","enabled",default=False):
        errors.append("Keycloak needs separate external-secret hardening before production use")
    if get(conf,"langfuse","enabled",default=False):
        errors.append("Langfuse needs separate external-secret hardening before production use")
    if get(conf,"finetune","enabled",default=False):
        if get(conf,"finetune","evaluation","minSamples",default=0) < 20:
            errors.append("fine-tuning needs at least 20 independent heldout samples")
        if get(conf,"finetune","deploy","auto",default=False):
            errors.append("disable unapproved training-to-production auto deployment")
    return errors


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--values",type=Path,nargs="+",required=True,help="Helm values files in override order")
    p.add_argument("--report",type=Path)
    args=p.parse_args(argv)
    try:
        data={}
        for file in args.values:
            part=yaml.safe_load(file.read_text()) or {}
            if not isinstance(part,dict):
                raise ValueError("Helm values must be a mapping")
            data=merge(data,part)
        issues=validate(data)
    except (ValueError,OSError,yaml.YAMLError) as exc:
        print(f"ModelOps production preflight: invalid values ({type(exc).__name__})",file=sys.stderr)
        return 2
    report={"schema":"modelops.preflight.v1","result":"BLOCKED" if issues else "PASS_STATIC",
            "violations":issues,"secrets_verified_in_cluster":False,
            "runtime_verified":False}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 1 if issues else 0


if __name__=="__main__":
    raise SystemExit(main())
