/**
 * Server-only runtime configuration. These values are read per request on the
 * server and are never bundled into browser JavaScript (no NEXT_PUBLIC_ prefix).
 */
const DEFAULT_API_INTERNAL_URL = "http://localhost:8000";

export function getApiInternalUrl(): string {
  const value = process.env.API_INTERNAL_URL?.trim() || DEFAULT_API_INTERNAL_URL;
  return value.replace(/\/+$/, "");
}
