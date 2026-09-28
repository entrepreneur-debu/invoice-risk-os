import { afterEach, describe, expect, it, vi } from "vitest";

import { apiAuthHeaders, resetIdTokenCache } from "./api-auth";

afterEach(() => resetIdTokenCache());

describe("apiAuthHeaders", () => {
  it("adds nothing when no audience is configured (local development)", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(await apiAuthHeaders()).toEqual({});
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fetches and caches an identity token from the metadata server", async () => {
    vi.stubEnv("API_ID_TOKEN_AUDIENCE", "https://irs-api-xyz.a.run.app");
    const fetchMock = vi.fn(async () => new Response("eyJ.token.sig\n"));
    vi.stubGlobal("fetch", fetchMock);

    expect(await apiAuthHeaders()).toEqual({ Authorization: "Bearer eyJ.token.sig" });
    await apiAuthHeaders();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("audience=https%3A%2F%2Firs-api-xyz.a.run.app");
    expect(new Headers(init.headers).get("Metadata-Flavor")).toBe("Google");
  });
});
