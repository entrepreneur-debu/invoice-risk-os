import type { InvoiceStatus, RiskLevel, Severity } from "./types";

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

export function formatMoney(value: string | number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined || value === "") return "—";
  const number = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (currency === "INR") return inr.format(number);
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(number);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const text = value.replace(/[._]/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const STATUS_LABELS: Record<InvoiceStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  processing: "Processing",
  extracted: "Extracted",
  risk_analysis: "Analysing risk",
  review_required: "Review required",
  pending_approval: "Pending approval",
  approved: "Approved",
  rejected: "Rejected",
  needs_changes: "Changes requested",
  failed: "Processing failed",
};

export const RISK_LABELS: Record<RiskLevel, string> = {
  none: "No signals",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  info: "Info",
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const SOURCE_LABELS: Record<string, string> = {
  document_ai: "Read by AI from the document",
  "document_ai+text_layer": "AI and document text agree",
  text_layer: "Document text layer",
  manual: "Entered manually",
  invoice: "Invoice",
  vendor_master: "Vendor master",
  purchase_order: "Purchase order",
  invoice_history: "Invoice history",
  document: "Document",
  policy: "Organization policy",
  ai: "AI-generated",
};
