"""Generate an expiring JWT only for local development/testing, never in prod."""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

import jwt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--role", choices=("viewer", "editor", "admin"), required=True)
    p.add_argument("--minutes", type=int, default=30)
    args = p.parse_args()
    if os.getenv("MODELOPS_ENV") != "development" or os.getenv("MODELOPS_AUTH_MODE") != "dev":
        raise SystemExit("Local development token issuance is disabled outside dev mode")
    secret = os.getenv("MODELOPS_JWT_SECRET", "")
    if len(secret) < 32 or not 1 <= args.minutes <= 120:
        raise SystemExit("Configure a 32+ char secret and duration of 1–120 minutes")
    now = datetime.now(timezone.utc)
    print(jwt.encode({"iss": "modelops-local", "aud": "modelops-dev", "sub": args.subject,
                      "tenant": args.tenant, "role": args.role,
                      "iat": now, "exp": now + timedelta(minutes=args.minutes)},
                     secret, algorithm="HS256"))


if __name__ == "__main__":
    main()
