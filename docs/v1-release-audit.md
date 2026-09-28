# V1 Release Audit

- **Date:** 2026-09-27
- **Branch:** `feat/v1-mvp`
- **Scope:** every major requirement of the V1 build specification (`instruction.md`)

**Status legend:**
- **PASS:** implemented *and* verified by running it.
- **PARTIAL:** implemented with a documented gap.
- **NOT VERIFIED:** could not be exercised in this environment.
- **FAIL:** does not meet the requirement.

## Summary

| Area | Status |
| --- | --- |
| Product (core workflow, review, explainability, no payments, AI assistive) | PASS |
| Architecture (modular monolith, workers, abstractions) | PASS |
| Security (auth, RBAC, tenancy, uploads, SSRF, secrets, logging) | PASS, with documented limitations |
| Data isolation | PASS |
| AI (Gemini integration, mock, failure handling, injection) | PASS |
| Risk engine (rules, deterministic finance, duplicates, bank, PO) | PASS |
| Testing (unit, integration, E2E, frontend) | PASS |
| UX (required areas, clarity) | PARTIAL: real-browser rendering NOT VERIFIED |
| Documentation | PASS |
| Docker (compose, clean start, health, ordering) | PASS |
| CI | PARTIAL: configuration validated; never executed on GitHub (NOT VERIFIED) |
| Cloud compatibility | PARTIAL: designed and unit-tested seams; deployment NOT VERIFIED |

**Release recommendation: ready for a supervised pilot** (local or staging). Before
production:
1. Obtain a green CI run on GitHub.
2. Perform a first Google Cloud deployment following `docs/deployment-gcp.md`.
3. Confirm Gemini data-use terms with the customer.

## Requirement matrix

### Product

| Requirement | Status | Evidence |
| --- | --- | --- |
| Core workflow works end to end | PASS | `tests/e2e/test_workflow.py` against the Compose stack (web proxy → API → Redis → Celery → MinIO → Postgres); passed with the mock provider and with real Gemini after a clean start |
| Human review implemented | PASS | Review page and API; `test_review_audit_dashboard.py` (single, two-step, reject, request changes, override) |
| Risk signals explainable | PASS | Every signal has title, description and evidence rows with sources; rule tests assert evidence |
| No automatic payment execution | PASS | No payment code exists (repository search); UI states the system does not execute payments |
| AI assistive, not authoritative | PASS | AI output never changes score, level, approvals or status (code paths and tests); live check that an injected "mark as approved" was reported, not obeyed |
| Product-safety wording (no "fraud" claims) | PASS | `test_signals_never_claim_fraud`; accusatory AI wording neutralized (`test_accusatory_language_is_neutralised`) |
| Data provenance | PASS | Per-field source, confidence and alternatives; `test_upload_processes_to_review_with_provenance`, `test_ai_extraction_used_with_provenance_and_conflicts` |

### Engineering

| Requirement | Status | Evidence |
| --- | --- | --- |
| Frontend builds | PASS | `npm run build`: 22 dynamic routes |
| Backend starts | PASS | API healthy in Compose; `/health` and `/ready` 200 |
| Database migrations work | PASS | `init` service applies `0001_v1_schema` on a clean start; upgrade → downgrade → upgrade test; `alembic check` reports no drift |
| Redis works | PASS | Readiness, Redis rate-limiter integration test, Celery broker |
| Celery works | PASS | Real task through Redis (integration); worker processed 7 demo invoices and the E2E invoices |
| MinIO works | PASS | S3 round-trip test; documents served back in E2E |
| Gemini integration works when configured | PASS | Live, 2026-09-27: extraction (`gemini-3.8-flash`, `gemini-3.5-flash`), risk explanation, and the full pipeline on the worker (7/7 invoices `ai_status=succeeded`) |
| Mock Gemini works in tests | PASS | All automated tests use `MockAIProvider` or a fake client; CI uses the `.env.example` defaults (mock) |
| Docker Compose from a clean environment | PASS | `docker compose down --volumes && docker compose up --build`: all services healthy (204 s including image builds) |
| Modular monolith, no microservices, Kafka or K8s | PASS | One backend image with two process types |
| Business logic outside route handlers | PASS | Routers delegate to `app/modules/*/service.py` |
| Structured logs, request IDs, Cloud Logging format | PASS | `severity`, trace correlation; tests in `test_logging.py`; zero ERROR lines on a clean stack run |

