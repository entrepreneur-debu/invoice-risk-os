"use client";

import { useState } from "react";

import { Alert, Card, Loading, PageHeader, Select, Table, Td, Th } from "@/components/ui";
import { formatDate, formatMoney, humanize } from "@/lib/format";
import type { Analytics } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function Bars({ rows, label }: { rows: { name: string; value: number }[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  if (rows.length === 0) return <p className="text-sm text-muted">No data in this period.</p>;
  return (
    <figure>
      <figcaption className="sr-only">{label}</figcaption>
      <ul className="space-y-2 text-sm">
        {rows.map((row) => (
          <li key={row.name}>
            <div className="flex justify-between">
              <span>{row.name}</span>
              <span className="tabular-nums">{row.value}</span>
            </div>
            <div className="mt-1 h-2 rounded bg-background" aria-hidden="true">
              <div
                className="h-2 rounded bg-accent"
                style={{ width: `${(row.value / max) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export default function RiskPage() {
  const [days, setDays] = useState(90);
  const { data, error, loading } = useApi<Analytics>(`/analytics?days=${days}`);
  return (
    <>
      <PageHeader
        title="Risk and analytics"
        description="Computed from your invoices and review decisions; nothing is estimated."
        actions={
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">Period</span>
            <Select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-auto"
            >
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last 12 months</option>
            </Select>
          </label>
        }
      />
      {loading ? (
        <Loading />
      ) : error || !data ? (
        <Alert tone="danger">{error}</Alert>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Key figures">
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted">Duplicate signals</dt>
                <dd className="text-xl font-semibold">{data.duplicate_detections}</dd>
              </div>
              <div>
                <dt className="text-muted">PO mismatch signals</dt>
                <dd className="text-xl font-semibold">{data.po_mismatch_signals}</dd>
              </div>
              <div>
                <dt className="text-muted">Approved / rejected</dt>
                <dd className="text-xl font-semibold">
                  {data.decisions.approved ?? 0} / {data.decisions.rejected ?? 0}
                </dd>
              </div>
              <div>
                <dt className="text-muted">Signals overridden</dt>
                <dd className="text-xl font-semibold">{data.signals_resolved_by_override}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted">Review turnaround (request → decision)</dt>
                <dd>
                  {data.review_turnaround_hours.decided_invoices === 0
                    ? "No decisions yet"
                    : `median ${data.review_turnaround_hours.median} h · average ${data.review_turnaround_hours.average} h · ${data.review_turnaround_hours.decided_invoices} decided`}
                </dd>
              </div>
            </dl>
          </Card>
          <Card title="Risk levels of analysed invoices">
            <Bars
              label="Risk levels"
              rows={["high", "medium", "low", "none"].map((k) => ({
                name: humanize(k),
                value: data.risk_level_distribution[k] ?? 0,
              }))}
            />
          </Card>
          <Card title="Signals by category">
            <Bars
              label="Signals by category"
              rows={data.risk_categories.map((c) => ({
                name: humanize(c.category),
                value: c.count,
              }))}
            />
          </Card>
          <Card title="Most frequent rules">
            <Bars
              label="Most frequent rules"
              rows={data.top_rules.map((r) => ({ name: humanize(r.rule_code), value: r.count }))}
            />
          </Card>
          <Card title="Vendors with anomalies">
            <Bars
              label="Vendors with anomalies"
              rows={data.vendor_anomalies.map((v) => ({ name: v.vendor_name, value: v.signals }))}
            />
          </Card>
          <Table caption="Weekly invoice volume">
            <thead>
              <tr>
                <Th>Week of</Th>
                <Th className="text-right">Invoices</Th>
                <Th className="text-right">Value</Th>
              </tr>
            </thead>
            <tbody>
              {data.invoice_volume.map((w) => (
                <tr key={w.week_start}>
                  <Td>{formatDate(w.week_start)}</Td>
                  <Td className="text-right tabular-nums">{w.count}</Td>
                  <Td className="text-right tabular-nums">{formatMoney(w.total_value)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </>
  );
}
