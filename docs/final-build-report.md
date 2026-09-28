# Final Build Report: Invoice Risk & Payment Control OS V1

- **Date:** 2026-09-28
- **Branch:** `feat/v1-mvp`
- **Companion:** [v1-release-audit.md](v1-release-audit.md), which gives the status of every requirement

## 1. What was implemented

A complete, locally runnable, tested MVP of an India-first invoice-risk and payment-control SaaS:

- **Multi-tenant SaaS core:**
  - signup/login/logout with server-side sessions, CSRF and rate limiting
  - organizations, invitations, and roles (owner, admin, reviewer, viewer) enforced on the server
- **Vendors:**
  - GSTIN/PAN validation
  - encrypted bank accounts with full history
  - independent verification (segregation of duties) and audited reveal
- **Purchase orders:** server-computed totals and invoiced-to-date tracking.
- **Ingestion:**
  - upload (PDF/PNG/JPEG, strict validation)
  - SSRF-safe URL import
  - email ingestion (token-authenticated inbound endpoint + CLI)
- **Extraction:** Gemini document extraction and text-layer heuristics, merged with
  per-field provenance. Unknown values stay unknown.
- **Deterministic risk engine:** 28 explainable rules covering duplicates, vendor identity,
  bank accounts, PO three-way checks, GST arithmetic, data quality, behavioural anomalies,
  invoice splitting and prompt injection.
- **Gemini risk assistance:** schema-validated and advisory only.
- **Human review:**
  - evidence-first review page
  - approve / reject / request changes / comment, all with a reason
  - second approver for high value or high risk
  - authorised overrides for high signals
- **Tamper-evident audit trail**, in-app notifications, dashboard and analytics (real data only).
- **Docker Compose stack**, CI (backend, frontend, security, stack), Google Cloud deployment
  guide, pilot and operator guides, and 12 ADRs.

## 2. Architecture summary

A modular monolith with async workers:
- **Web:** Next.js 16. The browser talks only to it: pages plus a same-origin `/api/v1` proxy.
- **Backend:** FastAPI (API) and Celery (worker) from one Python codebase.
- **Data and AI:** PostgreSQL, Redis, S3-compatible storage (MinIO or GCS), and Gemini
  behind `AIProvider`.

See [architecture.md](architecture.md).

## 3. Database summary

- 21 tables in one Alembic migration.
- Every tenant-owned row carries `organization_id`.
- Money uses `NUMERIC(18,2)`.
- The audit table is append-only (database trigger) and hash-chained.
- Bank numbers are AES-GCM encrypted with a keyed fingerprint.

See [database.md](database.md).

## 4. API summary

- 51 operations under `/api/v1`, plus `/health` and `/ready`.
- Pydantic contracts, one error envelope with request IDs, pagination, and cookie auth
  with CSRF.

See [api.md](api.md) (generated from OpenAPI).

## 5. Frontend summary

- 21 pages: login, signup, invite, dashboard, invoices (list, add, review), approvals,
  vendors (list, new, detail), purchase orders (list, new, detail), risk, notifications,
  audit, settings, and members.
- Reusable UI component set, strict TypeScript, and a nonce-based CSP via `proxy.ts`.
- The review page shows signals with evidence, AI assistance (clearly labelled), the
  original document, provenance, the approval workflow and audit history.

## 6. Risk-engine summary

- Pure rules over immutable facts, with `Decimal` arithmetic.
- Deterministic scoring (HIGH 40, MEDIUM 15, LOW 5).
- Per-organization serialized analysis, so concurrent duplicates are detected.
- A rule that errors is surfaced as a signal, never silently skipped.

See [risk-engine.md](risk-engine.md).

## 7. Gemini integration summary

- `GeminiProvider` (google-genai, JSON output, temperature 0, full schema validation) and
  `MockAIProvider` for all tests.
- **Verified live on 2026-09-27 with the owner's key:**
  - extraction was exact and agreed with the text layer
  - an injected instruction was reported, not obeyed
  - the risk explanation was correct
  - the worker pipeline succeeded on 7 of 7 demo invoices
  - the E2E test passed on a Gemini-configured stack
- **Defaults:** `gemini-3.8-flash` (`gemini-2.5-flash` is retired). AI can be switched
  off per organization.

See [ai.md](ai.md).

## 8. Security summary

- Argon2id passwords; HttpOnly sessions with CSRF plus Origin checks; lockout and rate limits.
- RBAC with segregation of duties; tenant isolation tested for every resource type.
- Upload validation; SSRF protection; encrypted bank data; secrets only from the environment.
- Production-safety validation at startup; strict headers and CSP; redacted JSON logs.
- CI runs gitleaks, pip-audit and npm audit, all clean.

See [security.md](security.md) for the permission matrix and limitations.

## 9. Testing summary

| Suite | Result |
| --- | --- |
| Backend unit | **216 passed** |
| Backend integration (real PostgreSQL, Redis, MinIO, Celery; migrations; API) | **57 passed** |
| End-to-end workflow (Compose stack through the web proxy) | **1 passed** (mock AI, and again with real Gemini after a clean start) |
| Frontend (Vitest + Testing Library) | **34 passed** |
| Smoke checks (running stack) | **12/12 passed** |
| Lint / format / strict types | Ruff, mypy `--strict` (135 files); ESLint (0 warnings), Prettier, `tsc` strict: all clean |

