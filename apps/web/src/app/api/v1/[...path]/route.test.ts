import { describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const context = (path: string[]) => ({ params: Promise.resolve({ path }) });

describe("API proxy route", () => {
  it("forwards allow-listed headers and returns cookies", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000");
    const upstream = new Response(JSON.stringify({ ok: true }), {
      status: 201,
      headers: {
        "content-type": "application/json",
        "set-cookie": "irs_session=abc; HttpOnly",
        "x-internal": "secret",
      },
    });
    const fetchMock = vi.fn(async () => upstream);
    vi.stubGlobal("fetch", fetchMock);
    const request = new Request("http://localhost:3000/api/v1/vendors?q=acme", {
      method: "POST",
      body: JSON.stringify({ name: "x" }),
      headers: {
        cookie: "irs_session=abc",
        "x-csrf-token": "t",
        "content-type": "application/json",
        "x-evil": "1",
      },
    });

    const response = await POST(request, context(["vendors"]));

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const sent = new Headers(init.headers);
    expect(url).toBe("http://api:8000/api/v1/vendors?q=acme");
    expect(sent.get("cookie")).toBe("irs_session=abc");
    expect(sent.get("x-csrf-token")).toBe("t");
    expect(sent.get("x-evil")).toBeNull();
    expect(response.status).toBe(201);
    expect(response.headers.get("set-cookie")).toContain("irs_session=abc");
    expect(response.headers.get("x-internal")).toBeNull();
  });

  it("rejects path traversal", async () => {
    const response = await GET(new Request("http://localhost/api/v1/x"), context(["..", "admin"]));
    expect(response.status).toBe(400);
  });

  it("returns a safe 502 when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connect ECONNREFUSED 10.0.0.5");
      }),
    );
    const response = await GET(
      new Request("http://localhost/api/v1/dashboard"),
      context(["dashboard"]),
    );
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain("ECONNREFUSED");
  });
});
