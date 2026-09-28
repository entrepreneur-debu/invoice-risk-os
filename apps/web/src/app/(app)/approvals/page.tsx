"use client";

import Link from "next/link";
import { useState } from "react";

import { RiskBadge, StatusBadge } from "@/components/badges";
import { Alert, EmptyState, Loading, PageHeader, Pagination, Table, Td, Th } from "@/components/ui";
import { formatDateTime, formatMoney } from "@/lib/format";
import type { InvoiceSummary, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function ApprovalsPage() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useApi<Page<InvoiceSummary>>(
    `/approvals?limit=25&offset=${offset}`,
  );
  return (
    <>
      <PageHeader
        title="Approvals"
        description="Invoices waiting for a decision you are allowed to make, oldest first."
      />
      {loading ? (
        <Loading />
      ) : error ? (
        <Alert tone="danger">{error}</Alert>
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="Nothing waiting for you">
          New invoices appear here after risk analysis.
        </EmptyState>
      ) : (
        <>
          <Table caption="Invoices awaiting your decision">
            <thead>
              <tr>
                <Th>Invoice</Th>
                <Th>Vendor</Th>
                <Th className="text-right">Total</Th>
                <Th>Status</Th>
                <Th>Risk</Th>
                <Th>Received</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((inv) => (
                <tr key={inv.id}>
                  <Td>
                    <Link
                      href={`/invoices/${inv.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {inv.invoice_number ?? "Unnumbered"}
                    </Link>
                  </Td>
                  <Td>{inv.vendor_name ?? "Unknown vendor"}</Td>
                  <Td className="text-right tabular-nums">{formatMoney(inv.total)}</Td>
                  <Td>
                    <StatusBadge status={inv.status} />
                  </Td>
                  <Td>
                    <RiskBadge level={inv.risk_level} score={inv.risk_score} />
                  </Td>
                  <Td className="text-muted">{formatDateTime(inv.created_at)}</Td>
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
