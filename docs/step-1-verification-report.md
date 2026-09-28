# Step 1 Verification Report

- **Audit date:** 2026-09-27
- **Auditor:** Claude (the same agent that built Step 1, so the checks below are
  deliberately evidence-based rather than self-reported)
- **Scope:** Step 1 (engineering foundation) plus the Gemini provider added afterwards
  at the product owner's request
- **Environment:** macOS (arm64), Docker 29.8.0 / Compose v5.5.1, Node 24.21.0 / npm 11.19.0,
  uv 0.12.19, Python 3.12

## Executive Summary

**Overall status: PASS WITH FIXES**

The local foundation works end to end:

- All seven Compose services start and become healthy, with ordering driven by health
  checks.
- `/health` and `/ready` behave correctly, including detecting dependency outages and
  recovering from them.
- The asynchronous path API → Redis → Celery worker → result was proven by leaving a
  task queued in Redis with the worker stopped, then watching the worker drain it.
- PostgreSQL, Redis and MinIO are reachable through application code and configuration.
- 47/47 backend tests and 9/9 frontend tests pass. Lint and strict type checks pass.
  Dependency scans find no known vulnerabilities.

The audit found one **real defect**, which is fixed: the CI workflow referenced
`astral-sh/setup-uv@v10`, a tag that does not exist. Two of the three CI jobs would have
failed at "resolve action". The fix is verified statically only.

What is **not** verified:

- **CI has never executed.** Nothing from Step 1 is committed or pushed; the GitHub
  repository still contains only the original empty README.
- **Real-browser rendering** of the page was not verified. Headless Chrome did not
  complete in this environment.
- **A Docker start from a fresh clone** was not repeated during the audit. The isolated
  clean-copy stack run was stopped at the owner's request. Clean-copy frontend and
  backend checks did pass.

## Requirement Matrix

