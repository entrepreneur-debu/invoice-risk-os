"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input, PageHeader, Select } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { Page, PurchaseOrder, Vendor } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface LineDraft {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
}
const EMPTY_LINE: LineDraft = { description: "", quantity: "1", unit_price: "", tax_rate: "18" };

export default function NewPurchaseOrderPage() {
  const router = useRouter();
  const vendors = useApi<Page<Vendor>>("/vendors?limit=100");
  const [vendorId, setVendorId] = useState("");
  const [poNumber, setPoNumber] = useState("");
  const [issueDate, setIssueDate] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([{ ...EMPTY_LINE }]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Preview only; the server recomputes every amount with exact decimal arithmetic.
  const preview = lines.reduce(
    (sum, l) =>
      sum +
      (Number(l.quantity) || 0) *
        (Number(l.unit_price) || 0) *
        (1 + (Number(l.tax_rate) || 0) / 100),
    0,
  );
  const update = (index: number, key: keyof LineDraft, value: string) =>
    setLines((ls) => ls.map((l, i) => (i === index ? { ...l, [key]: value } : l)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const po = await api<PurchaseOrder>("/purchase-orders", {
        json: { vendor_id: vendorId, po_number: poNumber, issue_date: issueDate || null, lines },
      });
      router.push(`/purchase-orders/${po.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="New purchase order" />
      <form onSubmit={submit} className="space-y-6">
        {error ? (
          <Alert tone="danger" title="Could not create the purchase order">
            {error}
          </Alert>
        ) : null}
        <Card title="Order">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Vendor">
              {(p) => (
                <Select
                  id={p.id}
                  required
                  value={vendorId}
                  onChange={(e) => setVendorId(e.target.value)}
                >
                  <option value="">Select a vendor</option>
                  {(vendors.data?.items ?? []).map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="PO number">
              {(p) => (
                <Input
                  id={p.id}
                  required
                  value={poNumber}
                  onChange={(e) => setPoNumber(e.target.value)}
                />
              )}
            </Field>
            <Field label="Issue date">
              {(p) => (
                <Input
                  id={p.id}
                  type="date"
                  value={issueDate}
                  onChange={(e) => setIssueDate(e.target.value)}
                />
              )}
            </Field>
          </div>
        </Card>
        <Card
          title="Lines"
          actions={
            <Button
              type="button"
              variant="secondary"
              onClick={() => setLines((ls) => [...ls, { ...EMPTY_LINE }])}
            >
              Add line
            </Button>
          }
        >
          <div className="space-y-3">
            {lines.map((line, index) => (
              <fieldset
                key={index}
                className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_1fr_auto] sm:items-end"
              >
                <legend className="sr-only">Line {index + 1}</legend>
                <Field label="Description">
                  {(p) => (
                    <Input
                      id={p.id}
                      required
                      value={line.description}
                      onChange={(e) => update(index, "description", e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Quantity">
                  {(p) => (
                    <Input
                      id={p.id}
                      required
                      inputMode="decimal"
                      value={line.quantity}
                      onChange={(e) => update(index, "quantity", e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Unit price (₹)">
                  {(p) => (
                    <Input
                      id={p.id}
                      required
                      inputMode="decimal"
                      value={line.unit_price}
                      onChange={(e) => update(index, "unit_price", e.target.value)}
                    />
                  )}
                </Field>
                <Field label="GST %">
                  {(p) => (
                    <Input
                      id={p.id}
                      required
                      inputMode="decimal"
                      value={line.tax_rate}
                      onChange={(e) => update(index, "tax_rate", e.target.value)}
                    />
                  )}
                </Field>
                <Button
                  type="button"
                  variant="ghost"
                  aria-label={`Remove line ${index + 1}`}
                  disabled={lines.length === 1}
                  onClick={() => setLines((ls) => ls.filter((_, i) => i !== index))}
                >
                  Remove
                </Button>
              </fieldset>
            ))}
          </div>
          <p className="mt-4 text-sm text-muted">
            Estimated total incl. GST: {formatMoney(preview)} (final amounts are computed by the
            server).
          </p>
        </Card>
        <Button type="submit" loading={busy}>
          Create purchase order
        </Button>
      </form>
    </>
  );
}
