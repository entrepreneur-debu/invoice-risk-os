#!/usr/bin/env bash
# End-to-end verification of a running local stack (docker compose up -d --wait).
# Exercises: web -> API, API -> PostgreSQL/Redis/MinIO, API -> Redis -> Celery worker.
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:${API_PORT:-8000}}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:${WEB_PORT:-3000}}"

failures=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; failures=$((failures + 1)); }

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

echo "API ($BACKEND_URL)"
check "GET /health reports process alive" 200 '"status":"ok"' "$BACKEND_URL/health"
check "GET /ready reports all dependencies ready" 200 \
  '"checks":{"database":"ok","redis":"ok","object_storage":"ok"}' "$BACKEND_URL/ready"
check "Celery task executes via Redis (API -> Redis -> worker)" 200 '"result":"pong"' \
  -X POST "$BACKEND_URL/api/v1/diagnostics/worker-ping"
check "Unknown routes return the error envelope" 404 '"code":"http_404"' "$BACKEND_URL/nope"
check "Oversized bodies are rejected" 413 '"request_too_large"' \
  -X POST -H 'Content-Type: application/octet-stream' --data-binary @<(head -c 2000000 /dev/zero) \
  "$BACKEND_URL/api/v1/diagnostics/worker-ping"

echo "Web ($FRONTEND_URL)"
check "Home page renders" 200 'Engineering foundation initialized.' "$FRONTEND_URL/"
check "Web server reaches the API" 200 '"status":"ok"' "$FRONTEND_URL/api/backend-health"

if ((failures > 0)); then
  echo "$failures check(s) failed"
  exit 1
fi
echo "All smoke checks passed"
