# Admin and Operator Guide

## Roles (who does what)

- **Owner:** organization-level control; manages admins and owners.
- **Admin:** settings, members (reviewer/viewer), bank-account verification, final
  approvals, risk overrides, audit log, email ingestion.
- **Reviewer:** uploads, corrections, vendors, POs, first-step review.
- **Viewer:** read-only.

The full matrix is in [security.md](security.md#authorization-rbac).

## Routine tasks

| Task | How |
| --- | --- |
| Invite a user | Settings → Members and roles → Invite. Copy the one-time link to the user; it expires after 72 h. Email delivery is not in V1. |
| Remove access | Members → Disable. Takes effect on the user's next request. |
| Change approval policy or tolerances | Settings → Approval policy and risk rules. Changes are audited with before and after values. |
| Turn AI off or on | Settings → AI assistance (extraction and explanations separately). |
| Set up email ingestion | Settings → enable email ingestion → create the ingestion token (shown once). Configure your mail provider's inbound webhook to POST raw messages to `/api/v1/email-ingestion/inbound` with header `X-Ingestion-Token`. |
| Verify a bank change | Vendor → Bank accounts → Verify or Reject, with a note on how you confirmed it. Must be a different person from the one who entered it. |
| Check audit integrity | Audit log → Verify integrity |
| Reprocess a failed invoice | Invoice → Try again (after fixing the cause shown) |

## Operations

- **Health:** `GET /health` (liveness) and `GET /ready` (PostgreSQL, Redis and storage;
  503 on failure). Containers have health checks. The worker answers `celery inspect ping`,
  and on Cloud Run the `WORKER_HEALTH_PORT` endpoint.
- **Logs:** JSON on stdout. Useful messages include `invoice processing failed`,
  `ai extraction failed`, `ai risk explanation unavailable`, `risk rule failed`,
  `unhandled exception` (with `request_id`) and `task dispatched`. Every API response
  carries `X-Request-ID`; quote it when investigating.
- **Failures:** invoices never fail silently. They go to `failed` with an error code, and
  the uploader and reviewers are notified. Transient storage or database errors retry up to
  `TASK_MAX_RETRIES` with exponential backoff (maximum 5 minutes).
- **Backups:** Cloud SQL automated backups + PITR, and GCS object versioning (see
  [deployment-gcp.md](deployment-gcp.md)). **Back up `DATA_ENCRYPTION_KEY` separately.**
- **Password reset (V1):** there is no self-service reset. An owner can re-invite the user;
  for the owner account, an operator must reset the hash in the database. Planned for a
  later release.
- **Locked accounts:** unlocked automatically after 15 minutes.
- **Data retention:** `document_retention_days` is recorded per organization, but
  automated purging is **not** implemented in V1.

## Incident checklist (suspected payment fraud)

1. Do not pay. Reject or request changes on the invoice with the reason recorded.
2. Contact the vendor through a known channel (not the invoice or email contact details).
3. Export the audit trail for the invoice and vendor (audit log filter, or API
   `/audit-events?entity_type=invoice&entity_id=…`).
4. If a bank change was involved, reject the pending account (Vendor → Bank accounts).