| # | Requirement | Status | Evidence | Notes |
| --- | --- | --- | --- | --- |
| 1 | Repository inspected before changes | PASS | `docs/initial-repository-audit.md` matches git history (1 commit, empty README) | |
| 2 | Repository audit documented | PASS | `docs/initial-repository-audit.md` | |
| 3 | Modular monolith, no microservices/K8s/Kafka | PASS | One backend image with API and worker entrypoints; 7 Compose services | |
| 4 | Clear project structure (web / api / worker / infra / docs / tests) | PASS | `apps/web`, `apps/backend/app/{api,worker}`, `docs`, `scripts`, `.github` | Deviations from the suggested layout are justified in ADR 0002 |
| 5 | Next.js + TypeScript (strict) + Tailwind | PASS | Next 16.3.6, `strict` + `noUncheckedIndexedAccess`, Tailwind 4; `tsc --noEmit` exit 0 | |
| 6 | Frontend lint and format | PASS | `npm run lint` (0 warnings allowed) and `npm run format:check` exit 0 | |
| 7 | Accessible HTML | PARTIAL | Landmarks, skip link, `role="status"`/`aria-live`; ESLint jsx-a11y rules; test asserts landmarks | No axe or Lighthouse audit was run |
| 8 | Responsive layout | NOT VERIFIED | Responsive Tailwind classes exist | Not viewed in a browser at multiple widths |
| 9 | Page shows product name and "Engineering foundation initialized." | PASS | Present in the HTML from Docker, `next start` and `next dev`; unit test | |
| 10 | Frontend environment-variable support | PASS | `API_INTERNAL_URL` read at runtime; route test stubs env; works in Docker (`http://api:8000`) | |
| 11 | Frontend starts | PASS | Docker `web` healthy; `npm run start` and `next dev` served pages on 3101/3102 | `next start` prints a warning with `output: standalone` (Q3) |
| 12 | Frontend ↔ backend communication | PASS | `GET :3000/api/backend-health` → `{"status":"ok"}` (web container → api container) | Server-side path verified |
| 13 | Status badge renders in a real browser | NOT VERIFIED | Component unit tests (4) only | Headless Chrome did not complete here |
| 14 | FastAPI app factory, settings, versioning | PASS | `create_app()`, pydantic-settings, `/api/v1` router | |
| 15 | Structured logging | PASS | All API/worker/cli logs are one-line JSON with request IDs | Alembic output is plain text; uvicorn adds `color_message` (Q4) |
| 16 | `GET /health` | PASS | 200 `{"status":"ok",...}`; touches no dependencies | |
| 17 | `GET /ready` | PASS | 200 with all `ok`; 503 with `redis: unavailable` when Redis was stopped; recovered in ≤2 s; also after a PostgreSQL restart | |
| 18 | No secrets or config in responses | PASS | `/ready` returns only ok/unavailable; production `/boom` returns a generic 500 with request ID; checked for secret strings | |
| 19 | Invalid configuration fails safely | PASS | 6 invalid configs rejected with clear messages and no secret echo; empty `DATABASE_URL` fails at startup | Empty required secrets pass settings validation (Q2) |
| 20 | No stack traces in production | PASS | Production-mode app: 500 body contains no traceback, exception text or secret; `/docs` and `/openapi.json` return 404 | |
| 21 | Backend foundation ready for future modules | PASS | Module layout documented in `docs/architecture.md` | |
| 22 | PostgreSQL + SQLAlchemy connection handling | PASS | `pool_pre_ping`, timeouts; 1 pooled connection after 20 `/ready` calls; readiness recovered after a PostgreSQL restart | |
| 23 | Alembic foundation, no premature schema | PASS | `alembic upgrade head` runs in `init` and on the host; only `alembic_version` exists | Autogenerate is not exercised yet (no models) |
| 24 | Redis via Compose, env-driven, readiness | PASS | PONG; the app sets/gets through settings; container uses `redis://redis:6379/0` from env | |
| 25 | Celery app, Redis broker, worker container, env config | PASS | `inspect registered` → `system.ping`; worker healthy | |
| 26 | Celery task executes (API → Redis → worker) | PASS | Worker stopped → API 504 and queue length 1 (task `327145e8…`) → worker started → queue 0, result `SUCCESS/pong` in Redis, worker "received"/"succeeded" logs; live round trip 64 ms | |
| 27 | MinIO via Compose, S3 config from env | PASS | HeadBucket ok; put/get/delete of synthetic object; wrong secret rejected (`ClientError`); console HTTP 200 | Third-party image (ADR 0006) |
| 28 | No hardcoded storage credentials | PASS | Source grep: no credentials; the only placeholder constant exists to reject it | |
| 29 | `.env.example` documents every variable | PASS | Every variable is consumed somewhere (table in Documentation Findings) | Two comments are inaccurate (D1, D2) |
| 30 | No real or realistic-looking secrets in the repo | PASS | Pattern scans of committable files: none | |
| 31 | Compose has all services, explicit deps, health checks | PASS | 7 services; `depends_on` with `service_healthy` / `service_completed_successfully` | |
| 32 | No arbitrary sleeps; dependencies retried | PASS | No `sleep`/wait-for scripts; lazy connections; `broker_connection_retry_on_startup`; recovery observed | |
| 33 | `docker compose up --build` works | PASS | Exit 0 in 24 s; all healthy; 0 restarts; no warnings or errors in logs | |
| 34 | Clean-start reproducibility (fresh clone) | PARTIAL | Clean copy of committable files: frontend (6 steps) and backend (7 steps) pass | Fresh-clone Docker run not repeated in the audit; nothing is pushed, so a real clone gets an empty repo |
| 35 | Backend tests: startup, health, ready, DB, Redis, Celery | PASS | 47 passed / 0 failed / 0 skipped / 0 errors | |
| 36 | Frontend tests: app and page render | PASS | 9 passed | |
| 37 | Deterministic tests | PASS | Unit tests isolated from the shell environment (verified with `.env` exported); no sleeps or randomness in assertions | Integration tests need the developer's `.env` ports (by design) |
| 38 | AI provider abstraction and mock | PASS | `AIProvider` protocol; SDK import confined to `app/ai/gemini.py`; `google.genai` not loaded at app start | |
| 39 | No real AI calls in tests | PASS | Fake client injected; no Anthropic SDK in `uv.lock` | |
| 40 | Security baseline: CORS, size limit, safe errors, logs | PASS | Evil origin gets no ACAO header and preflight 400; 2 MB body → 413; web security headers present | |
| 41 | Dependencies pinned and locked | PASS | `uv.lock`, `package-lock.json`, images pinned by digest | |
| 42 | `.gitignore` correct | PASS | `.env` ignored (`git check-ignore`); no `node_modules`, `.venv`, `.next` or DB files committable | |
| 43 | `docs/security-baseline.md` without a production-secure claim | PASS | States "not production-secure" | |
| 44 | Backend lint, format, type check | PASS | Ruff check/format and mypy `--strict`: 46 files, exit 0 | |
| 45 | CI workflow covers all required checks | PASS | Backend, frontend and Docker-stack jobs mirror every local check | |
| 46 | CI configuration valid | PASS (after fix) | actionlint 1.7.12 clean; YAML parses; every `uses:` ref resolves; every input exists at that ref | Before the fix: FAIL (unresolvable `setup-uv@v10`) |
| 47 | CI executed successfully on GitHub | NOT VERIFIED | `git ls-remote origin` → only `20b2589` (empty README) | Never pushed, never run |
| 48 | README / architecture / ADRs | PASS | All present; host-run and Docker instructions executed successfully | Minor inaccuracies (D1–D4) |
| 49 | Business functionality not implemented | PASS | Routes: `/health`, `/ready`, `/api/v1/diagnostics/worker-ping`; task: `system.ping` only | Gemini provider exists (owner-requested) |

