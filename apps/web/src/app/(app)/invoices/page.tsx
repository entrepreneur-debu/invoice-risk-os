"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useAuth } from "@/components/auth-context";
import { RiskBadge, StatusBadge } from "@/components/badges";
import {
  Alert,
  EmptyState,
  Input,
  Loading,
  PageHeader,
  Pagination,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { formatDate, formatMoney, STATUS_LABELS } from "@/lib/format";
import type { InvoiceStatus, InvoiceSummary, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const LIMIT = 25;

function InvoiceList() {
  const { can } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const offset = Number(params.get("offset") ?? 0);
  const query = new URLSearchParams(params);
  query.set("limit", String(LIMIT));
  const { data, error, loading } = useApi<Page<InvoiceSummary>>(`/invoices?${query.toString()}`);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      next.delete(key);
      if (value) next.set(key, value);
    }
    if (!("offset" in changes)) next.delete("offset");
    router.replace(`${pathname}?${next.toString()}`);
  };

  return (
    <>
      <PageHeader
        title="Invoices"
        description="Every invoice is checked before payment. Open one to review its evidence."
        actions={
          can("invoice.upload") ? (
            <Link
              href="/invoices/new"
              className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
            >
              Add invoice
            </Link>
          ) : null
        }
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <label className="text-sm">
          <span className="mb-1 block text-muted">Search</span>
          <Input
            type="search"
            placeholder="Invoice number or vendor"
            defaultValue={params.get("q") ?? ""}
            onKeyDown={(e) => {
              if (e.key === "Enter") update({ q: e.currentTarget.value || null });
            }}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Status</span>
          <Select
            value={params.get("status") ?? ""}
            onChange={(e) => update({ status: e.target.value || null })}
          >
            <option value="">All statuses</option>
            {(Object.keys(STATUS_LABELS) as InvoiceStatus[]).map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </Select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-muted">Risk</span>
          <Select
            value={params.get("risk_level") ?? ""}
            onChange={(e) => update({ risk_level: e.target.value || null })}
          >
            <option value="">Any risk</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="none">No signals</option>
          </Select>
        </label>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <Alert tone="danger">{error}</Alert>
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No invoices match">Upload an invoice or change the filters.</EmptyState>
      ) : (
        <>
          <Table caption="Invoices">
            <thead>
              <tr>
                <Th>Invoice</Th>
                <Th>Vendor</Th>
                <Th>Date</Th>
                <Th className="text-right">Total</Th>
                <Th>Status</Th>
                <Th>Risk</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((inv) => (
                <tr key={inv.id} className="hover:bg-background">
                  <Td>
                    <Link
                      href={`/invoices/${inv.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {inv.invoice_number ?? "Unnumbered invoice"}
                    </Link>
                    <div className="text-xs text-muted">via {inv.source.replace("_", " ")}</div>
                  </Td>
                  <Td>{inv.vendor_name ?? <span className="text-muted">Unknown vendor</span>}</Td>
                  <Td className="whitespace-nowrap">{formatDate(inv.invoice_date)}</Td>
                  <Td className="whitespace-nowrap text-right tabular-nums">
                    {formatMoney(inv.total, inv.currency ?? "INR")}
                  </Td>
                  <Td>
                    <StatusBadge status={inv.status} />
                  </Td>
                  <Td>
                    <RiskBadge level={inv.risk_level} score={inv.risk_score} />
                    {inv.open_high_signals > 0 ? (
                      <div className="mt-1 text-xs text-danger">
                        {inv.open_high_signals} open high signal(s)
                      </div>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination
            total={data.total}
            limit={LIMIT}
            offset={offset}
            onChange={(o) => update({ offset: String(o) })}
          />
        </>
      )}
    </>
  );
}

export default function InvoicesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <InvoiceList />
    </Suspense>
  );
}
