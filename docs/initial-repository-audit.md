# Initial Repository Audit

Audit performed on 2026-09-27, before any Step 1 changes were made.

## Repository summary

| Item | Finding |
| --- | --- |
| Git state | Branch `main`, clean working tree, up to date with `origin/main` |
| Remote | `origin` → `https://github.com/entrepreneur-debu/invoice-risk-os.git` |
| History | One commit: `20b2589 First Commit` |
| Tracked files | `README.md` (0 bytes, empty) |
| Classification | **Empty repository**: no source code, configuration or tooling |

## Detected technologies

None. There were no package manifests (`package.json`, `pyproject.toml`,
`requirements*.txt`), lockfiles, framework configuration, Dockerfiles, Compose files,
CI workflows, tests, or documentation beyond the empty README.

## Existing structure

```
.
├── .git/
└── README.md   (empty)
```

## Existing useful components

None apart from the Git history and remote. The empty `README.md` was replaced with
project documentation.

## Conflicts or risks

No conflicts with the target architecture, because nothing existed. Risks found
while inspecting the **local environment** (not the repository):

1. **Host port conflicts.** Another local Docker project (`jobagent-postgres`,
   `jobagent-redis`) already publishes ports 5432 and 6379. Every host port in
   `docker-compose.yml` is therefore configurable through `.env`
   (`POSTGRES_PORT`, `REDIS_PORT`, `API_PORT`, `WEB_PORT`, `MINIO_*_PORT`).
2. **MinIO container images.** `minio/minio` no longer exists on Docker Hub, and
   `quay.io/minio/minio` requires authentication. See
   [ADR 0006](decisions/0006-object-storage-minio-image.md).
3. **Toolchain.** The machine has Python 3.12.7 (Anaconda), Node 24.21.0 / npm 11.19.0
   and Docker 29.8.0 with Compose v5.5.1. `uv` and `pnpm` were not installed.
   The project standardises on `uv` for Python (see ADR 0004), which contributors
   must install.

## Recommended changes (applied in Step 1)

- Establish the modular-monolith layout: `apps/web` (Next.js) and `apps/backend`
  (FastAPI API + Celery worker in one codebase), plus `docs/`, `scripts/` and
  `.github/workflows/`.
- Add Docker Compose for PostgreSQL, Redis, MinIO, the API, the worker and the web app.
- Add lint, format, type-check and test tooling for both applications, plus CI.
- Document the architecture, the security baseline and the decisions (ADRs).

## Assumptions

- The repository is new and nothing outside it depends on its current layout.
- The target deployment is not yet chosen; Step 1 optimises for a reproducible local
  stack and CI, not for any specific cloud.
- India-first requirements (data residency, GST, INR formatting) belong to later
  steps. Only the HTML `lang="en-IN"` attribute reflects them now.