Totals (49 rows): 44 PASS (1 after a fix), 2 PARTIAL, 3 NOT VERIFIED, 0 FAIL remaining.

## Runtime Verification

### Frontend

Commands, run in a **clean copy** of only the git-committable files, in CI order (no
`node_modules`, `.next` or `next-env.d.ts`):

```
npm ci --no-audit --no-fund          exit 0
npm run lint                         exit 0
npm run format:check                 exit 0
npm run typecheck                    exit 0   (before build, as CI does; next-env.d.ts absent)
npm test                             exit 0   (9 passed)
npm run build                        exit 0   (routes: /, /_not-found, ƒ /api/backend-health)
API_INTERNAL_URL=http://localhost:8000 PORT=3101 npm run start
API_INTERNAL_URL=http://localhost:8000 npx next dev -p 3102
curl localhost:3000/ ; curl localhost:3000/api/backend-health   (Docker)
```

Results:

- Every step passed.
- All three startup modes (Docker, `next start`, `next dev`) served the heading and
  "Engineering foundation initialized." The proxy returned `{"status":"ok"}`.
- `npm run start` logged: *"next start" does not work with "output: standalone"*.
- Web security headers are present. `X-Powered-By` is absent.

### Backend

Commands, in the clean copy (CI order) and in the working repo:

```
uv sync --frozen --python 3.12                    exit 0
uv run ruff check .                               All checks passed
uv run ruff format --check .                      46 files already formatted
uv run mypy                                       no issues in 46 files
uv run pytest -m "not integration"                41 passed
uv sync --frozen --no-dev && uv run --no-sync python -c "import app.main, app.cli, app.worker.tasks, app.ai, app.ai.gemini"   exit 0
uv run pytest -rsxX                               47 passed (junit: tests=47 failures=0 errors=0 skipped=0)
uv run uvicorn app.main:create_app --factory --reload --port 8099   (/ready → 200)
uv run celery -A app.worker.main worker           (worker "ready")
curl /health /ready /nope /docs /openapi.json; CORS and preflight probes; X-Request-ID probes
Production-mode create_app() via TestClient: /boom, /docs, /openapi.json, diagnostics, /ready
docker compose exec -T -e <invalid values> api python -c "get_settings()"   (7 cases)
```

Results:

- **Development endpoints:** 200 for health, ready, docs and openapi; 404 envelope for
  unknown routes.