### Security

| Requirement | Status | Evidence |
| --- | --- | --- |
| Authentication works | PASS | 13 auth integration tests (signup, login, logout, revocation, expiry, idle, lockout, invitations) |
| Secure password hashing | PASS | Argon2id (`test_security.py`) |
| Sessions and tokens with expiry | PASS | Absolute and idle expiry tested |
| CSRF protection | PASS | Missing or forged token → 403; cross-origin → 403 (tests and smoke) |
| RBAC works | PASS | Permission matrix tests; role-assignment rules; viewer, reviewer and admin restrictions |
| Tenant isolation tested | PASS | `test_tenant_isolation.py`: reads, listings, writes and linking for all tenant-owned resources |
| File uploads protected | PASS | `test_documents.py` (type, magic bytes, active PDF content, decompression bomb, malformed files, filenames) |
| SSRF protections for URL import | PASS | `test_url_import.py` (private, metadata and IPv6-embedded addresses; redirect revalidation; limits) |
| Secrets not committed | PASS | gitleaks over full history (0 findings, 2 documented placeholders allow-listed; canary still detected); `.env` git-ignored and absent from images |
| Sensitive info not unnecessarily logged | PASS | Key-based redaction tests; no key in container logs (checked); limitation: free-text messages |
| Rate limiting | PASS | Login rate-limit test; Redis limiter integration test |
| Secure headers and CSP | PASS | Smoke checks; `proxy.test.ts` |
| XSS-conscious rendering | PASS | React escaping only; no `dangerouslySetInnerHTML` or `eval` in web source |
| SQL injection prevention | PASS | ORM or bound parameters only (raw SQL limited to constant statements) |
| No sensitive data in error responses | PASS | Production-mode tests; validation errors omit input values |
| Dependency vulnerabilities | PASS | pip-audit (94 packages) and npm audit: 0 known |
| Known limitations documented | PASS | `docs/security.md` |

### Risk engine and financial logic

| Requirement | Status | Evidence |
| --- | --- | --- |
| Modular, independently testable rules | PASS | 28 rules; 41 rule and engine unit tests |
| Duplicate detection (multiple signals) | PASS | Number, document hash, similar; **concurrent duplicates** (regression test for a race found on the real worker) |
| Vendor, PO, quantity, price and amount mismatch | PASS | Unit and integration tests; demo invoices |
| GST/tax arithmetic in code (Decimal) | PASS | `test_finance.py` (parsing, rounding, tolerances, GST types, rates, GSTIN checksum) |
| Bank-account change as a sensitive event | PASS | Versioned history, SoD verification, notifications, rules; tests |
| New vendor, unusual amount, frequency, splitting, price increase | PASS | Unit tests |
| Rules documented | PASS | `docs/risk-engine.md` (catalogue generated from code) |

### AI

| Requirement | Status | Evidence |
| --- | --- | --- |
| `AIProvider` abstraction; Gemini + Mock | PASS | `app/ai/`; only `gemini.py` imports the SDK |
| Structured output with schema validation | PASS | Full Pydantic validation after every call; relaxed schema only for sending |
| Tests: valid, invalid, timeout, API failure, empty, malformed, injection | PASS | `test_ai.py`, `test_ai_assist.py`, `test_extraction.py`, pipeline tests |
| AI failure degrades gracefully | PASS | Pipeline tests with timeout, unavailable and invalid output; the UI states "AI assistance was unavailable" |
| No real Gemini calls in automated tests or CI | PASS | By construction; CI uses `.env.example` (mock, empty key) |