## 10. Docker summary

- **Services:** postgres, redis, minio, init (migrations and bucket), api, worker and web.
  All are health-checked, with ordered startup and non-root processes.
- **Ports:** bound to localhost.
- **Clean start** (`down --volumes && up --build`) verified on the final code: all healthy,
  zero ERROR log lines.
- **Images:** Cloud Run-ready (`PORT`, graceful shutdown).

## 11. CI summary

`.github/workflows/ci.yml` has four jobs:
- **backend:** lint, format, types, unit tests, no-dev import check
- **frontend:** lint, format, types, tests, build
- **security:** gitleaks over full history, pip-audit, npm audit
- **stack:** compose build and start, smoke, integration, end-to-end

actionlint reports no errors, and every step was run locally. **The workflow has never
executed on GitHub** (NOT VERIFIED). No Gemini key is needed.

## 12. Google Cloud readiness summary

- **Target:** Cloud Run for web, API (internal + IAM) and worker; Cloud SQL, Memorystore,
  GCS, Artifact Registry and Secret Manager; Cloud Logging and Trace correlation.
- **Implemented seams:**
  - GCS storage backend
  - `PORT` and graceful shutdown
  - separate migration job
  - worker health port
  - ID-token service authentication from web to API
  - JSON logs with severity and trace
- Step-by-step commands are in [deployment-gcp.md](deployment-gcp.md).
- **No resources were provisioned; the deployment is NOT VERIFIED.**

## 13. Known limitations

- **Not verified in this environment:**
  - rendering in a real browser (component, HTTP smoke and E2E tests only)
  - any GitHub CI run
  - any Google Cloud deployment, including the GCS provider against real GCS
- **Missing features:**
  - no MFA, SSO or self-service password reset
  - email and Slack notification delivery not implemented (in-app only)
  - no ERP or accounting integration, no GST-portal lookup, no multi-currency conversion
  - scanned-image invoices depend on Gemini, or manual entry
  - retention setting recorded but no automated purge; no customer data export
- **Security depth:**
  - tenant isolation is application-level (no PostgreSQL RLS yet)
  - audit chain is tamper-evident, not tamper-proof (no external anchoring)
  - rate limiting fails open without Redis
  - no malware scanning of uploads
- **Infrastructure:**
  - no OpenTelemetry spans
  - Memorystore TLS path not implemented
  - MinIO (local only) comes from a third-party image build
- **AI data handling:** invoice documents are sent to the Gemini API when enabled. Confirm
  terms with customers, or disable per organization.

## 14. Technical debt

- `approval_steps` and `reviews` both carry decision data. Consolidate if workflows become
  configurable.
- The frontend data hooks are hand-written (no cache library). Revisit if pages multiply.
- Heuristic text extraction is regex-based. Add layout-aware parsing if pilots rely on
  text-only extraction.
- Risk re-analysis after a manual correction resets earlier signal resolutions (by design
  for V1; could carry them forward).
- The `DATA_ENCRYPTION_KEY` rotation tool is missing.
- The worker health check spawns a Celery client every 30 s (Compose). Use a lighter probe at scale.
- No Terraform/IaC or CD pipeline yet.

## 15. Items intentionally excluded from V1

Payment execution and bank integrations; autonomous approval or rejection;
ERP/accounting integrations; billing and subscriptions; direct mailbox connectors
(Gmail/Microsoft 365); Slack; data warehousing; microservices, Kafka and Kubernetes. See
[product-overview.md](product-overview.md#v1-exclusions-deliberate).

## 16. Phase status

| Phase | Status | Notes |
| --- | --- | --- |
| 0 Product foundation | PASS | [product-overview.md](product-overview.md) |
| 1 Engineering foundation | PASS | Step 1 audit + V1 re-verification |
| 2 SaaS core (auth, orgs, RBAC, tenancy) | PASS | 13 auth + 6 isolation + RBAC tests |
| 3 Vendors | PASS | Bank-change control verified |
| 4 Invoice ingestion and extraction | PASS | Upload, URL, email; Gemini verified live |
| 5 Purchase orders | PASS | Deterministic matching |
| 6 Risk engine | PASS | 28 rules; concurrency fix |
| 7 Human review and approval | PASS | Two-step, SoD, overrides |
| 8 Notifications | PASS (in-app) | External channels NOT implemented (by design) |
| 9 Email ingestion | PASS | Webhook-style endpoint + CLI; provider abstraction |
| 10 Dashboard and analytics | PASS | Real-data metrics only |
| 11 Audit and compliance | PASS | Hash chain + DB trigger; retention purge not implemented |
| 12 Security hardening | PASS | Tests + scans; documented limitations |
| 13 Production architecture readiness | PARTIAL | Code-ready; GCP NOT VERIFIED |
| 14 Production testing | PASS | Except the CI run and browser checks (NOT VERIFIED) |
| 15 Pilot readiness | PASS | Demo seeding, pilot and operator guides, measurement framework |
| 16 V1 release candidate | PASS | [v1-release-audit.md](v1-release-audit.md) |
