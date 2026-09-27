import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { proxy } from "./proxy";

describe("proxy", () => {
  it("redirects visitors without a session to login, preserving the destination", () => {
    const response = proxy(new NextRequest("http://localhost:3000/invoices/123?tab=risk"));
    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/invoices/123?tab=risk");
  });

  it("serves public pages without a session", () => {
    const response = proxy(new NextRequest("http://localhost:3000/login"));
    expect(response.headers.get("location")).toBeNull();
  });

  it("sets a strict nonce-based CSP", () => {
    const request = new NextRequest("http://localhost:3000/", {
      headers: { cookie: "irs_session=x" },
    });
    const csp = proxy(request).headers.get("content-security-policy") ?? "";
    expect(csp).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    const other = proxy(
      new NextRequest("http://localhost:3000/", { headers: { cookie: "irs_session=x" } }),
    );
    expect(other.headers.get("content-security-policy")).not.toBe(csp);
  });
});
