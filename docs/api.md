# API

- **Base path:** `/api/v1` (versioned). `/health` and `/ready` are unversioned for load balancers.
- **Interactive docs:** `/docs` and `/openapi.json` are available outside production.
- **Browser access:** through the web app's same-origin proxy (`http://localhost:3000/api/v1/...`).
  Direct access is `http://localhost:8000/api/v1/...`.

## Conventions

- **Authentication:** session cookie `irs_session` (HttpOnly). State-changing requests also
  need `X-CSRF-Token` (the value of the `irs_csrf` cookie, also returned by `/auth/me`)
  and a same-site `Origin`.
- **Inbound email** uses `X-Ingestion-Token` instead.
- **Tenancy:** every call acts in the session's active organization. Resources in other
  organizations return `404`.
- **Errors:** always `{"error": {"code", "message", "request_id", ...}}`. Stable codes
  include `not_authenticated`, `permission_denied`, `csrf_failed`,
  `origin_not_allowed`, `not_found`, `validation_error`, `invalid_input`,
  `rate_limited` (with `Retry-After`), `open_high_risk_signals`,
  `segregation_of_duties`, `invoice_not_decidable`, `unsupported_file_type`,
  `url_blocked_address` and `storage_unavailable`.
- **Pagination:** `?limit=` (1–100, default 25) and `?offset=`. Responses are
  `{items, total, limit, offset}`.
- **Money:** decimal strings (e.g. `"7788.00"`), never floats.
- **Contracts:** Pydantic schemas, never ORM models. Bank account numbers are write-only
  (masked in responses).

## Endpoints

Generated from the application's OpenAPI schema (with diagnostics enabled):

| Area | Method | Path | Summary |
| --- | --- | --- | --- |
| operations | GET | `/health` | Health |
| operations | GET | `/ready` | Ready |
| auth | GET | `/api/v1/auth/invitations/{token}` | Preview Invitation |
| auth | POST | `/api/v1/auth/invitations/{token}/accept` | Accept Invitation |
| auth | POST | `/api/v1/auth/login` | Login |
| auth | POST | `/api/v1/auth/logout` | Logout |
| auth | GET | `/api/v1/auth/me` | Me |
| auth | POST | `/api/v1/auth/signup` | Signup |
| auth | POST | `/api/v1/auth/switch-organization` | Switch Organization |
| organization | GET | `/api/v1/organization` | Get Organization |
| organization | PATCH | `/api/v1/organization` | Update Organization |
| organization | POST | `/api/v1/organization/email-ingestion/token` | Rotate Ingestion Token |
| organization | GET | `/api/v1/organization/invitations` | List Invitations |
| organization | POST | `/api/v1/organization/invitations` | Create Invitation |
| organization | DELETE | `/api/v1/organization/invitations/{invitation_id}` | Revoke Invitation |
| organization | GET | `/api/v1/organization/members` | List Members |
| organization | PATCH | `/api/v1/organization/members/{membership_id}` | Update Member |
| vendors | GET | `/api/v1/vendors` | List Vendors |
| vendors | POST | `/api/v1/vendors` | Create Vendor |
| vendors | GET | `/api/v1/vendors/{vendor_id}` | Get Vendor |
| vendors | PATCH | `/api/v1/vendors/{vendor_id}` | Update Vendor |
| vendors | GET | `/api/v1/vendors/{vendor_id}/bank-accounts` | Bank Accounts |
| vendors | POST | `/api/v1/vendors/{vendor_id}/bank-accounts` | Change Bank Account |
| vendors | POST | `/api/v1/vendors/{vendor_id}/bank-accounts/{account_id}/reject` | Reject Bank Account |
| vendors | POST | `/api/v1/vendors/{vendor_id}/bank-accounts/{account_id}/reveal` | Reveal Account |
| vendors | POST | `/api/v1/vendors/{vendor_id}/bank-accounts/{account_id}/verify` | Verify Bank Account |
| purchase-orders | GET | `/api/v1/purchase-orders` | List Pos |
| purchase-orders | POST | `/api/v1/purchase-orders` | Create Po |
| purchase-orders | GET | `/api/v1/purchase-orders/{po_id}` | Get Po |
| purchase-orders | PATCH | `/api/v1/purchase-orders/{po_id}` | Update Po |
| invoices | GET | `/api/v1/invoices` | List Invoices |
| invoices | POST | `/api/v1/invoices/import-url` | Import Invoice Url |
| invoices | POST | `/api/v1/invoices/upload` | Upload Invoice |
| invoices | GET | `/api/v1/invoices/{invoice_id}` | Get Invoice |
| invoices | PATCH | `/api/v1/invoices/{invoice_id}` | Update Invoice |
| invoices | POST | `/api/v1/invoices/{invoice_id}/decisions` | Decide |
| invoices | POST | `/api/v1/invoices/{invoice_id}/documents` | Replace Document |
| invoices | GET | `/api/v1/invoices/{invoice_id}/documents/{document_id}` | Download Document |
| invoices | POST | `/api/v1/invoices/{invoice_id}/reprocess` | Reprocess |
| invoices | POST | `/api/v1/invoices/{invoice_id}/signals/{signal_id}/resolve` | Resolve Signal |
| approvals | GET | `/api/v1/approvals` | Approval Queue |
| notifications | GET | `/api/v1/notifications` | List Notifications |
| notifications | POST | `/api/v1/notifications/read-all` | Mark All Read |
| notifications | GET | `/api/v1/notifications/unread-count` | Unread Count |
| notifications | POST | `/api/v1/notifications/{notification_id}/read` | Mark Read |
| audit | GET | `/api/v1/audit-events` | List Events |
| audit | GET | `/api/v1/audit-events/verify` | Verify Chain |
| dashboard | GET | `/api/v1/analytics` | Analytics |
| dashboard | GET | `/api/v1/dashboard` | Dashboard |
| email-ingestion | POST | `/api/v1/email-ingestion/inbound` | Receive Email |
| diagnostics | POST | `/api/v1/diagnostics/worker-ping` | Worker Ping |

51 operations.

## Example: upload and review

```bash
# sign in (stores cookies), then read the CSRF token from the cookie jar
curl -c jar -H 'Origin: http://localhost:3000' -H 'Content-Type: application/json' \
  -d '{"email":"reviewer@demo.invoice-risk.example","password":"…"}' http://localhost:3000/api/v1/auth/login
CSRF=$(awk '$6=="irs_csrf"{print $7}' jar)
curl -b jar -H "X-CSRF-Token: $CSRF" -H 'Origin: http://localhost:3000' \
  -F 'file=@invoice.pdf;type=application/pdf' http://localhost:3000/api/v1/invoices/upload
```
