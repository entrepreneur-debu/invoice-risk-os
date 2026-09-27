# 0004 - Dependency management and code-quality tooling

- Status: Accepted
- Date: 2026-09-27

## Decision

**Python (`apps/backend`)**

| Concern | Tool | Why |
| --- | --- | --- |
| Dependencies and lockfile | uv (`pyproject.toml` + `uv.lock`) | Fast, reproducible installs with a cross-platform lockfile. The same tool runs locally, in CI and in Docker. |
| Lint and format | Ruff | One fast tool for linting (including bandit security rules) and formatting |
| Types | mypy `--strict` with the pydantic plugin | Catches contract errors in settings and models |
| Tests | pytest (`integration` marker for real services) | Standard. The marker keeps unit tests hermetic. |
| HTTP test client | httpx2 | Required by the current Starlette `TestClient` |
| Type stubs | boto3-stubs[s3], celery-types | Needed for strict mypy. Dev-only, never imported at runtime. |

**TypeScript (`apps/web`)**

| Concern | Tool | Why |
| --- | --- | --- |
| Package manager | npm (`package-lock.json`) | Ships with Node, so there is nothing extra to install |
| Lint | ESLint 9 + `eslint-config-next` (core-web-vitals, TypeScript) | Official Next.js rules, including accessibility (jsx-a11y) |
| Format | Prettier | Standard formatter |
| Types | TypeScript `strict` + `noUncheckedIndexedAccess` | Strictness |
| Tests | Vitest + React Testing Library + jsdom | Documented Next.js unit-testing setup. Fast, native ESM and TypeScript. |

**Runtimes:** Python 3.12, Node 24 LTS. Container base images are pinned by digest.

## Consequences

- Contributors must install `uv` (see README).
- `uv.lock` and `package-lock.json` are committed. CI installs with `--frozen` / `npm ci`.
- Warnings fail the pytest run (`filterwarnings = error`). Known upstream warnings are
  ignored one by one, with a comment (see `pyproject.toml`).
