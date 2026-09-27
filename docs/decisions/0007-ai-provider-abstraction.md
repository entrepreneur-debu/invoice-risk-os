# 0007 - AI provider abstraction

- Status: Accepted
- Date: 2026-09-27

## Context

Later steps will use LLMs (Anthropic Claude first) for invoice understanding and risk
explanations. Coupling domain code to a vendor SDK would make testing, provider
changes, cost controls and audit logging harder.

## Decision

Domain code depends only on the `AIProvider` protocol (`app/ai/provider.py`), with
provider-neutral `AIRequest` / `AIResponse` types. `create_ai_provider(settings)`
selects the implementation from `AI_PROVIDER`:

- `mock` (default): `MockAIProvider`. Deterministic, makes no network calls, records
  requests, and supports queued responses and simulated failures. Used by all tests.
- `gemini`: `GeminiProvider` (`app/ai/gemini.py`), using the official `google-genai`
  SDK against the Gemini Developer API. It needs `GEMINI_API_KEY`, with `GEMINI_MODEL`
  and `AI_REQUEST_TIMEOUT_SECONDS` configurable. The SDK is imported lazily, only
  when this provider is selected. Its errors surface as `AIProviderError` with the
  HTTP status only. Added 2026-09-27 at the product owner's request.
- `anthropic`: reserved. Selecting it currently raises `NotImplementedError`. The
  Anthropic SDK is **not** a dependency yet, and settings validation already requires
  `ANTHROPIC_API_KEY` for it.

## Consequences

- Automated tests never call a real AI API.
- The interface is deliberately minimal (`generate`). It will grow (structured output,
  document inputs, usage and cost accounting, prompt versioning) when invoice analysis
  is designed. Changing it now is cheap because nothing depends on it yet.
- The Anthropic implementation must go behind this protocol, and AI inputs and outputs
  will need audit logging with redaction.
