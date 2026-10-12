"""Bearer JWT verification and server-side tenant role policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from .config import Settings

ROLE_LEVEL = {"viewer": 0, "editor": 1, "admin": 2}


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    role: str

    def require(self, minimum: str) -> None:
        if ROLE_LEVEL[self.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


class Verifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = PyJWKClient(settings.oidc_jwks_url) if settings.auth_mode == "oidc" else None

    def verify(self, token: str) -> Principal:
        try:
            if self.settings.auth_mode == "dev":
                claims = jwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"],
                                    audience="modelops-dev", issuer="modelops-local")
            else:
                key = self.jwks.get_signing_key_from_jwt(token)
                claims = jwt.decode(token, key.key, algorithms=["RS256"],
                                    audience=self.settings.oidc_audience, issuer=self.settings.oidc_issuer)
            subject, tenant, role = claims.get("sub"), claims.get("tenant"), claims.get("role")
            if (not isinstance(subject, str) or not subject.strip() or
                not isinstance(tenant, str) or not tenant.strip() or
                role not in ROLE_LEVEL):
                raise ValueError("Missing tenant/role/sub")
            if not tenant.replace("-", "").isalnum() or len(tenant) > 40 or tenant.lower() != tenant:
                raise ValueError("Invalid tenant claim")
            return Principal(subject=subject, tenant=tenant, role=role)
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=401, detail="Invalid bearer token") from exc


def require_principal(request: Request) -> Principal:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not header[7:].strip():
        raise HTTPException(status_code=401, detail="Bearer token required")
    return request.app.state.verifier.verify(header[7:].strip())
