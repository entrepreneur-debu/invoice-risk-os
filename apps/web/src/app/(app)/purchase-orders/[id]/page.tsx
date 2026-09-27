"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { useAuth } from "@/components/auth-context";
import { Alert, Badge, Button, Card, Loading, PageHeader, Table, Td, Th } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/format";
import type { PurchaseOrder } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function PurchaseOrderPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { data: po, error, loading, reload } = useApi<PurchaseOrder>(`/purchase-orders/${id}`);
  if (loading && !po) return <Loading />;
  if (error || !po) return <Alert tone="danger">{error}</Alert>;
  const setStatus = async (status: string) => {
    await api(`/purchase-orders/${po.id}`, { method: "PATCH", json: { status } });
    reload();
  };
  return (
    <>
      <PageHeader
        title={`PO ${po.po_number}`}
        description={
          <>
            {po.vendor_name} · issued {formatDate(po.issue_date)}
          </>
        }
        actions={
          can("po.write") && po.status === "open" ? (
            <Button variant="secondary" onClick={() => void setStatus("closed")}>
              Close PO
            </Button>
          ) : null
        }
      />
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card>
          <p className="text-xs uppercase text-muted">Status</p>
          <Badge tone={po.status === "open" ? "info" : "neutral"}>{po.status}</Badge>
        </Card>
        <Card>
          <p className="text-xs uppercase text-muted">PO total</p>
          <p className="text-xl font-semibold">{formatMoney(po.total)}</p>
        </Card>
        <Card>
          <p className="text-xs uppercase text-muted">Invoiced to date</p>
          <p className="text-xl font-semibold">{formatMoney(po.invoiced_total)}</p>
        </Card>
        <Card>
          <p className="text-xs uppercase text-muted">Remaining</p>
          <p className="text-xl font-semibold">
            {formatMoney(Number(po.total) - Number(po.invoiced_total))}
          </p>
        </Card>
      </div>
      <Table caption="Purchase order lines">
        <thead>
          <tr>
            <Th>#</Th>
            <Th>Description</Th>
            <Th className="text-right">Ordered</Th>
            <Th className="text-right">Invoiced</Th>
            <Th className="text-right">Unit price</Th>
            <Th className="text-right">GST %</Th>
            <Th className="text-right">Amount</Th>
          </tr>
        </thead>
        <tbody>
          {po.lines.map((l) => (
            <tr key={l.id}>
              <Td>{l.line_no}</Td>
              <Td>{l.description}</Td>
              <Td className="text-right tabular-nums">{l.quantity}</Td>
              <Td
                className={`text-right tabular-nums ${Number(l.invoiced_quantity) > Number(l.quantity) ? "text-danger" : ""}`}
              >
                {l.invoiced_quantity}
              </Td>
              <Td className="text-right tabular-nums">{formatMoney(l.unit_price)}</Td>
              <Td className="text-right tabular-nums">{l.tax_rate}</Td>
              <Td className="text-right tabular-nums">{formatMoney(l.amount)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {po.linked_invoice_ids.length > 0 ? (
        <Card title="Linked invoices" className="mt-6">
          <ul className="list-disc pl-5 text-sm">
            {po.linked_invoice_ids.map((invoiceId) => (
              <li key={invoiceId}>
                <Link href={`/invoices/${invoiceId}`} className="text-accent hover:underline">
                  {invoiceId.slice(0, 8)}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
