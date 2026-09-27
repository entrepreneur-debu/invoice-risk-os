# Database

PostgreSQL 17, SQLAlchemy 2 (sync, psycopg 3), Alembic migrations. There is no automatic
table creation: the schema exists only through migrations.

## Tables (21)

| Table | Purpose | Tenant-owned |
| --- | --- | :-: |
| `organizations` | Tenants; GSTIN, state, validated `settings` (JSONB), hashed inbound-email token | (tenant) |
| `users` | Global identities; Argon2id password hash, lockout counters | — |
| `memberships` | User ↔ organization with role and status | ✓ |
| `invitations` | Hashed single-use invitation tokens | ✓ |
| `user_sessions` | Server-side sessions (hashed token, expiry, revocation, active organization) | — |
| `vendors` | Vendor master; unique GSTIN per organization (partial index) | ✓ |
| `vendor_bank_accounts` | One row per account version: encrypted number, last 4, fingerprint, IFSC, status, `previous_account_id`, verifier | ✓ |
| `purchase_orders`, `purchase_order_lines` | POs with server-computed amounts; unique number per organization | ✓ |
| `invoices` | Canonical invoice fields, `field_provenance` (JSONB), risk level/score, status, approvals required | ✓ |
| `invoice_lines` | Line items with source | ✓ |
| `invoice_documents` | Stored originals: storage key, SHA-256, type, size, pages | ✓ |
| `invoice_extractions` | Each extraction attempt (document_ai / text_layer / manual) and its validated output | ✓ |
| `invoice_status_changes` | Every status transition with actor and reason | ✓ |
| `risk_assessments` | One per analysis run: engine version, level, score, context snapshot, AI status/output | ✓ |
| `risk_signals` | Explainable signals with evidence (JSONB), source (rule/ai), resolution | ✓ |
| `reviews` | Every reviewer action with reason and evidence snapshot (append-only by design) | ✓ |
| `approval_steps` | Steps per approval cycle, required permission, decider | ✓ |
| `audit_events` | Hash-chained, append-only audit trail (trigger blocks UPDATE/DELETE) | ✓ |
| `notifications` | In-app notifications per recipient | ✓ |
| `inbound_emails` | Received invoice emails (deduplicated on Message-ID) | ✓ |

Conventions:
- UUID primary keys and `timestamptz` timestamps.
- Money is `NUMERIC(18,2)`, quantities `NUMERIC(18,3)`, rates `NUMERIC(7,3)`.
- Enums are stored as `VARCHAR` with CHECK constraints (adding values is a simple migration).
- Constraint names are deterministic (naming convention in `app/db/base.py`).

## Multi-tenancy

Every tenant-owned row carries `organization_id` (indexed, `ON DELETE CASCADE` from the
organization). Services always filter on the caller's organization. See
[security.md](security.md#tenant-isolation) and [ADR 0009](adr/0009-tenant-isolation.md).

## Migrations

```bash
cd apps/backend
uv run alembic upgrade head                            # apply
uv run alembic revision --autogenerate -m "describe"   # after changing models (review the file!)
uv run alembic check                                   # verify models and migrations agree
uv run alembic downgrade -1                            # roll back one revision
```

- `0001_v1_schema.py` creates all tables and the audit append-only trigger. Autogenerate
  can't express triggers, so they are hand-written in migrations.
- In Compose, the one-shot `init` service runs `alembic upgrade head` before the API and
  worker start. On Google Cloud, run it as a Cloud Run job before deploying a new revision
  (see [deployment-gcp.md](deployment-gcp.md)).
- `tests/integration/test_infrastructure.py::test_migrations_upgrade_downgrade_upgrade`
  runs the full cycle on a scratch database, and `alembic check` reports no drift.

## Concurrency

- Audit events: a transaction-scoped advisory lock per organization serializes sequence numbers.
- Risk analysis: a per-organization advisory lock, so concurrent duplicates see each other.
- Review decisions: `SELECT … FOR UPDATE` on the invoice row.
