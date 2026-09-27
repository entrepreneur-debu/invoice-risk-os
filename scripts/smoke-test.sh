#!/usr/bin/env bash
# Fast end-to-end checks of a running stack (docker compose up -d --wait).
# The full business workflow is covered by: cd apps/backend && uv run pytest -m e2e
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:${API_PORT:-8000}}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:${WEB_PORT:-3000}}"

failures=0
pass() { printf '  PASS %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; failures=$((failures + 1)); }

# check <description> <expected-status> <expected-substring> <curl args...>
check() {
  local description="$1" expected_status="$2" expected_body="$3"
  shift 3
  local body status
  body="$(curl -sS --max-time 20 -w $'\n%{http_code}' "$@" || true)"
  status="${body##*$'\n'}"
  body="${body%$'\n'*}"
  if [[ "$status" == "$expected_status" && "$body" == *"$expected_body"* ]]; then
    pass "$description"
  else
    fail "$description (status=$status body=${body:0:200})"
  fi
}

# header_check <description> <header-substring> <url>
header_check() {
  if curl -sS -D - -o /dev/null --max-time 20 "$3" | tr -d '\r' | grep -qi -- "$2"; then
    pass "$1"
  else
    fail "$1"
  fi
}

echo "API ($BACKEND_URL)"
check "GET /health reports process alive" 200 '"status":"ok"' "$BACKEND_URL/health"
check "GET /ready reports all dependencies ready" 200 \
  '"checks":{"database":"ok","redis":"ok","object_storage":"ok"}' "$BACKEND_URL/ready"
check "Protected endpoints require authentication" 401 '"code":"not_authenticated"' \
  "$BACKEND_URL/api/v1/invoices"
check "Unknown routes return the error envelope" 404 '"code":"http_404"' "$BACKEND_URL/nope"
check "Oversized JSON bodies are rejected" 413 '"request_too_large"' \
  -X POST -H 'Content-Type: application/json' --data-binary @<(head -c 2000000 /dev/zero) \
  "$BACKEND_URL/api/v1/auth/login"
header_check "API responses carry security headers" "x-content-type-options: nosniff" "$BACKEND_URL/health"

echo "Web ($FRONTEND_URL)"
check "Login page renders" 200 'Sign in' "$FRONTEND_URL/login"
header_check "Pages carry a nonce-based CSP" "content-security-policy: default-src 'self'; script-src 'self' 'nonce-" \
  "$FRONTEND_URL/login"
header_check "Unauthenticated app pages redirect to login" "location: /login" "$FRONTEND_URL/invoices"
check "Web server reaches the API" 200 '"status":"ok"' "$FRONTEND_URL/api/backend-health"
check "Same-origin API proxy enforces authentication" 401 '"not_authenticated"' \
  "$FRONTEND_URL/api/v1/auth/me"
check "Cross-site state changes are rejected" 403 '"origin_not_allowed"' \
  -X POST -H 'Origin: https://evil.example' -H 'Content-Type: application/json' \
  -d '{"email":"a@b.example","password":"x"}' "$FRONTEND_URL/api/v1/auth/login"

if ((failures > 0)); then
  echo "$failures check(s) failed"
  exit 1
fi
echo "All smoke checks passed"
