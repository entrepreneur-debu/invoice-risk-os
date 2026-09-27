# 0003 - Synchronous SQLAlchemy 2 with psycopg 3

- Status: Accepted
- Date: 2026-09-27

## Context

FastAPI supports both sync and async database access. Celery tasks are synchronous.
Financial workflows need correct, easy-to-follow transaction handling more than
high-concurrency I/O.

## Decision

Use **SQLAlchemy 2.x in synchronous mode** with the **psycopg 3** driver. FastAPI runs
sync endpoints and dependencies in its threadpool. Sessions are request-scoped via
`get_db_session`. Alembic manages schema migrations, and no migration exists until the
first domain table does.

## Consequences

- API and worker share the same session and repository code.
- Transaction boundaries are explicit and debuggable. There are no async pitfalls
  (implicit lazy loads or event-loop blocking) in financial logic.
- Concurrency per API process is bounded by the threadpool and connection pool
  (`DATABASE_POOL_SIZE` + `DATABASE_MAX_OVERFLOW`). Scale by adding processes.
- If a genuinely high-fanout I/O path appears, add async for that path without
  converting everything.
