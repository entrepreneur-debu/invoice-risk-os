# 0001 - Modular monolith with asynchronous workers

- Status: Accepted
- Date: 2026-09-27

## Context

The product will ingest invoices, extract data (OCR/AI), match invoices against vendors
and purchase orders, score risk, and route approvals with an audit trail. Much of that
work is slow (document parsing, AI calls) and must not block HTTP requests. The team is
small and the domain is still being discovered.

## Decision

Build a **modular monolith**: one deployable backend codebase, organised by domain
module, backed by one PostgreSQL database. Run slow or retryable work in **Celery
workers** that share the same codebase, with Redis as the broker. Do not use
microservices, Kubernetes, Kafka or a service mesh.

## Consequences

- One codebase, one schema and in-process calls keep changes cheap while domain
  boundaries are still moving.
- API and worker scale independently as separate processes of the same image.
- Module boundaries are a convention, not enforced by the network. Later steps should
  add import-boundary checks if modules start to tangle.
- A module can later be extracted into a service if it gains distinct scaling or
  isolation needs. Async task interfaces make that easier.
