# 0002 - Repository layout: one backend codebase for API and worker

- Status: Accepted
- Date: 2026-09-27

## Context

The initial brief suggested `apps/web`, `apps/api`, `apps/worker`, `packages/shared`,
`infrastructure/docker` and a top-level `tests/`. Under ADR 0001 the API and the
worker run the *same* domain code: a worker task that processes an invoice uses the
same models, settings and services as the API.

## Decision

```
apps/web/        Next.js frontend (own package.json, tests, Dockerfile)
apps/backend/    Python: FastAPI API + Celery worker + Alembic migrations
  app/api/       HTTP layer (the API process)
  app/worker/    Celery app and tasks (the worker process)
docs/            Architecture, security baseline, ADRs
scripts/         Operational scripts (end-to-end smoke test)
.github/         CI
docker-compose.yml   Local orchestration (repo root, so `docker compose up` works there)
```

- **No separate `apps/worker`.** A second Python project would have to import the
  first (or duplicate it). The worker is a second entrypoint (`app/worker/main.py`)
  in the same package and image.
- **No `packages/shared` yet.** The only shared contract between TypeScript and Python
  is the tiny `/health` response. Add the package when there is real schema to share,
  for example TypeScript types generated from the API's OpenAPI document.
- **No `infrastructure/docker`.** Each Dockerfile sits next to the code it builds.
  The Compose file sits at the root. Nothing else is infrastructure yet.
- **Tests live with each app** (`apps/backend/tests`, `apps/web/src/**/*.test.tsx`).
  Cross-stack verification is `scripts/smoke-test.sh`.

## Consequences

- Folders exist only where they hold something. Add new top-level folders when their
  content arrives.
- Domain modules go under `apps/backend/app/<module>/` (see `docs/architecture.md`).
