# Invoice Risk & Payment Control OS

> Every invoice gets checked before a business pays it.

An India-first B2B financial-control SaaS. It will ingest vendor invoices, extract
structured data, compare invoices against vendors and purchase orders, detect
anomalies with explainable risk signals, route invoices for human review and approval,
and keep a strong audit trail.

## Current stage: Step 1, engineering foundation

This repository contains **only the engineering foundation**: application skeletons,
local infrastructure, configuration, tests, CI and documentation. Invoice processing,
OCR, AI analysis, risk scoring, vendors, purchase orders, approvals, payments,
authentication and every other business feature arrive in later steps.

## Architecture

A modular monolith with asynchronous workers:

| Component | Tech | Location |
| --- | --- | --- |
| Web app | Next.js 16, React 19, TypeScript (strict), Tailwind CSS 4 | `apps/web` |
| API | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2 | `apps/backend/app` |
| Worker | Celery 5 (same codebase and image as the API) | `apps/backend/app/worker` |
| Migrations | Alembic | `apps/backend/migrations` |
| Database | PostgreSQL 17 | Docker Compose |
| Broker/cache | Redis 7.4 | Docker Compose |
| Object storage | MinIO (S3 API) | Docker Compose |

See [docs/architecture.md](docs/architecture.md) for the design and diagram, and
[docs/decisions/](docs/decisions/README.md) for the ADRs.

```
apps/web/            Next.js frontend
apps/backend/        FastAPI API + Celery worker + Alembic
docs/                Architecture, security baseline, ADRs, repository audit
scripts/             smoke-test.sh (end-to-end stack verification)
.github/workflows/   CI
docker-compose.yml   Local stack
.env.example         Every environment variable, documented
```

## Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| Docker with Compose v2 | Docker 24+ | Running the stack |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.12+ | Backend development and tests (uv provisions Python 3.12 if missing) |
| Node.js | 24 LTS (npm 11) | Frontend development and tests |

Only Docker is required to *run* the stack. uv and Node are needed to develop and to
run checks outside containers.

## Environment setup

```bash
cp .env.example .env
```

`.env.example` documents every variable. Its values are development placeholders, so
the stack runs without edits. `.env` is git-ignored. Never commit it.

Key variables:

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `development`, `test` or `production`. Production enforces a strong secret, no wildcard CORS, no diagnostics, and no `/docs`. |
| `APP_SECRET_KEY` | Application secret. Placeholder locally. Production requires 32+ random characters. |
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://...`) |
| `REDIS_URL` | Redis URL. Celery's broker and result backend default to it. |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` | Object storage |
| `CORS_ALLOWED_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `MAX_REQUEST_BODY_BYTES` | Request body limit (default 1 MiB) |
| `ENABLE_DIAGNOSTICS_ENDPOINTS` | Enables `POST /api/v1/diagnostics/worker-ping` (development only) |
| `AI_PROVIDER` | `mock` (default, no network) or `gemini`. `anthropic` is reserved. |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini credentials and model, used only when `AI_PROVIDER=gemini`. Set the key in `.env` only. |
| `API_INTERNAL_URL` | How the Next.js server reaches the API (server-side only) |
| `*_PORT` | Host ports. Change them if something else already uses 5432/6379/3000/8000/9000. |

Inside Docker Compose the service hostnames (`postgres`, `redis`, `minio`, `api`)
replace the `localhost` URLs automatically. The `localhost` values in `.env` are for
running the backend directly on your machine.

## Run the stack with Docker Compose

```bash
cp .env.example .env              # first time only
docker compose up --build         # add -d --wait to run detached until all services are healthy
```

Then verify it end to end:

```bash
set -a && . ./.env && set +a && ./scripts/smoke-test.sh
```

The smoke test checks `/health`, `/ready`, a Celery round trip (API → Redis → worker),
the error envelope, the body-size limit, the web page, and web → API connectivity.

### Local services

| Service | URL | Notes |
| --- | --- | --- |
| Web app | http://localhost:3000 | Shows live API connectivity |
| API | http://localhost:8000 | |
| API liveness | http://localhost:8000/health | |
| API readiness | http://localhost:8000/ready | 503 if PostgreSQL, Redis or storage is down |
| API docs | http://localhost:8000/docs | Disabled when `APP_ENV=production` |
| Celery round trip | `curl -X POST http://localhost:8000/api/v1/diagnostics/worker-ping` | Diagnostics must be enabled |
| MinIO API / console | http://localhost:9000 / http://localhost:9001 | Log in with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| PostgreSQL | `localhost:5432` | `docker compose exec postgres psql -U invoice_risk invoice_risk` |
| Redis | `localhost:6379` | `docker compose exec redis redis-cli` |

