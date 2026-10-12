"""Cryptographic separation between trusted evaluation worker and ModelOps API."""
import base64
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from modelops.config import Settings
from modelops.evidence import EvidenceError, digest_report, verify_report


def make_report():
    return {
        "schema": "modelops.heldout.v1", "proof_type": "real_checkpoint_holdout",
        "num_samples": 25, "train_overlap_count": 0,
        "generation_success_rate": 1.0, "artifact_sha256": "a" * 64,
        "heldout_sha256": "b" * 64,
        "metrics": {
            "base_token_f1": 0.65,
            "candidate_token_f1": 0.75,
            "delta_token_f1": 0.10,
        },
    }


def key_pair():
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )).decode()
    return private, public


def test_ed25519_worker_public_key_only_can_approve_real_report():
    private, public = key_pair()
    data = make_report()
    sig = base64.b64encode(private.sign(digest_report(data).encode("ascii"))).decode()
    artifact = SimpleNamespace(digest="a" * 64)
    dataset = SimpleNamespace(digest="b" * 64)
    passed, metrics = verify_report(data, sig, public, artifact, dataset, scheme="ed25519")
    assert passed and metrics["candidate_token_f1"] == 0.75
    with pytest.raises(EvidenceError):
        verify_report({**data, "num_samples": 26}, sig, public, artifact, dataset,
                      scheme="ed25519")
    other, _ = key_pair()
    with pytest.raises(EvidenceError):
        verify_report(data, base64.b64encode(other.sign(digest_report(data).encode())).decode(),
                      public, artifact, dataset, scheme="ed25519")
    with pytest.raises(EvidenceError):
        verify_report(data, sig, "not-a-base64-key", artifact, dataset,
                      scheme="ed25519")
    with pytest.raises(EvidenceError):
        verify_report(data, "0" * 64, "shared-dev-hmac-secret" * 3, artifact, dataset,
                      scheme="ed25519")


def test_production_configuration_requires_only_an_ed25519_public_key():
    _, public = key_pair()
    prod = Settings(
        database_url="postgresql+psycopg://modelops:pass@postgres.internal:5432/modelops",
        runtime="kubernetes", environment="production", auth_mode="oidc",
        oidc_issuer="https://idp.internal/realms/modelops",
        oidc_audience="modelops", oidc_jwks_url="https://idp.internal/keys",
        evidence_verify_key=public,
    )
    prod.validate()
    with pytest.raises(ValueError, match="public key"):
        Settings(**{**prod.__dict__, "evidence_verify_key": ""}).validate()
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(**{**prod.__dict__, "database_url": "sqlite:///models.db"}).validate()
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(**{**prod.__dict__, "oidc_issuer": "http://localhost/issuer"}).validate()
    with pytest.raises(ValueError, match="forbidden in production"):
        Settings(**{**prod.__dict__, "auth_mode": "dev", "jwt_secret": "x"*64}).validate()


def test_isolated_worker_signer_matches_api_verifier_and_refuses_key_leak(tmp_path):
    worker_script = (Path(__file__).resolve().parents[2] /
                     "pipelines/evaluation/sign_report.py")
    spec = importlib.util.spec_from_file_location("worker_signer", worker_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    private, public = key_pair()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    data = make_report()
    assert mod.canonical_digest(data) == digest_report(data).encode("ascii")
    signature = mod.sign(data, pem)
    passed, _ = verify_report(data, signature, public,
                              SimpleNamespace(digest=data["artifact_sha256"]),
                              SimpleNamespace(digest=data["heldout_sha256"]),
                              scheme="ed25519")
    assert passed

    key_file = tmp_path / "worker-signing-key.pem"
    report_file = tmp_path / "report.json"
    out = tmp_path / "signature.txt"
    key_file.write_bytes(pem)
    key_file.chmod(0o600)
    report_file.write_text(json.dumps(data))
    assert mod.main(["--report", str(report_file),
                     "--private-key-file", str(key_file),
                     "--signature-output", str(out)]) == 0
    assert out.read_text().strip() == signature
    if os.name == "posix":
        key_file.chmod(0o644)
        assert mod.main(["--report", str(report_file),
                         "--private-key-file", str(key_file),
                         "--signature-output", str(out)]) == 2
    assert pem not in out.read_bytes()
