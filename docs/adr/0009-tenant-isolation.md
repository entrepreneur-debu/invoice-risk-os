# 0009 - Tenant isolation in the service layer, proven by tests

- Status: Accepted
- Date: 2026-09-27

## Context

This is a multi-tenant SaaS, and cross-tenant data exposure is the most severe possible
failure. The options were application-layer scoping, PostgreSQL row-level security (RLS),
or both.

## Decision

- Every tenant-owned table carries `organization_id`.
- Every service receives a `TenantContext` built from the session and the caller's
  **active membership**, and filters every query on `organization_id`.
- Another tenant's resource is reported as 404.
- Cross-tenant linking (vendor, PO) is rejected.
- A dedicated integration suite asserts isolation for every resource type, covering reads,
  listings and writes.

RLS is **not** enabled in V1. It is attractive defence in depth, but it adds
connection-level session state (`SET app.org_id`) across the API, workers and connection
pooling, which we will introduce deliberately after V1.

## Consequences

- One missed filter would be a vulnerability. The mitigations are the service pattern
  (no tenant queries in routers), code review, and the isolation test suite, which new
  resources must extend.
- Enabling RLS later is a recorded follow-up.
