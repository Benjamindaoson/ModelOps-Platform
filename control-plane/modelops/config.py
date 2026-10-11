"""Secure-by-default application configuration."""
from __future__ import annotations

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
            if not self.oidc_jwks_url.startswith("https://"):
                raise ValueError("OIDC JWKS must be HTTPS")
        else:
            raise ValueError("MODELOPS_AUTH_MODE must be dev or oidc")
        if self.environment == "production":
            if self.runtime != "kubernetes":
                raise ValueError("Production requires real Kubernetes runtime")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production requires durable PostgreSQL")
