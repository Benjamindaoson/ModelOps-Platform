"""Secure-by-default application configuration."""
from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./modelops.db"
    runtime: str = "disabled"
    environment: str = "development"
    auth_mode: str = "oidc"
    jwt_secret: str = ""
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    k8s_context: str = ""
    cors_origin: str = ""
    evidence_verify_key: str = ""
    artifact_root: str = ""
    gpu_python: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv("MODELOPS_DATABASE_URL", "sqlite:///./modelops.db"),
            runtime=os.getenv("MODELOPS_RUNTIME", "disabled"),
            environment=os.getenv("MODELOPS_ENV", "development"),
            auth_mode=os.getenv("MODELOPS_AUTH_MODE", "oidc"),
            jwt_secret=os.getenv("MODELOPS_JWT_SECRET", ""),
            oidc_issuer=os.getenv("MODELOPS_OIDC_ISSUER", ""),
            oidc_audience=os.getenv("MODELOPS_OIDC_AUDIENCE", ""),
            oidc_jwks_url=os.getenv("MODELOPS_OIDC_JWKS_URL", ""),
            k8s_context=os.getenv("MODELOPS_K8S_CONTEXT", ""),
            cors_origin=os.getenv("MODELOPS_CORS_ORIGIN", ""),
            evidence_verify_key=os.getenv("MODELOPS_EVIDENCE_VERIFY_KEY", ""),
            artifact_root=os.getenv("MODELOPS_ARTIFACT_ROOT", ""),
            gpu_python=os.getenv("MODELOPS_GPU_PYTHON", ""),
        )

    def validate(self) -> None:
        if self.environment not in {"development", "production", "test"}:
            raise ValueError("MODELOPS_ENV must be development, production or test")
        if self.runtime not in {"disabled", "kubernetes", "linux"}:
            raise ValueError("MODELOPS_RUNTIME must be disabled, kubernetes or linux")
        if self.runtime == "linux" and not (self.artifact_root and self.gpu_python):
            raise ValueError("Linux runtime requires explicit artifact root and GPU interpreter")
        if self.auth_mode == "dev":
            if self.environment == "production" or len(self.jwt_secret) < 32:
                raise ValueError("Development JWT auth is forbidden in production; set a random 32+ char secret only for dev/tests")
        elif self.auth_mode == "oidc":
            if not all([self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url]):
                raise ValueError("OIDC requires issuer, audience and JWKS URL")
            if not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("OIDC JWKS must be HTTPS")
        else:
            raise ValueError("MODELOPS_AUTH_MODE must be dev or oidc")
        if self.environment == "production":
            if self.runtime != "kubernetes":
                raise ValueError("Production requires real Kubernetes runtime")
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL with psycopg")
            if not self.oidc_issuer.startswith("https://"):
                raise ValueError("Production requires an HTTPS OIDC issuer")
            try:
                public = base64.b64decode(self.evidence_verify_key, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Production requires base64 Ed25519 public key") from exc
            if len(public) != 32:
                raise ValueError("Production requires 32-byte Ed25519 verifier public key")
