# Development

## Prerequisites

Docker (with Compose v2), [uv](https://docs.astral.sh/uv/) 0.12+ and Node.js 24. Only
Docker is needed to run the product. uv and Node are needed to develop and test.

## Run everything

```bash
cp .env.example .env                 # development placeholders; mock AI by default
docker compose up --build -d --wait  # postgres, redis, minio, init (migrations), api, worker, web
docker compose exec worker python -m app.cli seed-demo   # optional synthetic demo data
open http://localhost:3000
```

`seed-demo` prints the demo sign-ins (owner, admin, reviewer, viewer) and a generated
password. Set `DEMO_PASSWORD` to choose it. It refuses to run in production.

To use Gemini, set `AI_PROVIDER=gemini` and `GEMINI_API_KEY=…` in `.env`, then run
`docker compose up -d`.

| Service | URL |
| --- | --- |
| Web app | http://localhost:3000 |
| API / docs | http://localhost:8000 · http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |
| PostgreSQL / Redis | localhost:5432 / localhost:6379 (bound to 127.0.0.1) |

Change the `*_PORT` variables in `.env` if those ports are taken (and the matching
`localhost` URLs for host-run processes).

## Hot reload (apps on the host, infrastructure in Docker)

```bash
docker compose up -d --wait postgres redis minio
cd apps/backend && uv sync && uv run alembic upgrade head && uv run python -m app.cli ensure-bucket
uv run uvicorn app.main:create_app --factory --reload --port 8000
uv run celery -A app.worker.main worker --loglevel=INFO          # second terminal
cd apps/web && npm install && API_INTERNAL_URL=http://localhost:8000 npm run dev
```

## Useful commands

```bash
docker compose logs -f api worker                 # structured JSON logs
docker compose down                               # stop (keep data)
docker compose down --volumes                     # full reset
docker compose exec worker python -m app.cli ingest-email path/to/invoice.eml --token <token>
```

## Environment variables

Every variable is documented inline in [`.env.example`](../.env.example), grouped as:
application, authentication, data protection, HTTP, URL import, PostgreSQL,
Redis/Celery, object storage, AI (Gemini), email ingestion, Google Cloud, and ports.
Production differs only in values (from Secret Manager). There is no separate code path.

## Conventions

- Python 3.12, Ruff (lint + format, line length 100), mypy `--strict`, pytest.
- TypeScript strict (`noUncheckedIndexedAccess`), ESLint (Next.js core-web-vitals +
  TypeScript), Prettier, Vitest + Testing Library.
- Business logic lives in `app/modules/*/service.py` and pure functions, not in routers.
- New tenant-owned tables need `organization_id`, service-level filtering and a
  cross-tenant test.
- Commit messages follow Conventional Commits (`feat(risk): …`, `fix(auth): …`).
