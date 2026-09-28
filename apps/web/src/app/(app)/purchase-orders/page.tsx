"use client";

import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/auth-context";
import {
  Alert,
  Badge,
  EmptyState,
  Input,
  Loading,
  PageHeader,
  Pagination,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { formatDate, formatMoney } from "@/lib/format";
import type { Page, PurchaseOrder } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function PurchaseOrdersPage() {
  const { can } = useAuth();
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useApi<Page<PurchaseOrder>>(
    `/purchase-orders?limit=25&offset=${offset}${query ? `&q=${encodeURIComponent(query)}` : ""}`,
  );
  return (
    <>
      <PageHeader
        title="Purchase orders"
        description="Invoices are matched to POs line by line using deterministic comparisons."
        actions={
          can("po.write") ? (
            <Link
              href="/purchase-orders/new"
              className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
            >
              New purchase order
            </Link>
          ) : null
        }
      />
      <label className="mb-4 block max-w-sm text-sm">
        <span className="mb-1 block text-muted">Search</span>
        <Input
          type="search"
          placeholder="PO number or vendor"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setOffset(0);
              setQuery(e.currentTarget.value);
            }
          }}
        />
      </label>
      {loading ? (
        <Loading />
      ) : error ? (
        <Alert tone="danger">{error}</Alert>
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No purchase orders" />
      ) : (
        <>
          <Table caption="Purchase orders">
            <thead>
              <tr>
                <Th>PO</Th>
                <Th>Vendor</Th>
                <Th>Issued</Th>
                <Th className="text-right">Total</Th>
                <Th className="text-right">Invoiced</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((po) => (
                <tr key={po.id}>
                  <Td>
                    <Link
                      href={`/purchase-orders/${po.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {po.po_number}
                    </Link>
                  </Td>
                  <Td>{po.vendor_name}</Td>
                  <Td>{formatDate(po.issue_date)}</Td>
                  <Td className="text-right tabular-nums">{formatMoney(po.total)}</Td>
                  <Td
                    className={`text-right tabular-nums ${Number(po.invoiced_total) > Number(po.total) ? "text-danger" : ""}`}
                  >
                    {formatMoney(po.invoiced_total)}
                  </Td>
                  <Td>
                    <Badge tone={po.status === "open" ? "info" : "neutral"}>{po.status}</Badge>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination total={data.total} limit={25} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}
