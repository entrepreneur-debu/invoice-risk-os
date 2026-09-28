import { describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("GET /api/backend-health", () => {
  it("calls the API over the internal URL and reports ok", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://api:8000/");
    const fetchMock = vi.fn(async () => Response.json({ status: "ok", service: "x" }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET();

    expect(fetchMock).toHaveBeenCalledWith("http://api:8000/health", expect.anything());
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
  });

  it("returns 503 when the API responds with an error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("boom", { status: 500 })),
    );

    const response = await GET();

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ status: "unavailable" });
  });

  it("returns 503 without leaking details when the API is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connect ECONNREFUSED 10.0.0.5:8000");
      }),
    );

    const response = await GET();
    const text = await response.text();

    expect(response.status).toBe(503);
    expect(text).not.toContain("ECONNREFUSED");
  });
});
