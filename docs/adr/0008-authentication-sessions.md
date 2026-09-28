# 0008 - Server-side sessions in HttpOnly cookies

- Status: Accepted
- Date: 2026-09-27

## Context

Browser users need authenticated sessions that can be revoked, time out when idle, and
never expose tokens to JavaScript. JWTs in local storage are exposed to XSS and can't be
revoked individually.

## Decision

- An opaque random 256-bit token lives in an `HttpOnly`, `SameSite=Lax` (and, in
  production, `Secure`) cookie. The database stores only its HMAC keyed by `AUTH_SECRET`.
- Sessions have an absolute TTL and an idle timeout, and logout revokes them server-side.
- CSRF protection uses a double-submit token derived from the session, required on every
  state-changing request, plus an Origin allow-list check that also covers login and signup.
- Passwords are hashed with Argon2id. Brute force is limited by Redis rate limits plus
  per-account lockout.

## Consequences

- Revocation is immediate, and there is no token in JavaScript.
- Each authenticated request performs one indexed session lookup (acceptable for V1).
- The browser must reach the API same-origin; the web proxy provides that (ADR 0005).
- Not in V1: MFA, SSO and self-service password reset.
