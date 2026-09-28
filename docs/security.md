# Security

Security is a first-class concern, but **V1 is not a finished security programme**.
The controls below are implemented and tested. Known limitations are listed at the end,
and nothing here claims the system is fully secure.

## Authentication and sessions

- **Passwords:** Argon2id (argon2-cffi), minimum 12 characters, not equal to the email.
  Transparent rehash on login when parameters change. Unknown emails cost the same
  hashing time as real ones (no enumeration timing oracle).
- **Sessions:** a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie
  (`Secure` required in production). Only its HMAC-SHA256 (keyed by `AUTH_SECRET`) is
  stored. Sessions have an absolute lifetime (`SESSION_TTL_HOURS`) and an idle timeout
  (`SESSION_IDLE_TIMEOUT_MINUTES`), and logout revokes them server-side.
- **CSRF:** a double-submit token derived from the session (`irs_csrf` cookie plus the
  `X-CSRF-Token` header), required on every state-changing authenticated request.
  In addition, an **Origin check** rejects cross-site state changes, including login and signup.
- **Brute force:** per-IP and per-email rate limits (Redis), plus account lockout for
  15 minutes after 5 consecutive failures. Failed logins are audited.
- **Invitations:** single-use 256-bit tokens (stored hashed), expiring after `INVITATION_TTL_HOURS`.
- Nothing sensitive is stored in browser storage. The frontend never sees the session
  token (it's HttpOnly) or the API's internal URL.

## Authorization: RBAC

Enforced on the server in every service call (`TenantContext.require`). The UI only
reflects the same matrix (via `/auth/me`) to hide actions a user can't take.

| Permission | Owner | Admin | Reviewer | Viewer |
| --- | :-: | :-: | :-: | :-: |
| `org.read` | ✓ | ✓ | ✓ | ✓ |
| `org.manage_settings` | ✓ | ✓ | — | — |
| `members.read` | ✓ | ✓ | ✓ | — |
| `members.manage` | ✓ | ✓ | — | — |
| `vendor.read` | ✓ | ✓ | ✓ | ✓ |
| `vendor.write` | ✓ | ✓ | ✓ | — |
| `vendor.bank_verify` | ✓ | ✓ | — | — |
| `vendor.bank_reveal` | ✓ | ✓ | — | — |
| `po.read` | ✓ | ✓ | ✓ | ✓ |
| `po.write` | ✓ | ✓ | ✓ | — |
| `invoice.read` | ✓ | ✓ | ✓ | ✓ |
| `invoice.upload` | ✓ | ✓ | ✓ | — |
| `invoice.edit` | ✓ | ✓ | ✓ | — |
| `invoice.review` | ✓ | ✓ | ✓ | — |
| `invoice.approve_final` | ✓ | ✓ | — | — |
| `risk.override` | ✓ | ✓ | — | — |
| `audit.read` | ✓ | ✓ | — | — |
| `analytics.read` | ✓ | ✓ | ✓ | ✓ |
| `email_ingestion.manage` | ✓ | ✓ | — | — |

Additional rules enforced in code:

- **Role assignment:** only owners manage owners and admins. Admins can grant only
  reviewer or viewer. Nobody can change their own membership, and the last owner
  can't be removed.
- **Segregation of duties:**
  - A bank account must be verified by someone other than the person who entered it.
  - The final approver must differ from the step-1 approver.
  - Open high-severity signals block approval until an owner or admin records
    "risk accepted" with a reason.
- **Disabled members** lose access on their next request (membership is checked every time).

## Tenant isolation

Every tenant-owned table has `organization_id`. Every service query filters on the
caller's organization, and resources from another tenant return **404** (existence is
not revealed). Linking another tenant's vendor or PO to an invoice is rejected.
`tests/integration/test_tenant_isolation.py` verifies this for vendors, bank accounts,
POs, invoices, documents, reviews, risk signals, audit logs, notifications and members,
covering reads, listings and writes. See [ADR 0009](adr/0009-tenant-isolation.md).

## Input and file security

- All request bodies are validated with Pydantic (extra fields forbidden on writes).
  Validation errors return field locations, never the submitted values.
- SQL is always issued through SQLAlchemy with bound parameters (no string-built SQL).
- **Uploads:** explicit allow-list (PDF, PNG, JPEG), with these checks:
  - magic-byte sniffing, plus extension and declared-type consistency
  - size limits, applied both per route and while the body streams
  - structural parsing, rejecting malformed files
  - rejection of encrypted PDFs, PDFs with JavaScript, launch actions or embedded files,
    and image decompression bombs

  Uploaded files are never executed. Filenames are sanitized, and storage keys are
  generated (`org/<org>/invoices/<invoice>/<uuid>.<ext>`), never derived from user input.
