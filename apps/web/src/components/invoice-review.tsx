"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { api, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, formatMoney, humanize, SOURCE_LABELS } from "@/lib/format";
import type { AuditEvent, FieldValue, InvoiceDetail, Page, RiskSignal } from "@/lib/types";
import { useApi } from "@/lib/use-api";

import { RiskBadge, SeverityBadge, StatusBadge } from "./badges";
import { Alert, Badge, Button, Card, Field, Input, Modal, Table, Td, Textarea, Th } from "./ui";

// ---------------------------------------------------------------------------------------
// Reason-required actions

export type DecisionKind = "approve" | "reject" | "request_changes" | "comment";

const DECISION_COPY: Record<
  DecisionKind,
  { title: string; button: string; variant: "primary" | "danger" | "secondary" }
> = {
  approve: { title: "Approve invoice", button: "Approve", variant: "primary" },
  reject: { title: "Reject invoice", button: "Reject", variant: "danger" },
  request_changes: { title: "Request changes", button: "Request changes", variant: "secondary" },
  comment: { title: "Add a comment", button: "Add comment", variant: "secondary" },
};

export function ReasonDialog({
  open,
  title,
  submitLabel,
  variant = "primary",
  description,
  onSubmit,
  onClose,
}: {
  open: boolean;
  title: string;
  submitLabel: string;
  variant?: "primary" | "danger" | "secondary";
  description?: string;
  onSubmit: (reason: string) => Promise<void>;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 3) {
      setError("Please give a reason (at least 3 characters). It is recorded in the audit trail.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(reason.trim());
      setReason("");
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title={title} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {description ? <p className="text-sm text-muted">{description}</p> : null}
        <Field
          label="Reason"
          hint="Recorded with your name, the time and the evidence shown."
          error={error}
        >
          {(p) => (
            <Textarea
              id={p.id}
              aria-describedby={p.describedBy}
              aria-invalid={p.invalid}
              rows={4}
              autoFocus
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant={variant} loading={busy}>
            {submitLabel}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function DecisionBar({
  invoice,
  onDecided,
}: {
  invoice: InvoiceDetail;
  onDecided: () => void;
}) {
  const [open, setOpen] = useState<DecisionKind | null>(null);
  const allowed = new Set(invoice.allowed_actions);
  const blocking = (invoice.assessment?.signals ?? []).filter(
    (s) => s.source === "rule" && s.severity === "high" && s.resolution === "open",
  );
  const pendingStep = invoice.approval_steps.find((s) => s.status === "pending");
  const decide = async (decision: DecisionKind, reason: string) => {
    await api(`/invoices/${invoice.id}/decisions`, { json: { decision, reason } });
    onDecided();
  };
  const buttons = (["approve", "request_changes", "reject"] as const).filter((d) => allowed.has(d));
  if (buttons.length === 0 && !allowed.has("comment")) return null;
  return (
    <div className="space-y-3">
      {pendingStep ? (
        <p className="text-sm text-muted">
          Awaiting <strong className="text-foreground">{humanize(pendingStep.name)}</strong> (step{" "}
          {pendingStep.step_no} of {invoice.approval_steps.length}).
        </p>
      ) : null}
      {allowed.has("approve") && blocking.length > 0 ? (
        <Alert tone="warning" title="Approval blocked">
          {blocking.length} high-severity signal(s) must be marked &ldquo;risk accepted&rdquo; or
          dismissed by an authorised approver before this invoice can be approved.
        </Alert>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {buttons.map((d) => (
          <Button
            key={d}
            variant={DECISION_COPY[d].variant}
            onClick={() => setOpen(d)}
            disabled={d === "approve" && blocking.length > 0}
          >
            {DECISION_COPY[d].button}
          </Button>
        ))}
        {allowed.has("comment") ? (
          <Button variant="ghost" onClick={() => setOpen("comment")}>
            Comment
          </Button>
        ) : null}
      </div>
      {open ? (
        <ReasonDialog
          open
          title={DECISION_COPY[open].title}
          submitLabel={DECISION_COPY[open].button}
          variant={DECISION_COPY[open].variant}
          description={
            open === "approve"
              ? "Approval records that you reviewed the evidence. No payment is made by this system."
              : undefined
          }
          onSubmit={(reason) => decide(open, reason)}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------------------
// Risk signals and evidence

export function EvidenceList({ signal }: { signal: RiskSignal }) {
  if (signal.evidence.length === 0) return null;
  return (
    <dl className="mt-3 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[minmax(0,14rem)_1fr]">
      {signal.evidence.map((e, i) => (
        <div key={`${e.label}-${i}`} className="contents">
          <dt className="text-muted">{e.label}</dt>
          <dd>
            {e.value ?? <span className="text-muted">—</span>}
            <span className="ml-2 text-xs text-muted">
              ({SOURCE_LABELS[e.source] ?? humanize(e.source)})
            </span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function SignalCard({
  signal,
  canResolve,
  onResolve,
}: {
  signal: RiskSignal;
  canResolve: boolean;
  onResolve: (signal: RiskSignal, resolution: "risk_accepted" | "dismissed") => void;
}) {
  const resolved = signal.resolution !== "open";
  return (
    <li className={`rounded-md border border-border p-4 ${resolved ? "opacity-75" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={signal.severity} />
        {signal.source === "ai" ? (
          <Badge tone="info">AI-suggested · advisory</Badge>
        ) : (
          <Badge>Rule: {signal.rule_code}</Badge>
        )}
        {resolved ? (
          <Badge tone="success">
            {signal.resolution === "risk_accepted" ? "Risk accepted" : "Dismissed"}
          </Badge>
        ) : null}
      </div>
      <h3 className="mt-2 font-medium">{signal.title}</h3>
      <p className="mt-1 text-sm text-muted">{signal.description}</p>
      <EvidenceList signal={signal} />
      {signal.ai_explanation ? (
        <div className="mt-3 rounded-md bg-accent/5 p-3 text-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            AI-generated explanation
          </p>
          <p className="mt-1">{signal.ai_explanation}</p>
        </div>
      ) : null}
      {resolved ? (
        <p className="mt-3 text-sm text-muted">
          {signal.resolution === "risk_accepted" ? "Risk accepted" : "Dismissed"} by{" "}
          {signal.resolved_by_email} on {formatDateTime(signal.resolved_at)}: &ldquo;
          {signal.resolution_reason}&rdquo;
        </p>
      ) : canResolve && signal.source === "rule" ? (
        <div className="mt-3 flex gap-2">
          <Button variant="secondary" onClick={() => onResolve(signal, "risk_accepted")}>
            Accept risk
          </Button>
          <Button variant="ghost" onClick={() => onResolve(signal, "dismissed")}>
            Dismiss
          </Button>
        </div>
      ) : null}
    </li>
  );
}

export function RiskPanel({
  invoice,
  onChanged,
}: {
  invoice: InvoiceDetail;
  onChanged: () => void;
}) {
  const [resolving, setResolving] = useState<{
    signal: RiskSignal;
    resolution: "risk_accepted" | "dismissed";
  } | null>(null);
  const assessment = invoice.assessment;
  if (!assessment) {
    return (
      <Card title="Risk">
        <p className="text-sm text-muted">Risk analysis has not completed yet.</p>
      </Card>
    );
  }
  const ruleSignals = assessment.signals.filter((s) => s.source === "rule");
  const aiSignals = assessment.signals.filter((s) => s.source === "ai");
  const canResolve = invoice.allowed_actions.includes("resolve_signal");
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Why this invoice needs attention{" "}
          <RiskBadge level={assessment.risk_level} score={assessment.score} />
        </span>
      }
    >
      {ruleSignals.length === 0 ? (
        <p className="text-sm">No risk rules were triggered. Deterministic checks passed.</p>
      ) : (
        <ul className="space-y-3">
          {ruleSignals.map((s) => (
            <SignalCard
              key={s.id}
              signal={s}
              canResolve={canResolve}
              onResolve={(signal, resolution) => setResolving({ signal, resolution })}
            />
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">
        Signals come from deterministic rules (engine {assessment.engine_version}); all amounts were
        recomputed in code. Signals indicate risk for human review; they are not findings of fraud.
      </p>
      <AIPanel invoice={invoice} aiSignals={aiSignals} />
      {resolving ? (
        <ReasonDialog
          open
          title={
            resolving.resolution === "risk_accepted" ? "Accept this risk" : "Dismiss this signal"
          }
          submitLabel={resolving.resolution === "risk_accepted" ? "Accept risk" : "Dismiss"}
          description={`"${resolving.signal.title}" will no longer block approval. Your reason is audited.`}
          onSubmit={async (reason) => {
            await api(`/invoices/${invoice.id}/signals/${resolving.signal.id}/resolve`, {
              json: { resolution: resolving.resolution, reason },
            });
            onChanged();
          }}
          onClose={() => setResolving(null)}
        />
      ) : null}
    </Card>
  );
}

const AI_STATUS_TEXT: Record<string, string> = {
  disabled:
    "AI assistance is turned off for this organization. The deterministic checks above are complete.",
  unavailable:
    "AI assistance was unavailable for this invoice. The deterministic checks above are complete and the invoice is fully reviewable.",
  invalid_output:
    "The AI response failed validation and was discarded. The deterministic checks above are complete.",
  not_requested: "AI assistance was not requested.",
};

export function AIPanel({
  invoice,
  aiSignals,
}: {
  invoice: InvoiceDetail;
  aiSignals: RiskSignal[];
}) {
  const assessment = invoice.assessment;
  if (!assessment) return null;
  return (
    <section
      aria-label="AI assistance"
      className="mt-5 rounded-md border border-accent/30 bg-accent/5 p-4"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-accent">
        AI assistance
        {assessment.ai_model ? ` · ${assessment.ai_provider} ${assessment.ai_model}` : ""} ·
        advisory only
      </p>
      {assessment.ai_status === "succeeded" ? (
        <div className="mt-2 space-y-3 text-sm">
          {assessment.ai_summary ? <p>{assessment.ai_summary}</p> : null}
          {assessment.ai_reviewer_focus.length > 0 ? (
            <div>
              <p className="font-medium">Suggested checks</p>
              <ul className="ml-5 list-disc">
                {assessment.ai_reviewer_focus.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {aiSignals.length > 0 ? (
            <ul className="space-y-2">
              {aiSignals.map((s) => (
                <li key={s.id}>
                  <Badge tone="info">AI observation</Badge> <strong>{s.title}</strong>:{" "}
                  {s.description}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-muted">
            Generated by AI from the evidence above. It does not change the risk level or approvals.
          </p>
        </div>
      ) : (
        <p className="mt-2 text-sm" role="status">
          {AI_STATUS_TEXT[assessment.ai_status] ?? "AI assistance is unavailable."}
          {assessment.ai_error_code ? (
            <span className="ml-1 text-xs text-muted">({assessment.ai_error_code})</span>
          ) : null}
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------------------
// Extracted fields with provenance, and manual correction

const FIELD_LABELS: Record<string, string> = {
  vendor_name: "Vendor name",
  vendor_gstin: "Vendor GSTIN",
  buyer_gstin: "Buyer GSTIN",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  due_date: "Due date",
  currency: "Currency",
  subtotal: "Subtotal",
  tax_total: "Total tax",
  cgst: "CGST",
  sgst: "SGST",
  igst: "IGST",
  total: "Total",
  po_number: "PO number",
  bank_account_number: "Bank account",
  bank_ifsc: "IFSC",
};
const MONEY_FIELDS = new Set(["subtotal", "tax_total", "cgst", "sgst", "igst", "total"]);
const DATE_FIELDS = new Set(["invoice_date", "due_date"]);
const EDITABLE = [
  "invoice_number",
  "invoice_date",
  "due_date",
  "subtotal",
  "cgst",
  "sgst",
  "igst",
  "tax_total",
  "total",
  "vendor_gstin",
  "po_number",
];

function displayValue(name: string, field: FieldValue): string {
  if (field.value === null || field.value === "") return "Not found on document";
  if (MONEY_FIELDS.has(name)) return formatMoney(field.value);
  if (DATE_FIELDS.has(name)) return formatDate(field.value);
  return field.value;
}

export function ProvenanceTable({ invoice }: { invoice: InvoiceDetail }) {
  return (
    <Table caption="Extracted invoice fields with provenance">
      <thead>
        <tr>
          <Th>Field</Th>
          <Th>Value</Th>
          <Th>Source</Th>
          <Th>Confidence</Th>
        </tr>
      </thead>
      <tbody>
        {Object.entries(FIELD_LABELS).map(([name, label]) => {
          const field = invoice.fields[name];
          if (!field) return null;
          const unknown = field.value === null || field.value === "";
          return (
            <tr key={name}>
              <Td className="text-muted">{label}</Td>
              <Td className={unknown ? "italic text-muted" : "tabular-nums"}>
                {displayValue(name, field)}
                {field.alternatives.map((alt) => (
                  <div key={`${alt.source}-${alt.value}`} className="mt-1 text-xs text-warning">
                    {SOURCE_LABELS[alt.source] ?? alt.source} read: {alt.value ?? "—"}
                  </div>
                ))}
              </Td>
              <Td className="text-xs text-muted">
                {field.source ? (SOURCE_LABELS[field.source] ?? humanize(field.source)) : "—"}
                {field.edited_by ? <div>by {field.edited_by}</div> : null}
              </Td>
              <Td className="text-xs">
                {field.confidence !== null && field.source && field.source !== "manual"
                  ? `${Math.round(field.confidence * 100)}%`
                  : "—"}
              </Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

export function CorrectionForm({
  invoice,
  onSaved,
  onCancel,
}: {
  invoice: InvoiceDetail;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const initial = Object.fromEntries(EDITABLE.map((k) => [k, invoice.fields[k]?.value ?? ""]));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const changes: Record<string, string | null> = {};
    for (const key of EDITABLE) {
      if ((values[key] ?? "") !== (initial[key] ?? ""))
        changes[key] = values[key] === "" ? null : (values[key] ?? null);
    }
    if (Object.keys(changes).length === 0) {
      setError("No changes to save.");
      return;
    }
    if (reason.trim().length < 3) {
      setError("Explain the correction (at least 3 characters).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api(`/invoices/${invoice.id}`, { method: "PATCH", json: { ...changes, reason } });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="text-sm text-muted">
        Corrections are recorded as manual values, audited, and re-run through the risk engine.
      </p>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {EDITABLE.map((key) => (
          <Field key={key} label={FIELD_LABELS[key] ?? key}>
            {(p) => (
              <Input
                id={p.id}
                type={DATE_FIELDS.has(key) ? "date" : "text"}
                inputMode={MONEY_FIELDS.has(key) ? "decimal" : undefined}
                value={values[key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              />
            )}
          </Field>
        ))}
      </div>
      <Field label="Reason for correction">
        {(p) => (
          <Textarea id={p.id} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        )}
      </Field>
      <div className="flex gap-2">
        <Button type="submit" loading={busy}>
          Save and re-analyse
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------------------
// History

export function AuditHistory({ invoiceId }: { invoiceId: string }) {
  const { data, error } = useApi<Page<AuditEvent>>(
    `/audit-events?entity_type=invoice&entity_id=${invoiceId}&limit=100`,
  );
  if (error) return <p className="text-sm text-muted">Audit history unavailable: {error}</p>;
  if (!data) return null;
  return (
    <ol className="space-y-2 text-sm">
      {data.items.map((event) => (
        <li key={event.id} className="flex flex-wrap gap-x-3">
          <span className="whitespace-nowrap text-muted">{formatDateTime(event.occurred_at)}</span>
          <span className="font-medium">{humanize(event.action)}</span>
          <span className="text-muted">{event.actor_label ?? event.actor_type}</span>
          {typeof event.details.reason === "string" ? (
            <span>&ldquo;{event.details.reason}&rdquo;</span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function InvoiceSummaryHeader({ invoice }: { invoice: InvoiceDetail }) {
  const total = invoice.fields.total?.value ?? null;
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-sm text-muted">
          <Link href="/invoices" className="text-accent hover:underline">
            Invoices
          </Link>{" "}
          /
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">
          {invoice.fields.invoice_number?.value ?? "Unnumbered invoice"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {invoice.vendor ? (
            <Link href={`/vendors/${invoice.vendor.id}`} className="text-accent hover:underline">
              {invoice.vendor.name}
            </Link>
          ) : (
            <span className="text-danger">
              Vendor not in vendor master ({invoice.fields.vendor_name?.value ?? "name not found"})
            </span>
          )}{" "}
          · {formatMoney(total ?? null, invoice.fields.currency?.value ?? "INR")} · received{" "}
          {formatDateTime(invoice.created_at)}
          {invoice.uploaded_by_email ? ` by ${invoice.uploaded_by_email}` : ""}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={invoice.status} />
        <RiskBadge
          level={invoice.assessment?.risk_level ?? null}
          score={invoice.assessment?.score}
        />
      </div>
    </div>
  );
}
