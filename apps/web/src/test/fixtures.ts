import type { InvoiceDetail, RiskSignal } from "@/lib/types";

export function signal(overrides: Partial<RiskSignal> = {}): RiskSignal {
  return {
    id: "sig-1",
    rule_code: "bank_account_mismatch",
    category: "bank",
    severity: "high",
    source: "rule",
    title: "Potential bank-account change: invoice account differs from vendor master",
    description: "The invoice directs payment to a different account.",
    evidence: [
      { label: "Account on invoice", value: "ending 1122", source: "invoice" },
      { label: "Account on file", value: "ending 5678", source: "vendor_master" },
    ],
    resolution: "open",
    resolved_by_email: null,
    resolved_at: null,
    resolution_reason: null,
    ai_explanation: null,
    ...overrides,
  };
}

export function invoice(overrides: Partial<InvoiceDetail> = {}): InvoiceDetail {
  const field = (value: string | null, source: string | null = "text_layer", confidence = 0.6) => ({
    value,
    source: value === null ? null : source,
    confidence: value === null ? 0 : confidence,
    alternatives: [],
    edited_by: null,
  });
  return {
    id: "inv-1",
    status: "review_required",
    source: "upload",
    created_at: "2026-09-20T10:00:00Z",
    uploaded_by_email: "reviewer@example.com",
    review_requested_at: "2026-09-20T10:00:05Z",
    decided_at: null,
    processing_error_code: null,
    processing_error_message: null,
    required_approvals: 1,
    fields: {
      invoice_number: field("INV-42"),
      total: field("7788.00"),
      due_date: field(null),
      vendor_gstin: field("27AAECA5678F1ZV", "document_ai+text_layer", 0.97),
      currency: field("INR"),
    },
    lines: [],
    documents: [],
    vendor: { id: "v-1", name: "Acme Industrial", gstin: "27AAECA5678F1ZV", status: "active" },
    vendor_match: "matched_by_gstin",
    purchase_order: null,
    assessment: {
      id: "as-1",
      engine_version: "1.0.0",
      risk_level: "high",
      score: 40,
      created_at: "2026-09-20T10:00:04Z",
      ai_status: "unavailable",
      ai_provider: "gemini",
      ai_model: null,
      ai_error_code: "ai_timeout",
      ai_summary: null,
      ai_reviewer_focus: [],
      ai_observations: [],
      signals: [signal()],
    },
    approval_steps: [
      {
        step_no: 1,
        cycle: 1,
        name: "review",
        required_permission: "invoice.review",
        status: "pending",
        decided_by_email: null,
        decided_at: null,
      },
    ],
    reviews: [],
    status_history: [],
    allowed_actions: ["approve", "reject", "request_changes", "comment", "edit"],
    ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}