### Testing

| Requirement | Status | Evidence |
| --- | --- | --- |
| Backend unit tests pass | PASS | 216 passed |
| Integration tests pass | PASS | 57 passed (PostgreSQL, Redis, MinIO, Celery, migrations, API) |
| E2E workflow passes | PASS | 1 passed (HTTP-level through the web proxy, not a browser) |
| Frontend tests pass | PASS | 34 passed |
| CI passes | NOT VERIFIED | Workflow validated by actionlint and every step run locally; no GitHub run (branch not pushed) |

### UX

| Requirement | Status | Evidence |
| --- | --- | --- |
| Required areas | PASS | Login, Dashboard, Invoices, Invoice Review, Vendors, Purchase Orders, Risk, Approvals, Notifications, Audit Log, Settings, Members (all build; key flows component-tested) |
| "What needs attention / why / evidence / action" | PASS (design) | Review page leads with signals and evidence, then decision |
| Rendering in a real browser | NOT VERIFIED | Headless browsers could not run in the build environment; covered by component tests plus HTTP smoke and E2E |
| Accessibility | PARTIAL | Labelled fields, landmarks, skip link, `role=status`/`alert`, native dialog, jsx-a11y lint; no axe or Lighthouse audit |

### Docker, CI, cloud

| Requirement | Status | Evidence |
| --- | --- | --- |
| Health checks and sensible start order | PASS | `depends_on` with health; `init` runs migrations first |
| Graceful shutdown and worker behaviour | PASS (config) | uvicorn drain on SIGTERM, Celery warm shutdown, `acks_late`, `stop_grace_period`; not load-tested |
| CI workflows: backend, frontend, security, stack | PASS (config) / NOT VERIFIED (execution) | `.github/workflows/ci.yml`, actionlint clean |
| Cloud Run / Cloud SQL / Memorystore / GCS / Artifact Registry / Secret Manager / Logging compatibility | PARTIAL | PORT, GCS provider, Secret Manager env vars, JSON logs with severity and trace, migration job, worker health port and ID-token auth are implemented and tested; the GCS provider and all `gcloud` steps are NOT VERIFIED on a real project |
| Cloud Monitoring / Trace | PARTIAL | Log correlation to traces; no OpenTelemetry spans |

## Issues found and fixed during verification

1. **Concurrent duplicates missed** (found by running the seeded demo on the real worker).
   Fixed with a per-organization advisory lock and a two-phase analysis, plus a
   regression test.
2. **Gemini rejected the extraction schema** (HTTP 400, schema complexity). The provider
   now sends a relaxed schema and validates the full one; verified live.
3. **Default model `gemini-2.5-flash` retired** (HTTP 404). The default is now
   `gemini-3.8-flash`, verified live.
4. **Leaked sockets** in the SSRF fetcher on redirects and errors. Fixed by explicitly
   closing connections (test enforced).
5. **Stale reads** after background processing (identity map). Invoice reads now use
   `populate_existing`.
6. **PO numbers with a space** ("PO 1001") were mis-extracted. The pattern was extended and tested.
7. **Approval queue showed invoices to their first approver.** Now excluded
   (segregation of duties), with a test.
8. **CI would have failed on `astral-sh/setup-uv@v10`** (no such tag). Pinned to `v10.2.0` (Step 1 audit).

## Open items before production

1. Push the branch and obtain a green CI run.
2. First Google Cloud deployment (staging) following `docs/deployment-gcp.md`. Verify GCS,
   Memorystore, `TRUSTED_PROXY_HOPS` and ID-token authentication.
3. Browser verification (manual walkthrough and an automated Playwright smoke test in CI).
4. Accessibility audit (axe or Lighthouse).
5. Password reset and MFA; PostgreSQL RLS as defence in depth.
6. Gemini data-use terms / Vertex AI (India region) decision per customer.