- **Production mode:**
  - `/boom` returns 500 `{"error":{"code":"internal_error",…,"request_id":…}}` with no
    traceback, exception text or secret.
  - `/docs`, `/openapi.json` and the diagnostics endpoint return 404.
  - `/ready` with dependencies down returns 503 with no hostnames or secrets.
- **Invalid configuration** is rejected, exit 1, with no secret in the output:
  - placeholder secret in production
  - diagnostics enabled in production
  - `APP_ENV=bogus`
  - `MAX_REQUEST_BODY_BYTES=-5`
  - wildcard CORS in production
  - `AI_PROVIDER=gemini` with an empty key
- **Empty `DATABASE_URL`** is accepted by settings, and the API then aborts at startup
  with SQLAlchemy "Could not parse SQLAlchemy URL" (fails safely, no secret shown).
- **Request IDs:** invalid incoming IDs (spaces, 80 characters) are replaced with a
  generated ID.

### PostgreSQL

Commands:

```
pg_isready ; psql -c "select version()"            accepting connections; PostgreSQL 17.11
psql -c "select table_name … schema public"        alembic_version (only)
docker compose exec api alembic current            (no revision; none exist)
pg_stat_activity count before/after 20 /ready      1 → 1
docker compose restart postgres ; poll /ready      database ok after 2 s
```

Results: PostgreSQL is healthy. The app connects through a pool that reuses a single
connection, and readiness recovers after a PostgreSQL restart without restarting the
API. There is no domain schema. The server runs as uid 70, not root.

### Redis

Commands:

```
redis-cli ping ; config get appendonly ; info clients     PONG; appendonly yes; 17 clients
api container: create_redis_client(get_settings()) ping/set/get   ok
docker compose stop redis ; curl /ready                   503, redis: unavailable
docker compose start redis ; poll /ready                  200 after 1 s
```

Results: PASS. The URL comes from the environment (`redis://redis:6379/0` inside
Compose). The server runs as uid 999. The 17 connected clients come mostly from the
Celery worker and its health-check processes.

### Celery

Commands:

```
docker compose stop worker
LLEN celery                                              0
curl -X POST :8000/api/v1/diagnostics/worker-ping        504 "No worker completed the task in time"
LLEN celery ; LINDEX celery 0                            1 ; task system.ping id 327145e8-…
GET celery-task-meta-<id>                                (empty)
docker compose start worker ; poll result key            SUCCESS / "pong" after 3 s; LLEN 0
docker compose logs worker | grep <id>                   "received" then "succeeded … 'pong'"
curl -X POST …/worker-ping (worker up)                   200 {"status":"SUCCESS","result":"pong"} in 64 ms
celery inspect registered                                system.ping; 1 node online
```

Results: every hop is proven with observable state:

- the API accepts and enqueues the task
- Redis holds the message
- the worker receives and executes it
- the result is stored in Redis
- the API reads the result back

The worker also survived Redis and PostgreSQL restarts (0 container restarts).

### MinIO

Commands, in the api container, using application settings and code:

```
ping_bucket ; list_buckets                         HeadBucket ok; ['invoice-risk-documents']
put/get/delete audit/<uuid>.txt (synthetic bytes)  round trip identical; 0 objects left
S3_SECRET_ACCESS_KEY=wrong-secret → ping_bucket    rejected: ClientError
curl :9001/ ; curl :9000/minio/health/live         200 ; 200
```

Results: PASS. Credentials come from settings. No credentials exist in application
source. No customer data was used.

### Docker Compose

Commands:

```
docker compose down ; docker compose up --build -d --wait --wait-timeout 300   exit 0 in 24 s
docker compose ps -a                         6 running (healthy), init Exited (0)
docker inspect: RestartCount                 0 for all services
docker compose logs | grep warn/error/…      none
grep sleep|wait-for in compose/Dockerfiles   none
docker top postgres/redis; exec id -u        processes non-root (70, 999, 10001, 1000, 65532)
docker inspect PortBindings / Privileged     all ports 127.0.0.1; privileged=false; only named volumes
docker save <image> | grep <gemini key>      0 matches in either image; no .env in images
scripts/smoke-test.sh                        7/7 PASS
```

Results: PASS.

