// Response contracts of the FastAPI service (see apps/backend/app/modules/*/schemas.py).

export type Role = "owner" | "admin" | "reviewer" | "viewer";
export type Severity = "info" | "low" | "medium" | "high";
export type RiskLevel = "none" | "low" | "medium" | "high";
export type InvoiceStatus =
  | "uploaded"
  | "queued"
  | "processing"
  | "extracted"
  | "risk_analysis"
  | "review_required"
  | "pending_approval"
  | "approved"
  | "rejected"
  | "needs_changes"
  | "failed";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface Me {
  user_id: string;
  email: string;
  full_name: string;
  organization: OrganizationSummary | null;
  organizations: OrganizationSummary[];
  permissions: string[];
  csrf_token: string;
  session_expires_at: string;
}

export interface BankAccount {
  id: string;
  account_holder_name: string;
  account_number_masked: string;
  ifsc: string;
  bank_name: string | null;
  status: "pending_verification" | "verified" | "rejected" | "superseded";
  is_current: boolean;
  previous_account_id: string | null;
  change_reason: string | null;
  source: string;
  created_at: string;
  created_by_email: string | null;
  verified_by_email: string | null;
  verified_at: string | null;
  verification_note: string | null;
}

export interface Vendor {
  id: string;
  name: string;
  gstin: string | null;
  pan: string | null;
  state_code: string | null;
  email: string | null;
  phone: string | null;
  contact_name: string | null;
  address: string | null;
  notes: string | null;
  status: "active" | "inactive";
  created_at: string;
  updated_at: string;
  current_bank_account: BankAccount | null;
}

export interface VendorDetail extends Vendor {
  risk: {
    invoice_count: number;
    total_invoiced: string;
    open_high_signals: number;
    signals_last_90_days: number;
    pending_bank_verification: boolean;
    last_bank_change_at: string | null;
    last_invoice_date: string | null;
  };
}

export interface POLine {
  id: string;
  line_no: number;
  description: string;
  sku: string | null;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  amount: string;
  invoiced_quantity: string;
}

export interface PurchaseOrder {
  id: string;
  vendor_id: string;
  vendor_name: string;
  po_number: string;
  issue_date: string | null;
  currency: string;
  status: "draft" | "open" | "closed" | "cancelled";
  subtotal: string;
  tax_total: string;
  total: string;
  invoiced_total: string;
  notes: string | null;
  created_at: string;
  lines: POLine[];
  linked_invoice_ids: string[];
}

export interface InvoiceSummary {
  id: string;
  status: InvoiceStatus;
  source: "upload" | "url_import" | "email";
  invoice_number: string | null;
  invoice_date: string | null;
  total: string | null;
  currency: string | null;
  vendor_id: string | null;
  vendor_name: string | null;
  risk_level: RiskLevel | null;
  risk_score: number | null;
  open_high_signals: number;
  required_approvals: number;
  created_at: string;
  processing_error_code: string | null;
}

export interface FieldValue {
  value: string | null;
  source: string | null;
  confidence: number | null;
  alternatives: { source: string; value: string | null }[];
  edited_by: string | null;
}

export interface Evidence {
  label: string;
  value: string | null;
  source: string;
}

export interface RiskSignal {
  id: string;
  rule_code: string;
  category: string;
  severity: Severity;
  source: "rule" | "ai";
  title: string;
  description: string;
  evidence: Evidence[];
  resolution: "open" | "risk_accepted" | "dismissed";
  resolved_by_email: string | null;
  resolved_at: string | null;
  resolution_reason: string | null;
  ai_explanation: string | null;
}

export interface RiskAssessment {
  id: string;
  engine_version: string;
  risk_level: RiskLevel;
  score: number;
  created_at: string;
  ai_status: "not_requested" | "disabled" | "succeeded" | "unavailable" | "invalid_output";
  ai_provider: string | null;
  ai_model: string | null;
  ai_error_code: string | null;
  ai_summary: string | null;
  ai_reviewer_focus: string[];
  ai_observations: { title: string; detail: string; suggested_severity: string }[];
  signals: RiskSignal[];
}

