# ModelOps Console

This is the first-party product console for the existing ModelOps Kubernetes Operator, backed by `control-plane/` FastAPI. No fake API data or starter dashboard counts: every model, dataset, job, deployment, evaluation and audit row comes from the authenticated Control API.

## Local development

1. Start control-plane using its README and generate an expiring development JWT.
2. `cd console && npm install && cp .env.example .env.local && npm run dev`.
3. Open http://localhost:3000, paste an OIDC access token into the session login form. Server verifies it at `GET /api/v1/me` before setting an HttpOnly, SameSite=Strict session cookie. Token is never saved to localStorage or exposed in NEXT_PUBLIC vars.
4. In offline metadata mode you can register model and dataset provenance, but deployments/actual training are blocked with an honest 503 (no demo success simulation).

The `/api/control/*` server-side route forwards requests to the single control API with the token read from the session cookie. Mutating requests enforce Origin checks. For enterprise production, deploy behind HTTPS, configure `MODELOPS_PUBLIC_ORIGIN`, and connect a real OIDC login flow with secure session expiry/refresh. The manual token form is an engineering-preview entry point, **not production-ready authentication UX**.

## Enterprise OIDC login (production)

Configure the console server with `MODELOPS_ENV=production`,
`MODELOPS_CONSOLE_AUTH=oidc`, `MODELOPS_OIDC_ISSUER`,
`MODELOPS_OIDC_CLIENT_ID`, `MODELOPS_PUBLIC_ORIGIN` (HTTPS).
Provide `MODELOPS_OIDC_CLIENT_SECRET` only if your IdP requires a
confidential client. Register `https://<domain>/api/auth/callback` as
the exact redirect URI. Only the server exchanges the authorization code;
a PKCE S256 verifier and CSRF state are held in short-lived, HttpOnly cookies.
Access-token issuer, audience, signature, tenant and role claims are checked
by the FastAPI Control API before creating a session.

The manual token form is restricted to an explicitly configured
development environment. Runtime origins and OIDC endpoints must match
the configured issuer, preventing user-provided SSRF redirect targets.

The OIDC flow implementation is type/build-tested; integration with an
actual external enterprise IdP remains an independent production acceptance
gate.
