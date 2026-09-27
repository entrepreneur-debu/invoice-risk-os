# Security Baseline

**This application is not production-secure.** Step 1 sets up hygiene and safe
defaults only. There is no authentication, authorisation or tenant isolation yet,
because no data or business endpoints exist yet.

## Current controls

### Secrets and configuration
- All configuration comes from environment variables (`app/core/config.py`). Nothing
  secret is hard-coded or baked into images.
- `.env` is git-ignored and excluded from both Docker build contexts. Only
  `.env.example` is committed, and it holds obvious development placeholders.
- Secrets are typed `SecretStr`, so they are masked in `repr()` and logs.
- The settings default to `APP_ENV=production`, and production mode **refuses to
  start** with the placeholder or a short (< 32 chars) `APP_SECRET_KEY`, wildcard CORS,
  or diagnostics endpoints enabled.
- Settings validation errors never echo input values (`hide_input_in_errors`), so a
  misconfiguration cannot print DSNs or keys into startup logs.
- Compose passes each backend container only the variables it needs.

### HTTP API
- **CORS:** an explicit origin allow-list from `CORS_ALLOWED_ORIGINS`. No credentials
  and a fixed set of methods and headers.
- **Request size:** bodies over `MAX_REQUEST_BODY_BYTES` (default 1 MiB) get 413. Both
  the declared `Content-Length` and streamed/chunked bodies are enforced.
- **Error responses:** a single JSON envelope. Unhandled exceptions return a generic
  500 with a request ID. Stack traces and exception text are logged server-side only.
  FastAPI `debug` is always off. Validation errors echo field locations, never input
  values.
- `/docs` and `/openapi.json` are disabled in production.
- `/ready` reports only `ok` / `unavailable` per dependency, never hostnames, errors or
  configuration.
- Diagnostics endpoints (`/api/v1/diagnostics/*`) are mounted only when explicitly
  enabled, and settings validation forbids them in production.
- Incoming `X-Request-ID` values are validated (`[A-Za-z0-9._-]{1,64}`) to prevent log
  or header injection.

### Web
- The browser never receives the API's internal URL. `API_INTERNAL_URL` is server-only.
- Headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`.
  `X-Powered-By` is removed.
- `robots.txt` disallows indexing.

### Logging
- Structured JSON logs (one object per line) with request ID, method, path, status and
  duration.
- Headers, query strings and bodies are **not** logged. `extra` fields whose names look
  sensitive (password, secret, token, api_key, authorization, cookie, credential,
  database_url, redis_url) are redacted.
- SQLAlchemy runs with `hide_parameters=True`, so bound values stay out of error messages.

### AI provider keys
- `GEMINI_API_KEY` (and the reserved `ANTHROPIC_API_KEY`) are `SecretStr`, set only
  in `.env` or the environment. Settings refuse `AI_PROVIDER=gemini` without a key.
- Automated tests use `MockAIProvider` or a fake Gemini client and never call a real API.
- Provider error messages are not propagated, only the HTTP status, because they may
  echo request content.

### Workers
- Celery accepts JSON only, never pickle, so untrusted payloads are never unpickled.

### Containers and infrastructure
- API, worker, web and MinIO containers run as non-root users.
- Base images are pinned by digest. Python and npm dependencies are locked
  (`uv.lock`, `package-lock.json`).
- Every published port binds to `127.0.0.1`, so nothing is exposed on the LAN.
- Tests use synthetic data only. No customer data or real credentials are in the repo.

### CI
- The workflow token is read-only (`permissions: contents: read`).
- Ruff's bandit (`S`) rules run on every backend change.

## Known limitations

- No authentication, authorisation, RBAC, sessions or CSRF protection. `APP_SECRET_KEY`
  exists but nothing uses it yet.
- No rate limiting or abuse protection.
- No TLS. The local stack is plain HTTP. TLS must terminate at an ingress or load
  balancer in any deployed environment.
- No Content-Security-Policy yet (it needs nonce planning with Next.js).
- Data is not encrypted at rest by the application. Local volumes are unencrypted.
  Local Redis and MinIO use development credentials, and Redis has no password.
- No audit log.
- No automated dependency or image vulnerability scanning, and no secret scanning in CI.
- Log redaction is by key name only. It cannot detect secrets embedded in free-text
  messages.
- MinIO comes from a third-party (Chainguard) build pinned by digest (ADR 0006).

## Future requirements (by later steps)

- **Identity:** authentication (SSO/OIDC for B2B), MFA, secure sessions or tokens,
  CSRF protection where cookies are used.
- **Authorisation:** organisation (tenant) isolation enforced in every query, RBAC,
  maker-checker (segregation of duties) for approvals and payments.
- **Audit:** an append-only, tamper-evident audit trail of every financial decision,
  approval and configuration change.
- **Documents:** upload validation (type sniffing, size limits per route, malware
  scanning), private buckets, short-lived pre-signed URLs, encryption at rest.
- **Compliance (India):** DPDP Act 2023 obligations, data residency for customer data,
  retention and deletion policies, GST data handling.
- **AI:** redaction or minimisation of data sent to providers, prompt-injection
  defences for invoice content, logging of AI inputs and outputs for explainability,
  a per-tenant provider policy.
- **Operations:** a secret manager, key rotation, rate limiting, WAF, CSP, dependency,
  image and secret scanning in CI (e.g. Dependabot, Trivy, gitleaks), security
  monitoring and alerting, backups with restore tests.
- **Payments:** strong controls before any payment execution (dual approval,
  bank-account change verification, velocity limits).
