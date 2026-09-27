# 0010 - Deterministic risk engine is authoritative; AI is advisory

- Status: Accepted
- Date: 2026-09-27

## Context

The product prevents payment errors and fraud. Decisions must be explainable,
reproducible and auditable. LLMs are useful for reading documents and explaining
evidence, but they are non-deterministic and can be manipulated by document content.

## Decision

- Risk signals, score, level, duplicate detection, GST arithmetic and PO matching are
  computed by pure, versioned rules (`ENGINE_VERSION`) using `Decimal` arithmetic.
- Gemini is used for (a) transcribing documents, merged with an independent text-layer
  extraction and with per-field provenance, and (b) explaining evidence to reviewers.
- AI output is schema-validated and post-validated, labelled as AI-generated, and **never**
  changes the score, level, approvals, status or authorization.
- Humans decide. Approvals require reasons, and high-severity signals require an explicit,
  audited override.

## Consequences

- Rules are easy to test (every rule has unit tests) and to explain to auditors.
- Some patterns a model could spot are only *observations* in V1, not signals.
- If AI is unavailable, the invoice is still fully reviewable.