- Volumes were preserved in this audit run. A full `down --volumes` reset followed by
  `up --build` succeeded earlier in the same session, before the Gemini change.
- Minor observation: the worker container shows `8000/tcp` because it inherits `EXPOSE`
  from the shared image. It is not published.

## Test Results

| Suite | Total | Passed | Failed | Skipped | Errors |
| --- | --- | --- | --- | --- | --- |
| Backend unit (`-m "not integration"`) | 41 | 41 | 0 | 0 | 0 |
| Backend integration (real PostgreSQL/Redis/MinIO/Celery) | 6 | 6 | 0 | 0 | 0 |
| **Backend total** | **47** | **47** | **0** | **0** | **0** |
| Frontend (Vitest) | 9 | 9 | 0 | 0 | 0 |
| Smoke test (live stack) | 7 checks | 7 | 0 | – | – |

No `skip`, `skipif`, `xfail`, `.skip`, `.todo`, `.only` or TODO markers exist in the
tests or application code.

### Test-quality observations

- **Meaningful tests.** Most tests assert concrete behaviour: status codes, exact
  bodies, absence of secrets, queue and result state. Integration tests hit real
  services and fail (rather than skip) when the services are absent.
- **Weak assertions.** `test_responses_carry_request_id` only asserts that an invalid ID
  is *not echoed* (it should assert a 32-character generated ID), and
  `test_app_starts_and_stops_cleanly` asserts little beyond `resources is not None`. The
  underlying behaviour was verified manually in this audit.
- **Integration coverage gaps.**
  - `test_celery_task_executes_through_redis` uses an in-process test worker. The
    containerised worker is covered only by the smoke test and the CI stack job.
  - `test_ready_endpoint_against_real_dependencies` creates the bucket first, so it
    would not detect an `init` failure (the smoke test would).
- **Environment dependence.** Integration tests depend on the developer's `.env`
  (host ports). This is by design and documented. Unit tests are isolated from the
  shell environment by `tests/unit/conftest.py`.
- **Missing tests.** No automated test covers `app.cli ensure-bucket`, Alembic
  migration execution, or `configure_logging` wiring. They are exercised by the `init`
  container and the smoke test.

## CI Verification

| Aspect | Status | Evidence |
| --- | --- | --- |
| Workflow configuration valid | **Verified (after fix)** | actionlint 1.7.12: no findings; YAML parses (3 jobs) |
| Action refs resolve and inputs exist | **Verified (after fix)** | Shallow-cloned `actions/checkout@v7`, `actions/setup-node@v7`, `astral-sh/setup-uv@v10.2.0`; all used inputs present; `setup-uv@v10` → "Remote branch v10 not found" |
| Job commands work | **Verified locally** | Backend and frontend job commands run in a clean copy, all exit 0. Stack-job commands were run locally with a port-adjusted `.env`. |
| No failure masking | Verified | No `continue-on-error` or `|| true` in the workflow; the smoke test exits 1 on any failed check |
| No embedded secrets | Verified | The workflow uses only `.env.example`; token permissions are `contents: read` |
| **Actual execution on GitHub** | **NOT VERIFIED** | Nothing pushed (`origin/main` = `20b2589`). The run history could not be queried (`gh` not installed; API unauthenticated). |

## Security Findings

| ID | Finding | Severity | Status |
| --- | --- | --- | --- |
| S1 | Committed secrets, keys, private keys or provider tokens | – | None found. Scans cover committable files and git history (1 commit). |
| S2 | The local `.env` contains a real Gemini API key (53 chars; value not printed) | Info | Correctly handled: git-ignored; absent from committable files, container logs and both images |
| S3 | No authentication, authorisation or tenant isolation | High (for the product) | Intentionally deferred. No data or business endpoints exist yet. |
| S4 | Redis has no password; PostgreSQL and MinIO use development credentials | Low | Accepted for local development. All ports bind to 127.0.0.1. |
| S5 | No Content-Security-Policy | Low | Documented limitation |
| S6 | Log redaction is key-based. Exception text in server-side logs could contain sensitive values. | Low | Documented limitation. Client responses are safe. |
| S7 | `/docs` and `/openapi.json` are exposed in development | Info | Disabled in production (verified) |
| S8 | Dependency vulnerabilities | – | `npm audit`: 0 (all and prod-only). `pip-audit` on the locked requirements: none. |
| S9 | Container hardening | – | Non-root processes everywhere; no privileged containers; no host bind mounts; no `.env` in images |
| S10 | npm blocked the `unrs-resolver` postinstall script | Info | Lint works without it. Leaving it blocked is the safer default. |
| S11 | MinIO image is a third-party build (Chainguard) with only a `latest` tag | Medium | Pinned by digest; ADR 0006. Supply-chain and maintenance risk. |

