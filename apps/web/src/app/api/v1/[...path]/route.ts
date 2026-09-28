import { apiAuthHeaders } from "@/lib/api-auth";
import { getApiInternalUrl } from "@/lib/server-env";

/**
 * Same-origin proxy from the browser to the FastAPI service.
 *
 * - Cookies stay first-party (HttpOnly session + CSRF cookie are set on this origin).
 * - The API's internal URL is never exposed to the browser.
 * - Only an allow-list of headers is forwarded in either direction.
 * - Request bodies are streamed (uploads); the API enforces size limits.
 */
const FORWARD_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "content-length",
  "cookie",
  "origin",
  "user-agent",
  "x-csrf-token",
  "x-request-id",
  "x-ingestion-token",
  "x-cloud-trace-context",
];
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "content-security-policy",
  "x-frame-options",
  "cache-control",
  "retry-after",
  "x-request-id",
];
const TIMEOUT_MS = 120_000;

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: Request, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  if (path.some((segment) => segment === ".." || segment.includes("/"))) {
    return Response.json({ error: { code: "bad_path", message: "Invalid path" } }, { status: 400 });
  }
  const incoming = new URL(request.url);
  const target = `${getApiInternalUrl()}/api/v1/${path.map(encodeURIComponent).join("/")}${incoming.search}`;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Client address for rate limiting/audit: first hop as seen by this server.
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    // Private Cloud Run API: service identity token (no-op locally).
    for (const [name, value] of Object.entries(await apiAuthHeaders())) headers.set(name, value);
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
      // Required by Node's fetch to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
    } as RequestInit);
  } catch {
    return Response.json(
      { error: { code: "api_unreachable", message: "The service is temporarily unavailable" } },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
