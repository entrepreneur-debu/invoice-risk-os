# 0011 - Tamper-evident, append-only audit trail

- Status: Accepted
- Date: 2026-09-27

## Decision

Audit events are written in the same transaction as the change they describe:
- sequence-numbered per organization under an advisory lock
- SHA-256 hash-chained (`previous_hash` → `hash` over canonical JSON)
- protected by a PostgreSQL trigger that rejects UPDATE and DELETE

The application has no endpoint that edits audit events. `GET /audit-events/verify`
recomputes the chain.

## Consequences

- Edits and gaps are detectable (tested). Business changes can't be committed without
  their audit record.
- This is tamper-*evident*, not tamper-*proof*: a database superuser can disable the
  trigger and rewrite rows consistently. Periodically anchoring the latest hash in
  write-once storage (GCS bucket lock) is future work.
- Audit writes are serialized per organization (fine at V1 volumes).
