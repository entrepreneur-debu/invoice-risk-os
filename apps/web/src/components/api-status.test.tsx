import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiStatus } from "./api-status";

function mockFetch(implementation: () => Promise<Response>) {
  const fetchMock = vi.fn(implementation);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ApiStatus", () => {
  it("shows a checking state before the response arrives", () => {
    mockFetch(() => new Promise<Response>(() => {}));

    render(<ApiStatus />);

    expect(screen.getByRole("status")).toHaveTextContent("Checking API connection…");
  });

  it("reports a healthy backend", async () => {
    const fetchMock = mockFetch(async () => Response.json({ status: "ok" }));

    render(<ApiStatus />);

    expect(await screen.findByText("API connection healthy")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/backend-health", expect.anything());
  });

  it("reports an unavailable backend", async () => {
    mockFetch(async () => Response.json({ status: "unavailable" }, { status: 503 }));

    render(<ApiStatus />);

    expect(await screen.findByText("API unavailable")).toBeInTheDocument();
  });

  it("treats network failures as unavailable", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    mockFetch(async () => {
      throw new TypeError("network down");
    });

    render(<ApiStatus />);

    expect(await screen.findByText("API unavailable")).toBeInTheDocument();
  });
});
