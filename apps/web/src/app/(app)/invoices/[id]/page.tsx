"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import {
  AuditHistory,
  CorrectionForm,
  DecisionBar,
  InvoiceSummaryHeader,
  ProvenanceTable,
  RiskPanel,
} from "@/components/invoice-review";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  Loading,
  Spinner,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, formatMoney, humanize, STATUS_LABELS } from "@/lib/format";
import type { InvoiceDetail, InvoiceStatus } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const IN_FLIGHT: InvoiceStatus[] = [
  "uploaded",
  "queued",
  "processing",
  "extracted",
  "risk_analysis",
];

function DocumentViewer({ invoice }: { invoice: InvoiceDetail }) {
  const document = invoice.documents[invoice.documents.length - 1];
  if (!document) return <p className="text-sm text-muted">No document.</p>;
  const url = `/api/v1/invoices/${invoice.id}/documents/${document.id}`;
  return (
    <div className="space-y-2">
      {document.content_type === "application/pdf" ? (
        <iframe
          src={`${url}?inline=true`}
          title="Original invoice document"
          className="h-[36rem] w-full rounded-md border border-border bg-white"
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- private, authenticated document
        <img
          src={`${url}?inline=true`}
          alt="Original invoice document"
          className="max-h-[36rem] w-full rounded-md border border-border object-contain"
        />
      )}
      <p className="flex flex-wrap justify-between gap-2 text-xs text-muted">
        <span>
          {document.original_filename} · {(document.size_bytes / 1024).toFixed(0)} KB · SHA-256{" "}
          {document.sha256.slice(0, 12)}…
        </span>
        <a href={url} className="text-accent hover:underline">
          Download original
        </a>
      </p>
    </div>
  );
}

function ReplaceDocument({ invoice, onDone }: { invoice: InvoiceDetail; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await api(`/invoices/${invoice.id}/documents`, { form });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <Field label="Corrected document (PDF, PNG or JPEG)">
        {(p) => (
          <Input
            id={p.id}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        )}
      </Field>
      <Button type="submit" variant="secondary" loading={busy} disabled={!file}>
        Upload corrected document
      </Button>
    </form>
  );
}

