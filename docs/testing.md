# Testing

| Suite | Command | Needs | Count |
| --- | --- | --- | --- |
| Backend unit | `cd apps/backend && uv run pytest -m "not integration and not e2e"` | nothing | 216 |
| Backend integration | `uv run pytest -m integration` | `docker compose up -d --wait postgres redis minio` | 57 |
| End-to-end workflow | `uv run pytest -m e2e` | full stack (`docker compose up -d --wait`) | 1 |
| Frontend | `cd apps/web && npm test` | nothing | 34 |
| Smoke | `set -a && . ./.env && set +a && ./scripts/smoke-test.sh` | full stack | 12 checks |

No test calls the real Gemini API. Every AI interaction uses `MockAIProvider` or a fake
Gemini client, so CI needs no key. Warnings are errors (`filterwarnings = error`), and unit
tests are isolated from the developer's environment variables.

## What is covered

- **Risk rules and financial logic:** every rule is tested against a clean baseline with a
  single perturbation. Also covered: scoring, rule-failure isolation, no "fraud" wording,
  Decimal parsing and rounding, GSTIN checksums, GST arithmetic and tolerances.
- **Duplicates:** number normalization, document hash, similar invoices, and
  **concurrent duplicate processing** (a regression test for a race found on the real worker).
- **PO matching:** quantities including earlier invoices, prices with tolerance, unordered
  items, fuzzy line matching, amount exceeded.
- **Vendors:** GSTIN/PAN validation, bank-change history, verification by a different
  person, rejection restoring the previous account, audited reveal, encryption at rest.
- **Authentication:**
  - signup and login
  - generic errors and lockout
  - rate limiting
  - CSRF and Origin checks
  - session revocation, expiry and idle timeout
  - invitations (single use) and organization switching
- **Permissions:** the role matrix, role-assignment rules, disabled members, and
  viewer/reviewer/admin restrictions on every sensitive action.
- **Tenant isolation:** reads, listings, writes and cross-tenant linking for vendors, bank
  accounts, POs, invoices, documents, reviews, signals, audit, notifications and members.
- **Pipeline:** upload through to review with provenance, AI extraction merge and
  conflicts, AI failure modes (timeout, unavailable, invalid), organization-disabled AI,
  prompt injection, storage outage, processing failure and reprocessing, manual correction
  with re-analysis, email ingestion.
- **Review workflow:** single approval, high-signal blocking and override, two-step
  approval with segregation of duties, reject, request changes and resubmission, the
  approval queue.
- **Audit:** reconstruction of decisions, chain verification, database-level
  immutability, tamper detection.
- **Security inputs:**
  - SSRF: private, metadata and IPv6-embedded addresses; redirect revalidation; size and
    redirect limits; schemes, ports and credentials
  - file validation: magic bytes, extension, active PDF content, decompression bombs,
    malformed files, filename sanitization
- **Infrastructure:** PostgreSQL, Redis rate limiter, MinIO round trip, a real Celery task
  through Redis, and migrations (upgrade → downgrade → upgrade).
- **Frontend:**
  - login/signup forms and errors, and open-redirect prevention
  - review screen: risk display, AI labelling and unavailability, approval blocking,
    reason-required decisions, provenance display
  - API client (CSRF header, error envelope)
  - the API proxy (header allow-lists, traversal, safe 502)
  - CSP and auth redirect in `proxy.ts`
- **End-to-end (real stack):**
  1. Organization signup and invitations through the web proxy.
  2. Vendor creation and verification by a different person.
  3. Upload of two invoices processed by the Celery worker through MinIO.
  4. Bank-mismatch detection, blocked approval, reject and approve.
  5. Audit trail and hash-chain verification, and dashboard counts.

## Manual verification performed (not automated)

- A real Gemini API call (extraction and explanation, including an injected instruction)
  with the owner's key. See [ai.md](ai.md).
- The seeded demo processed by the real worker with Gemini: all 7 invoices reached review
  with the expected rules.
- A clean start from empty volumes (`docker compose down --volumes && docker compose up --build`).

Not verified: rendering in a real browser (a headless browser could not run in the build
environment; UI behaviour is covered by component tests and the HTTP-level smoke and E2E tests).
