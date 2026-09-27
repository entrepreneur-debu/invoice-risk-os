import type { BackendStatusResponse } from "@/lib/backend-status";
import { getApiInternalUrl } from "@/lib/server-env";

const TIMEOUT_MS = 3000;

/**
 * Same-origin proxy to the API liveness endpoint. The browser talks only to the
 * web app; the web server reaches the API over the internal network. Only a coarse
 * status is returned, never upstream details.
 */
export async function GET(): Promise<Response> {
  let status: BackendStatusResponse["status"] = "unavailable";
  try {
    const upstream = await fetch(`${getApiInternalUrl()}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (upstream.ok) {
      const body = (await upstream.json()) as { status?: unknown };
      status = body.status === "ok" ? "ok" : "unavailable";
    }
  } catch {
    status = "unavailable";
  }
  const payload: BackendStatusResponse = { status };
  return Response.json(payload, {
    status: status === "ok" ? 200 : 503,
    headers: { "Cache-Control": "no-store" },
  });
}