## Documentation Findings

A new developer following the README can configure `.env`, start Compose, reach
every service, run every check, and understand the architecture. **All of those
commands were executed successfully during this audit.** Findings:

| ID | Finding | Severity |
| --- | --- | --- |
| D0 | The repository is not committed or pushed, so "clone the repository" currently yields only an empty README | **High** (process, not documentation) |
| D1 | `.env.example` says `FRONTEND_URL` is "used for docs/CORS alignment". Only `scripts/smoke-test.sh` reads it (as does `BACKEND_URL`). CORS uses `CORS_ALLOWED_ORIGINS`. | Low |
| D2 | `.env.example` presents `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` as options, but `docker-compose.yml` does not pass them to containers, so they only affect host-run processes | Low |
| D3 | `package.json` `start` (`next start`) is unsupported with `output: "standalone"`. It works, but Next.js warns. The README does not use it. | Low |
| D4 | README says Step 1 contains "only the engineering foundation", but a working Gemini provider now exists (documented in the README "Using Gemini" section and ADR 0007) | Info |
| D5 | README prerequisites omit `bash` and `curl` for `scripts/smoke-test.sh` (present by default on macOS and Linux; not Windows-friendly) | Info |

## Code Quality Findings

No critical or high findings in the code itself.

| ID | Area | Finding | Severity |
| --- | --- | --- | --- |
| Q1 | CI | Unresolvable action ref `astral-sh/setup-uv@v10` (**fixed**, see below) | High (before fix) |
| Q2 | Config | Required secrets accept empty strings (e.g. `DATABASE_URL=`), so misconfiguration surfaces at startup as a SQLAlchemy error rather than a settings error | Low |
| Q3 | Web | `npm run start` script is incompatible with standalone output (D3) | Low |
| Q4 | Logging | uvicorn `color_message` fields (with ANSI escapes) leak into the JSON logs; Alembic output in `init` is plain text | Low |
| Q5 | Worker | The health check spawns a full `celery inspect ping` process every 15 s: extra CPU, memory and Redis connections | Low |
| Q6 | API | Readiness timeouts stop waiting but do not cancel the worker thread. A hung dependency under frequent probing could accumulate threads. | Low |
| Q7 | API | The diagnostics endpoint blocks a threadpool thread for up to 10 s (development only) | Low |
| Q8 | API | `app.state.resources` / `celery` / `readiness_checks` are untyped attribute access | Low |
| Q9 | Tests | Weak assertions and coverage gaps (see Test-quality observations) | Low |
| Q10 | Repo | Scaffold artefacts: `apps/web/AGENTS.md` and `CLAUDE.md` (generated; `next dev` re-adds them) and the default Next.js favicon | Low |
| Q11 | AI | The default `GEMINI_MODEL=gemini-2.5-flash` may be retired by Google; it is configurable | Low |
| Q12 | Logging | `create_app()` reconfigures the global root logger (fine for one app per process) | Low |
| Q13 | Worker | Celery clock-drift warning when a host worker and a container worker run at once (different local timezones). Seen only in the audit's mixed setup. | Low |
| Q14 | Tests | An upstream Celery → redis-py `setex` deprecation warning is suppressed by a narrowly scoped filter | Info |

The separation of concerns is sound: settings, logging, middleware, infrastructure
clients, API layer, worker and AI boundary each live in their own module. There is no
duplicated logic or hidden global state beyond the cached settings and the root logger.

## Scope Violations

