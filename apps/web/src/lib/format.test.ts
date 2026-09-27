import { describe, expect, it } from "vitest";

import { formatDate, formatMoney, humanize } from "./format";

describe("formatting", () => {
  it("formats rupees with Indian digit grouping", () => {
    expect(formatMoney("1234567.5")).toBe("₹12,34,567.50");
    expect(formatMoney(null)).toBe("—");
  });

  it("formats dates for India and never throws on bad input", () => {
    expect(formatDate("2026-09-05")).toBe("05 Sept 2026");
    expect(formatDate("not a date")).toBe("not a date");
    expect(formatDate(null)).toBe("—");
  });

  it("humanizes codes", () => {
    expect(humanize("invoice.step_approved")).toBe("Invoice step approved");
  });
});
