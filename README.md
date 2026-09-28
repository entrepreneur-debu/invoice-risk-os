# Invoice Risk & Payment Control OS

> **Every invoice gets checked before your business pays it.** The payment firewall for
> Indian B2B finance teams.

Invoices arrive by upload, link or email. The system then:
1. stores the original and extracts its data with provenance (Gemini + text layer);
2. matches the vendor and purchase order;
3. runs **28 deterministic, explainable risk rules**: duplicates, bank-account changes,
   PO mismatches, GST arithmetic, anomalies, invoice splitting and more;
4. adds a clearly labelled AI explanation;
5. routes the invoice to human reviewers, with a second approver for high value or high
   risk, and records everything in a tamper-evident audit trail.

**Humans decide. The system never pays, never auto-approves, and never calls anything
"fraud".**

**Status: V1 release candidate.** Built, tested and runnable locally with Docker Compose,
and ready to deploy on Google Cloud (not yet deployed). See
[docs/final-build-report.md](docs/final-build-report.md) and
[docs/v1-release-audit.md](docs/v1-release-audit.md).

## Quick start

Prerequisites: Docker with Compose v2. For development and tests you also need
[uv](https://docs.astral.sh/uv/) and Node.js 24.

```bash
cp .env.example .env                                      # development placeholders, mock AI
docker compose up --build -d --wait                       # full stack, health-checked
docker compose exec worker python -m app.cli seed-demo    # optional synthetic demo data
open http://localhost:3000
```

`seed-demo` prints demo sign-ins for each role and a password. Seven demo invoices each
demonstrate different risk signals.

**Use Gemini:** set `AI_PROVIDER=gemini` and `GEMINI_API_KEY=<your key>` in `.env` (never
commit it), then run `docker compose up -d`. Without a key, the deterministic engine runs
and the UI states that AI assistance was unavailable.

## Architecture

A modular monolith with async workers:

- **Web:** Next.js 16, strict TypeScript, Tailwind; same-origin API proxy; nonce CSP.
- **Backend:** FastAPI API and Celery worker from one Python 3.12 codebase.
- **Storage:** PostgreSQL 17, Redis, S3-compatible object storage (MinIO locally, GCS in production).
- **AI:** Gemini behind an `AIProvider` interface.

Details: [docs/architecture.md](docs/architecture.md).

```
apps/web/        Next.js application (pages, components, API proxy, proxy.ts)
apps/backend/    FastAPI + Celery + Alembic (app/modules/* hold the business logic)
docs/            Product, architecture, security, risk engine, AI, API, database, GCP, ADRs
scripts/         smoke-test.sh
.github/         CI: lint, types, tests, build, integration, end-to-end, security scans
```

## Tests and checks

```bash
cd apps/backend
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -m "not integration and not e2e"   # 216 unit tests
uv run pytest -m integration                     # 57 tests (needs postgres, redis, minio)
uv run pytest -m e2e                             # full workflow against the running stack

cd apps/web
npm run lint && npm run format:check && npm run typecheck && npm test && npm run build

set -a && . ./.env && set +a && ./scripts/smoke-test.sh   # 12 stack checks
```

No test calls the real Gemini API. See [docs/testing.md](docs/testing.md).

## Documentation

| Topic | Document |
| --- | --- |
| Product, scope, exclusions, metrics | [docs/product-overview.md](docs/product-overview.md) |
| Architecture and module map | [docs/architecture.md](docs/architecture.md) |
| Local development and every environment variable | [docs/development.md](docs/development.md), [.env.example](.env.example) |
| Security controls, permission matrix, known limitations | [docs/security.md](docs/security.md) |
| Risk rules and deterministic financial logic | [docs/risk-engine.md](docs/risk-engine.md) |
| Gemini usage, prompt-injection defences, failure handling | [docs/ai.md](docs/ai.md) |
| API endpoints and conventions | [docs/api.md](docs/api.md) |
| Database schema and migrations | [docs/database.md](docs/database.md) |
| Testing strategy and coverage | [docs/testing.md](docs/testing.md) |
| Google Cloud deployment | [docs/deployment-gcp.md](docs/deployment-gcp.md) |
| Running a pilot; operating the system | [docs/pilot-guide.md](docs/pilot-guide.md), [docs/operations.md](docs/operations.md) |
| Architecture decisions | [docs/adr/](docs/adr/README.md) |
| Release audit and build report | [docs/v1-release-audit.md](docs/v1-release-audit.md), [docs/final-build-report.md](docs/final-build-report.md) |