export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const { data: invoice, error, loading, reload } = useApi<InvoiceDetail>(`/invoices/${id}`);
  const [editing, setEditing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const inFlight = invoice ? IN_FLIGHT.includes(invoice.status) : false;

  useEffect(() => {
    if (!inFlight) return;
    const timer = window.setInterval(reload, 2000);
    return () => window.clearInterval(timer);
  }, [inFlight, reload]);

  if (loading && !invoice) return <Loading />;
  if (error || !invoice)
    return (
      <Alert tone="danger" title="Invoice unavailable">
        {error}
      </Alert>
    );

  const reprocess = async () => {
    setActionError(null);
    try {
      await api(`/invoices/${invoice.id}/reprocess`, { method: "POST" });
      reload();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  };

  return (
    <>
      <InvoiceSummaryHeader invoice={invoice} />
      {inFlight ? (
        <div className="mb-4">
          <Alert tone="info" title={STATUS_LABELS[invoice.status]}>
            <span className="inline-flex items-center gap-2">
              <Spinner /> Extracting data and running risk checks. This page updates automatically.
            </span>
          </Alert>
        </div>
      ) : null}
      {invoice.status === "failed" ? (
        <div className="mb-4 space-y-3">
          <Alert tone="danger" title="Processing failed">
            {invoice.processing_error_message}{" "}
            <span className="text-xs text-muted">({invoice.processing_error_code})</span>
          </Alert>
          {invoice.allowed_actions.includes("reprocess") ? (
            <Button variant="secondary" onClick={reprocess}>
              Try again
            </Button>
          ) : null}
        </div>
      ) : null}
      {actionError ? (
        <div className="mb-4">
          <Alert tone="danger">{actionError}</Alert>
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="space-y-6">
          <RiskPanel invoice={invoice} onChanged={reload} />
          <Card title="Decision">
            {invoice.status === "approved" || invoice.status === "rejected" ? (
              <p className="text-sm">
                {STATUS_LABELS[invoice.status]} on {formatDateTime(invoice.decided_at)}. Decisions
                are final and audited. This system does not execute payments.
              </p>
            ) : (
              <DecisionBar invoice={invoice} onDecided={reload} />
            )}
            {invoice.status === "needs_changes" &&
            invoice.allowed_actions.includes("replace_document") ? (
              <div className="mt-4">
                <ReplaceDocument invoice={invoice} onDone={reload} />
              </div>
            ) : null}
          </Card>
          <Card
            title="Extracted data"
            actions={
              invoice.allowed_actions.includes("edit") && !editing ? (
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Correct values
                </Button>
              ) : null
            }
          >
            {editing ? (
              <CorrectionForm
                invoice={invoice}
                onCancel={() => setEditing(false)}
                onSaved={() => {
                  setEditing(false);
                  reload();
                }}
              />
            ) : (
              <ProvenanceTable invoice={invoice} />
            )}
          </Card>
          {invoice.lines.length > 0 ? (
            <Table caption="Invoice line items">
              <thead>
                <tr>
                  <Th>#</Th>
                  <Th>Description</Th>
                  <Th className="text-right">Qty</Th>
                  <Th className="text-right">Unit price</Th>
                  <Th className="text-right">GST %</Th>
                  <Th className="text-right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {invoice.lines.map((line) => (
                  <tr key={line.line_no}>
                    <Td>{line.line_no}</Td>
                    <Td>{line.description}</Td>
                    <Td className="text-right tabular-nums">{line.quantity ?? "—"}</Td>
                    <Td className="text-right tabular-nums">{formatMoney(line.unit_price)}</Td>
                    <Td className="text-right tabular-nums">{line.tax_rate ?? "—"}</Td>
                    <Td className="text-right tabular-nums">{formatMoney(line.amount)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : null}
        </div>

        <div className="space-y-6">
          <Card title="Original invoice">
            <DocumentViewer invoice={invoice} />
          </Card>
          <Card title="Vendor and purchase order">
            <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
              <dt className="text-muted">Vendor</dt>
              <dd>
                {invoice.vendor ? (
                  <Link
                    href={`/vendors/${invoice.vendor.id}`}
                    className="text-accent hover:underline"
                  >
                    {invoice.vendor.name}
                  </Link>
                ) : (
                  "Not matched"
                )}
                {invoice.vendor_match ? (
                  <span className="ml-2 text-xs text-muted">
                    ({humanize(invoice.vendor_match)})
                  </span>
                ) : null}
              </dd>
              <dt className="text-muted">GSTIN on file</dt>
              <dd>{invoice.vendor?.gstin ?? "—"}</dd>
              <dt className="text-muted">Purchase order</dt>
              <dd>
                {invoice.purchase_order ? (
                  <Link
                    href={`/purchase-orders/${invoice.purchase_order.id}`}
                    className="text-accent hover:underline"
                  >
                    {invoice.purchase_order.po_number} · {formatMoney(invoice.purchase_order.total)}{" "}
                    · {invoice.purchase_order.status}
                  </Link>
                ) : (
                  "None linked"
                )}
              </dd>
            </dl>
          </Card>
          <Card title="Approval workflow">
            {invoice.approval_steps.length === 0 ? (
              <p className="text-sm text-muted">Starts when analysis completes.</p>
            ) : (
              <ol className="space-y-2 text-sm">
                {invoice.approval_steps.map((step) => (
                  <li key={`${step.cycle}-${step.step_no}`} className="flex justify-between gap-3">
                    <span>
                      {step.step_no}. {humanize(step.name)}
                    </span>
                    <span className="text-muted">
                      {humanize(step.status)}
                      {step.decided_by_email ? ` · ${step.decided_by_email}` : ""}
                    </span>
                  </li>
                ))}
              </ol>
            )}
            {invoice.reviews.length > 0 ? (
              <div className="mt-4 border-t border-border pt-4">
                <h3 className="mb-2 text-sm font-semibold">Decisions and comments</h3>
                <ul className="space-y-3 text-sm">
                  {invoice.reviews.map((review) => (
                    <li key={review.id}>
                      <p>
                        <strong>{humanize(review.decision)}</strong> by {review.reviewer_email} ·{" "}
                        <span className="text-muted">{formatDateTime(review.created_at)}</span>
                      </p>
                      <p className="text-muted">&ldquo;{review.reason}&rdquo;</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Card>
          <Card title="Audit history">
            <AuditHistory invoiceId={invoice.id} />
          </Card>
        </div>
      </div>
    </>
  );
}
