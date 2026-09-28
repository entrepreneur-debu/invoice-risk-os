import { RISK_LABELS, SEVERITY_LABELS, STATUS_LABELS } from "@/lib/format";
import type { InvoiceStatus, RiskLevel, Severity } from "@/lib/types";

import { Badge, type Tone } from "./ui";

const STATUS_TONES: Record<InvoiceStatus, Tone> = {
  uploaded: "neutral",
  queued: "neutral",
  processing: "info",
  extracted: "info",
  risk_analysis: "info",
  review_required: "warning",
  pending_approval: "warning",
  approved: "success",
  rejected: "danger",
  needs_changes: "warning",
  failed: "danger",
};

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{STATUS_LABELS[status]}</Badge>;
}

const RISK_TONES: Record<RiskLevel, Tone> = {
  none: "success",
  low: "neutral",
  medium: "warning",
  high: "danger",
};

export function RiskBadge({ level, score }: { level: RiskLevel | null; score?: number | null }) {
  if (!level) return <Badge>Not analysed</Badge>;
  return (
    <Badge tone={RISK_TONES[level]}>
      {RISK_LABELS[level]}
      {score !== undefined && score !== null ? <span className="opacity-70">· {score}</span> : null}
    </Badge>
  );
}

const SEVERITY_TONES: Record<Severity, Tone> = {
  info: "neutral",
  low: "neutral",
  medium: "warning",
  high: "danger",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={SEVERITY_TONES[severity]}>{SEVERITY_LABELS[severity]} severity</Badge>;
}
