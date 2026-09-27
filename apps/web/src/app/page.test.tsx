import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";

import HomePage from "./page";

describe("HomePage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
  });

  it("renders the product name and foundation status", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Invoice Risk & Payment Control OS" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Engineering foundation initialized.")).toBeInTheDocument();
  });

  it("renders inside an accessible application shell", () => {
    render(
      <AppShell>
        <HomePage />
      </AppShell>,
    );

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});
