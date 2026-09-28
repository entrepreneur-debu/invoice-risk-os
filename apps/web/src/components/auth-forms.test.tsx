import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { routerMock } from "@/test/setup";

import { LoginForm, safeNext, SignupForm } from "./auth-forms";

describe("safeNext", () => {
  it.each([
    ["/invoices/1", "/invoices/1"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    [null, "/"],
  ])("sanitises %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});

describe("LoginForm", () => {
  it("signs in and redirects to the requested page", async () => {
    const fetchMock = vi.fn(async () => Response.json({ user_id: "u1" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<LoginForm next="/invoices" />);

    await userEvent.type(screen.getByLabelText("Work email"), "a@b.example");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/login");
    expect(JSON.parse(init.body as string)).toEqual({
      email: "a@b.example",
      password: "correct-horse-battery",
    });
    expect(routerMock.replace).toHaveBeenCalledWith("/invoices");
  });

  it("shows a generic error for bad credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          { error: { code: "invalid_credentials", message: "Invalid email or password" } },
          { status: 401 },
        ),
      ),
    );
    render(<LoginForm next="/" />);

    await userEvent.type(screen.getByLabelText("Work email"), "a@b.example");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(routerMock.replace).not.toHaveBeenCalled();
  });

  it("explains rate limiting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          { error: { code: "rate_limited", message: "Too many requests" } },
          { status: 429 },
        ),
      ),
    );
    render(<LoginForm next="/" />);
    await userEvent.type(screen.getByLabelText("Work email"), "a@b.example");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many sign-in attempts");
  });
});

describe("SignupForm", () => {
  it("validates password length before calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<SignupForm />);

    await userEvent.type(screen.getByLabelText("Your name"), "Priya");
    await userEvent.type(screen.getByLabelText("Work email"), "p@x.example");
    await userEvent.type(screen.getByLabelText("Organization name"), "Acme");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create organization" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("at least 12 characters");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