- **No Step 2+ business functionality exists.** There is no invoice, vendor, OCR, risk,
  PO, approval, payment, billing or ERP code. The exposed routes are `/health`, `/ready`
  and `/api/v1/diagnostics/worker-ping`. The only Celery task is `system.ping`. The
  database contains only `alembic_version`.
- **Beyond the original Step 1 brief:** a working `GeminiProvider` (`app/ai/gemini.py`,
  dependency `google-genai`, settings `GEMINI_API_KEY` / `GEMINI_MODEL` /
  `AI_REQUEST_TIMEOUT_SECONDS`). It was added at the owner's explicit request after
  Step 1. No code path calls it. Left in place; the owner decides whether it stays.

## Fixes Made During Audit

| File | Problem | Change | Verification |
| --- | --- | --- | --- |
| `.github/workflows/ci.yml` (lines 24, 87) | `uses: astral-sh/setup-uv@v10`: no `v10` tag exists upstream (only `v10.0.0`–`v10.2.0`), so the backend and stack jobs would fail at action resolution | Pinned to `astral-sh/setup-uv@v10.2.0`, with a comment | `git clone --branch v10` → "Remote branch v10 not found"; `--branch v10.2.0` succeeds and its `action.yml` defines `version`, `enable-cache` and `cache-dependency-glob`; actionlint clean afterwards. **Not verified by a real GitHub run.** |

No other files were changed by the audit. The audit also removed a stray `.env` it had
created in its own scratch copy (outside the repository) after the owner stopped the
isolated Docker run.

## Known Limitations

- CI has never run. Its first execution may reveal environment-specific issues
  (runner Docker/Compose versions, cache behaviour, timing of `--wait`).
- A fresh-clone Docker start was not repeated in this audit. Clean-volume startup was
  verified earlier in the session.
- Browser-side behaviour (client-rendered status badge, responsive layout,
  accessibility) was not verified in a real browser.
- A real Gemini call was not made. The provider is verified only against a fake client
  and by construction inside the container.
- Only macOS/arm64 was tested locally. CI targets linux/amd64 (the images are
  multi-arch, but that is unverified).

## Recommended Actions

### Required before Step 2

1. Commit the Step 1 work, push it, and confirm a **green CI run on GitHub**. That
   closes items 34 and 47 and validates the `setup-uv` fix.
2. Decide whether the Gemini provider stays in the foundation (scope decision).

### Recommended later

- Make required settings reject empty strings (Q2); correct the `.env.example` comments
  (D1, D2); fix or remove the `start` script (D3).
- Strengthen the weak test assertions; add tests for `ensure-bucket` and for running
  migrations against a real database.
- Replace the heavy worker health check with a lighter liveness signal (Q5); drop
  `color_message` from JSON logs (Q4).
- Run a browser-based check (Playwright smoke test and axe) in CI.
- Add Dependabot, image scanning (Trivy) and secret scanning (gitleaks) to CI.
- Add `.gitattributes` for line endings before Windows contributors join.

### Intentionally deferred (later steps)

- Authentication, RBAC, tenant isolation, audit trail, CSP, rate limiting, TLS,
  secret manager, managed S3 with India data residency, Anthropic provider, and all
  business functionality (see `docs/security-baseline.md`).

### Step 1 foundation readiness vs. production readiness

The **Step 1 foundation is ready to build on**: the local stack, tooling and
architecture seams work and are verified. The **product is not production-ready**
and should not be described as such. It has no authentication, authorisation, tenant
isolation, audit trail, deployment target, TLS, backups, monitoring or alerting,
secret management, data-residency controls, or any business functionality.

## Final Decision

**STEP 1 VERIFIED WITH NON-BLOCKING ISSUES**

Every runtime requirement of Step 1 was demonstrated with direct evidence in the live
environment. The one real defect found (an invalid CI action ref) is fixed. The
remaining gaps are CI never having executed, the unrepeated fresh-clone Docker run, and
unverified browser rendering. They do not block Step 1's local foundation, but item 1
under "Required before Step 2" (a green CI run on GitHub) must be done before Step 2
builds on it.
