/** Browser API client. All calls go to the same-origin /api/v1 proxy. */

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.split("; ").find((c) => c.startsWith("irs_csrf="));
  return match ? decodeURIComponent(match.slice("irs_csrf=".length)) : "";
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? (options.json !== undefined || options.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
    cache: "no-store",
    signal: options.signal,
  });
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    // A full navigation (not client routing) is intended: it discards all in-memory state.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${next}`;
  }
  if (!response.ok) {
    let payload: {
      error?: { code?: string; message?: string; request_id?: string; details?: unknown };
    } = {};
    try {
      payload = await response.json();
    } catch {
      // non-JSON error body
    }
    const error = payload.error ?? {};
    throw new ApiError(
      response.status,
      error.code ?? `http_${response.status}`,
      error.message ?? "Request failed",
      error.request_id,
      error.details,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId
      ? `${error.message} (ref ${error.requestId.slice(0, 8)})`
      : error.message;
  }
  return "Something went wrong. Please try again.";
}
