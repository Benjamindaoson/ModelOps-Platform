"""Secure-by-default application configuration."""
from __future__ import annotations

import base64
import binascii
import os
from urllib.parse import urlparse
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
        )

    def validate(self) -> None:
        if self.environment not in {"development", "production", "test"}:
            raise ValueError("MODELOPS_ENV must be development, production or test")
        if self.runtime not in {"disabled", "kubernetes"}:
            raise ValueError("MODELOPS_RUNTIME must be disabled or kubernetes")
        if self.auth_mode == "dev":
            if self.environment == "production" or len(self.jwt_secret) < 32:
                raise ValueError("Development JWT auth is forbidden in production; set a random 32+ char secret only for dev/tests")
        elif self.auth_mode == "oidc":
            if not all([self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url]):
                raise ValueError("OIDC requires issuer, audience and JWKS URL")
            parsed = urlparse(self.oidc_jwks_url)
            issuer = urlparse(self.oidc_issuer)
            if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password
                or parsed.fragment or parsed.query
                or issuer.scheme != "https" or not issuer.hostname
                or parsed.hostname != issuer.hostname):
                raise ValueError("OIDC issuer and JWKS must use matching HTTPS hosts without URL credentials")
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
