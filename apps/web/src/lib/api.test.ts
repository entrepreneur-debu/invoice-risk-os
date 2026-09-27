import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, errorMessage } from "./api";

afterEach(() => {
  document.cookie = "irs_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("api client", () => {
  it("sends the CSRF token on state-changing requests only", async () => {
    document.cookie = "irs_csrf=token-123";
    const fetchMock = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/vendors", { json: { name: "x" } });
    await api("/vendors");

    const [postUrl, post] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const [, get] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(postUrl).toBe("/api/v1/vendors");
    expect((post.headers as Record<string, string>)["X-CSRF-Token"]).toBe("token-123");
    expect(post.method).toBe("POST");
    expect((get.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });

  it("turns the error envelope into an ApiError with the request id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          {
            error: {
              code: "open_high_risk_signals",
              message: "Resolve signals first",
              request_id: "abcdef1234",
            },
          },
          { status: 409 },
        ),
      ),
    );

    const error = await api("/invoices/1/decisions", { json: {} }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("open_high_risk_signals");
    expect(errorMessage(error)).toBe("Resolve signals first (ref abcdef12)");
  });

  it("does not leak unexpected errors to the user", () => {
    expect(errorMessage(new TypeError("stack trace details"))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});