All ports bind to `127.0.0.1` only.

### Stop and reset

```bash
docker compose stop               # stop, keep containers and data
docker compose down               # remove containers, keep data volumes
docker compose down --volumes     # full reset: also deletes PostgreSQL, Redis and MinIO data
docker compose logs -f api worker # follow logs
```

### Troubleshooting

- **`port is already allocated`**: another process uses that host port. Change the
  matching `*_PORT` in `.env` (and the port in `DATABASE_URL` / `REDIS_URL` /
  `S3_ENDPOINT_URL` if you run the backend on the host).
- **`init` exited non-zero**: run `docker compose logs init`. It runs migrations and
  bucket creation.

## Development without Docker (hot reload)

Start only the infrastructure in Docker, then run the apps on the host:

```bash
docker compose up -d --wait postgres redis minio

# Backend (reads the repository-root .env)
cd apps/backend
uv sync
uv run alembic upgrade head
uv run python -m app.cli ensure-bucket
uv run uvicorn app.main:create_app --factory --reload --port 8000
uv run celery -A app.worker.main worker --loglevel=INFO     # second terminal

# Frontend
cd apps/web
npm install
API_INTERNAL_URL=http://localhost:8000 npm run dev
```

## Tests, linting and type checks

Backend (`apps/backend`):

```bash
uv run ruff check .                     # lint (includes security rules)
uv run ruff format --check .            # format check (use `ruff format .` to fix)
uv run mypy                             # strict type checking
uv run pytest -m "not integration"      # unit tests: no services needed
uv run pytest -m integration            # needs postgres, redis and minio running (see above)
uv run pytest                           # everything
```

Frontend (`apps/web`):

```bash
npm run lint           # ESLint (zero warnings allowed)
npm run format:check   # Prettier (use `npm run format` to fix)
npm run typecheck      # tsc --noEmit (strict)
npm test               # Vitest + React Testing Library
npm run build          # production build
```

### Using Gemini

Put your key in the repository-root `.env` (never in `.env.example`):

```
AI_PROVIDER=gemini
GEMINI_API_KEY=<your key>
```

Then restart: `docker compose up -d` (or restart the host-run API/worker). No feature
calls the provider yet. It becomes available to code through `create_ai_provider(settings)`.

Automated tests never call real AI APIs. `MockAIProvider` is used instead (see
[ADR 0007](docs/decisions/0007-ai-provider-abstraction.md)).

## CI

`.github/workflows/ci.yml` runs on every push to `main` and every pull request:

1. **Backend:** `uv sync --frozen`, Ruff lint and format check, mypy, unit tests, and a
   runtime import check without dev dependencies.
2. **Frontend:** `npm ci`, ESLint, Prettier check, `tsc`, Vitest, `next build`.
3. **Docker stack** (after 1 and 2 pass): builds every image, starts the full Compose
   stack, runs `scripts/smoke-test.sh` and the backend integration tests, and prints
   logs on failure.

Any failing step fails the workflow.

## Documentation

- [Architecture](docs/architecture.md)
- [Security baseline](docs/security-baseline.md)
- [Architecture decision records](docs/decisions/README.md)
- [Initial repository audit](docs/initial-repository-audit.md)
