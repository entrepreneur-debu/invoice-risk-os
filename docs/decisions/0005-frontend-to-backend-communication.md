# 0005 - Frontend reaches the API through a same-origin server route

- Status: Accepted
- Date: 2026-09-27

## Context

The web app needs to show API connectivity now and will call the API heavily later.
Next.js inlines `NEXT_PUBLIC_*` variables at **build** time, so baking an API URL into
the browser bundle ties each image to one environment.

## Decision

For Step 1 the browser calls a same-origin Next.js route handler
(`/api/backend-health`). That handler calls the API server-side using the runtime,
server-only variable `API_INTERNAL_URL` (`http://api:8000` inside Compose). The API
also has an explicit CORS allow-list (`CORS_ALLOWED_ORIGINS`) for any direct browser
calls later.

## Consequences

- One web image works in every environment. No API URL is compiled into client code.
- The browser never sees internal hostnames or upstream error details.
- How authenticated data requests flow (a backend-for-frontend proxy versus direct
  browser-to-API calls with CORS) is **deliberately left open** until authentication
  is designed in a later step.