export interface InvoiceDetail {
  id: string;
  status: InvoiceStatus;
  source: string;
  created_at: string;
  uploaded_by_email: string | null;
  review_requested_at: string | null;
  decided_at: string | null;
  processing_error_code: string | null;
  processing_error_message: string | null;
  required_approvals: number;
  fields: Record<string, FieldValue>;
  lines: {
    line_no: number;
    description: string;
    quantity: string | null;
    unit_price: string | null;
    tax_rate: string | null;
    amount: string | null;
    source: string;
  }[];
  documents: {
    id: string;
    original_filename: string;
    content_type: string;
    size_bytes: number;
    sha256: string;
    page_count: number | null;
    source_url_host: string | null;
    created_at: string;
  }[];
  vendor: { id: string; name: string; gstin: string | null; status: string } | null;
  vendor_match: string | null;
  purchase_order: {
    id: string;
    po_number: string;
    status: string;
    total: string;
    vendor_id: string;
  } | null;
  assessment: RiskAssessment | null;
  approval_steps: {
    step_no: number;
    cycle: number;
    name: string;
    required_permission: string;
    status: string;
    decided_by_email: string | null;
    decided_at: string | null;
  }[];
  reviews: {
    id: string;
    reviewer_email: string;
    decision: string;
    step_no: number | null;
    reason: string;
    evidence_snapshot: Record<string, unknown>;
    created_at: string;
  }[];
  status_history: {
    from_status: string | null;
    to_status: string;
    actor_type: string;
    actor_email: string | null;
    reason: string | null;
    created_at: string;
  }[];
  allowed_actions: string[];
}

export interface Notification {
  id: string;
  kind: string;
  severity: Severity;
  title: string;
  body: string;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  sequence: number;
  occurred_at: string;
  actor_type: string;
  actor_label: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  request_id: string | null;
  ip_address: string | null;
  details: Record<string, unknown>;
  hash: string;
}

export interface OrganizationSettings {
  high_value_threshold: string;
  second_approval_risk_levels: RiskLevel[];
  require_po_above: string | null;
  price_tolerance_percent: string;
  quantity_tolerance_percent: string;
  amount_tolerance_absolute: string;
  duplicate_window_days: number;
  unusual_amount_multiplier: string;
  price_increase_alert_percent: string;
  split_invoice_window_days: number;
  new_vendor_days: number;
  bank_change_alert_days: number;
  ai_assistance_enabled: boolean;
  ai_document_extraction_enabled: boolean;
  email_ingestion_enabled: boolean;
  document_retention_days: number;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  gstin: string | null;
  state_code: string | null;
  settings: OrganizationSettings;
  inbound_email_address: string | null;
  email_ingestion_configured: boolean;
}

export interface Member {
  membership_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  status: "active" | "disabled";
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  accepted_at: string | null;
  invitation_url?: string | null;
}

export interface Dashboard {
  invoices_received: number;
  by_status: Record<InvoiceStatus, number>;
  requiring_review: number;
  processing: number;
  high_risk_pending: number;
  approved: number;
  rejected: number;
  needs_changes: number;
  failed: number;
  potential_duplicates: number;
  pending_value: string;
  flagged_and_rejected: { label: string; count: number; total_value: string };
  vendor_risk: { vendor_id: string; vendor_name: string; risk_signals: number }[];
  recent_activity: {
    action: string;
    entity_type: string;
    entity_id: string | null;
    actor: string | null;
    occurred_at: string;
  }[];
}

export interface Analytics {
  period_days: number;
  invoice_volume: { week_start: string; count: number; total_value: string }[];
  risk_categories: { category: string; count: number }[];
  severity_distribution: Record<string, number>;
  risk_level_distribution: Record<string, number>;
  top_rules: { rule_code: string; count: number }[];
  decisions: Record<string, number>;
  review_turnaround_hours: {
    average: number | null;
    median: number | null;
    decided_invoices: number;
  };
  duplicate_detections: number;
  po_mismatch_signals: number;
  signals_resolved_by_override: number;
  vendor_anomalies: { vendor_name: string; signals: number }[];
}