- **Serving documents:** only through the API, after authorization, with
  `Content-Security-Policy: sandbox`, `nosniff`, `Content-Disposition`, and framing
  restricted to the same origin (for the review viewer).
- **URL import (SSRF):** see `modules/invoices/url_import.py`.
  - https only (http only if explicitly allowed; never in production), allow-listed
    ports, and no credentials in URLs.
  - All resolved addresses must be public: private, loopback, link-local (including
    cloud metadata), CGNAT, multicast, reserved and IPv4-embedded IPv6 are blocked.
  - The connection goes to the validated IP with TLS verified against the hostname,
    which defeats DNS rebinding.
  - Redirects are followed manually and re-validated at every hop.
  - Timeouts, an overall deadline and a streamed size cap apply.
- **Email ingestion:** per-organization token (stored hashed), size limit,
  deduplication on Message-ID, attachments validated like uploads. Email bodies are
  never interpreted as instructions.

## AI safety (prompt injection)

Invoice content is untrusted. See [ai.md](ai.md) for details. In summary:
- Untrusted content is delimited with an unguessable boundary.
- A security policy is set in the system instruction.
- Structured output is schema-validated and then post-validated.
- The deterministic engine flags instruction-like text as its own signal.
- The model can't change status, amounts, duplicates or permissions.

## Data protection

- **Bank account numbers:** AES-256-GCM (`DATA_ENCRYPTION_KEY`), with the row id bound as
  associated data so ciphertext can't be moved between rows. A keyed fingerprint allows
  comparison without decrypting. Responses show only the last four digits. Revealing a
  number requires `vendor.bank_reveal` and is audited. Bank details printed on invoices
  are stored only as last-four digits plus fingerprint.
- **Secrets:** only from the environment (Secret Manager in production). They are
  `SecretStr` in code, never logged, and validation errors never echo input values.
- **Production refuses to start** with: a placeholder or short `AUTH_SECRET`, the
  development encryption key, insecure cookies, wildcard CORS, diagnostics endpoints,
  or http URL import.

## Audit trail

Security and business events (sign-in, logout, failed sign-in, vendor and bank changes,
reveals, uploads, corrections, assessments, decisions, overrides, member and settings
changes) are written in the same transaction as the change. Events are append-only (a
database trigger rejects UPDATE and DELETE), sequence-numbered and SHA-256 hash-chained
per organization. `GET /api/v1/audit-events/verify` detects edits and gaps (tested).

## HTTP hardening

- **API:** `nosniff`, `Referrer-Policy: no-referrer`, `CORP: same-origin`,
  `X-Frame-Options: DENY`, `CSP: default-src 'none'`, `Cache-Control: no-store`,
  request IDs, and CORS allow-list with credentials.
- **Web:** nonce-based CSP (`script-src 'nonce-…' 'strict-dynamic'`,
  `frame-ancestors 'none'`, `object-src 'none'`), `X-Frame-Options: DENY`, `nosniff`,
  strict referrer and permissions policies. `X-Powered-By` is removed.
- **Errors:** one envelope with a code and request ID. Stack traces and exception text
  are never returned (tested in production mode).

## Logging

Logs are structured JSON (Cloud Logging compatible) with request, organization, user and
trace IDs. Headers, bodies and query strings are never logged. Keys that look sensitive
(password, secret, token, api_key, authorization, cookie, credential, account_number, …)
are redacted. HTTP client libraries are held at WARNING so URLs and headers aren't logged.

## Supply chain and CI

Python (`uv.lock`) and npm (`package-lock.json`) dependencies are locked, and base images
are pinned by digest. CI runs:
- gitleaks over the full git history (`.gitleaks.toml` allow-lists only two documented
  development/test placeholders)
- pip-audit
- npm audit (production dependencies, high severity and above)

As of 2026-09-27: no leaks, and no known vulnerabilities in 94 Python packages or the npm tree.

## Known limitations

- No MFA, SSO/SAML or password reset flow (V1 invitations only). Password reset requires an operator.
- Tenant isolation is enforced in the application layer. PostgreSQL row-level security
  is not yet enabled as defence in depth.
- Rate limiting fails open if Redis is unavailable (account lockout still applies).
- CSP allows inline `style` *attributes* (needed for chart bars). Inline scripts are nonce-bound.
- The audit hash chain is tamper-*evident*, not tamper-*proof*. A database superuser can
  disable the trigger. Anchoring hashes externally (e.g. object-lock storage) is future work.
- Log redaction is key-based. Free-text exception messages could still carry sensitive values.
- No malware scanning of uploaded documents (files are never executed or rendered
  server-side beyond PDF text extraction).
- Email notifications, data-retention purging and customer data export are not implemented.
- MinIO for local development is a third-party build ([ADR 0006](adr/0006-object-storage-minio-image.md)).
- No external penetration test has been performed.
