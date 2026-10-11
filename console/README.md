# ModelOps Console

This is the first-party product console for the existing ModelOps Kubernetes Operator, backed by `control-plane/` FastAPI. No fake API data or starter dashboard counts: every model, dataset, job, deployment, evaluation and audit row comes from the authenticated Control API.

## Local development

1. Start control-plane using its README and generate an expiring development JWT.
2. `cd console && npm install && cp .env.example .env.local && npm run dev`.
3. Open http://localhost:3000, paste an OIDC access token into the session login form. Server verifies it at `GET /api/v1/me` before setting an HttpOnly, SameSite=Strict session cookie. Token is never saved to localStorage or exposed in NEXT_PUBLIC vars.
4. In offline metadata mode you can register model and dataset provenance, but deployments/actual training are blocked with an honest 503 (no demo success simulation).

The `/api/control/*` server-side route forwards requests to the single control API with the token read from the session cookie. Mutating requests enforce Origin checks. For enterprise production, deploy behind HTTPS, configure `MODELOPS_PUBLIC_ORIGIN`, and connect a real OIDC login flow with secure session expiry/refresh. The manual token form is an engineering-preview entry point, **not production-ready authentication UX**.
