import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { invoice, jsonResponse, signal } from "@/test/fixtures";

import { DecisionBar, ProvenanceTable, RiskPanel, SignalCard } from "./invoice-review";

describe("risk display", () => {
  it("shows each signal with severity, rule and evidence with its source", () => {
    render(
      <ul>
        <SignalCard signal={signal()} canResolve={false} onResolve={() => undefined} />
      </ul>,
    );

    expect(screen.getByText("High severity")).toBeInTheDocument();
    expect(screen.getByText("Rule: bank_account_mismatch")).toBeInTheDocument();
    expect(screen.getByText("ending 1122")).toBeInTheDocument();
    expect(screen.getByText("(Vendor master)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept risk" })).not.toBeInTheDocument();
  });

  it("labels AI text as AI-generated and advisory", () => {
    render(
      <ul>
        <SignalCard
          signal={signal({ ai_explanation: "Payment diversion pattern." })}
          canResolve={false}
          onResolve={() => undefined}
        />
        <SignalCard
          signal={signal({ id: "ai-1", source: "ai", title: "Round amount" })}
          canResolve={false}
          onResolve={() => undefined}
        />
      </ul>,
    );

    expect(screen.getByText("AI-generated explanation")).toBeInTheDocument();
    expect(screen.getByText("AI-suggested · advisory")).toBeInTheDocument();
  });

  it("tells the reviewer when AI assistance was unavailable", () => {
    render(<RiskPanel invoice={invoice()} onChanged={() => undefined} />);

    const panel = screen.getByRole("region", { name: "AI assistance" });
    expect(within(panel).getByRole("status")).toHaveTextContent("AI assistance was unavailable");
    expect(within(panel).getByRole("status")).toHaveTextContent("fully reviewable");
  });

  it("offers overrides only when the server allows them", () => {
    const { rerender } = render(<RiskPanel invoice={invoice()} onChanged={() => undefined} />);
    expect(screen.queryByRole("button", { name: "Accept risk" })).not.toBeInTheDocument();
    rerender(
      <RiskPanel
        invoice={invoice({ allowed_actions: ["resolve_signal"] })}
        onChanged={() => undefined}
      />,
    );
    expect(screen.getByRole("button", { name: "Accept risk" })).toBeInTheDocument();
  });
});

describe("approval actions", () => {
  it("blocks approval while high-severity signals are open", () => {
    render(<DecisionBar invoice={invoice()} onDecided={() => undefined} />);

    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByText("Approval blocked")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("requires a reason and sends the decision", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ id: "r1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onDecided = vi.fn();
    const accepted = invoice({
      assessment: { ...invoice().assessment!, signals: [signal({ resolution: "risk_accepted" })] },
    });
    render(<DecisionBar invoice={accepted} onDecided={onDecided} />);

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = screen.getByRole("dialog", { name: "Approve invoice" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));
    expect(within(dialog).getByText(/Please give a reason/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    await userEvent.type(within(dialog).getByLabelText("Reason"), "Matches goods receipt GRN-17");
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/invoices/inv-1/decisions");
    expect(JSON.parse(init.body as string)).toEqual({
      decision: "approve",
      reason: "Matches goods receipt GRN-17",
    });
    expect(onDecided).toHaveBeenCalled();
  });

  it("hides decision buttons for users the server does not allow", () => {
    render(<DecisionBar invoice={invoice({ allowed_actions: [] })} onDecided={() => undefined} />);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});

describe("provenance", () => {
  it("shows the source and confidence of each value and keeps unknowns unknown", () => {
    render(<ProvenanceTable invoice={invoice()} />);

    expect(screen.getByText("₹7,788.00")).toBeInTheDocument();
    expect(screen.getByText("AI and document text agree")).toBeInTheDocument();
    expect(screen.getByText("97%")).toBeInTheDocument();
    expect(screen.getByText("Not found on document")).toBeInTheDocument();
  });
});
