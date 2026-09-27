"use client";

import Link from "next/link";

import { Alert, Card, Loading, PageHeader, Table, Td, Th } from "@/components/ui";
import { formatDateTime, formatMoney, humanize } from "@/lib/format";
import type { Dashboard } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function Metric({
  label,
  value,
  href,
  tone,
}: {
  label: string;
  value: string | number;
  href?: string;
  tone?: string;
}) {
  const body = (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${tone ?? ""}`}>{value}</p>
    </div>
  );
  return href ? (
    <Link href={href} className="block rounded-lg hover:ring-2 hover:ring-accent/30">
      {body}
    </Link>
  ) : (
    body
  );
}

export default function DashboardPage() {
  const { data, error, loading } = useApi<Dashboard>("/dashboard");
  if (loading) return <Loading />;
  if (error || !data)
    return (
      <Alert tone="danger" title="Dashboard unavailable">
        {error}
      </Alert>
    );
  return (
    <>
      <PageHeader title="Dashboard" description="What needs attention, and why." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric
          label="Requiring review"
          value={data.requiring_review}
          href="/invoices?status=review_required&status=pending_approval"
        />
        <Metric
          label="High-risk pending"
          value={data.high_risk_pending}
          href="/invoices?risk_level=high&status=review_required&status=pending_approval"
          tone={data.high_risk_pending > 0 ? "text-danger" : ""}
        />
        <Metric label="Potential duplicates" value={data.potential_duplicates} href="/risk" />
        <Metric label="Value awaiting decision" value={formatMoney(data.pending_value)} />
        <Metric label="Invoices received" value={data.invoices_received} href="/invoices" />
        <Metric label="Approved" value={data.approved} href="/invoices?status=approved" />
        <Metric label="Rejected" value={data.rejected} href="/invoices?status=rejected" />
        <Metric
          label="Processing / failed"
          value={`${data.processing} / ${data.failed}`}
          href="/invoices?status=failed"
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Prevented payments (measured, not estimated)">
          <p className="text-2xl font-semibold">
            {formatMoney(data.flagged_and_rejected.total_value)}
          </p>
          <p className="mt-1 text-sm text-muted">
            {data.flagged_and_rejected.count} invoice(s). {data.flagged_and_rejected.label}.
          </p>
        </Card>
        <Card title="Vendors with the most risk signals">
          {data.vendor_risk.length === 0 ? (
            <p className="text-sm text-muted">No medium or high signals yet.</p>
          ) : (
            <ul className="divide-y divide-border text-sm">
              {data.vendor_risk.map((v) => (
                <li key={v.vendor_id} className="flex justify-between py-2">
                  <Link href={`/vendors/${v.vendor_id}`} className="text-accent hover:underline">
                    {v.vendor_name}
                  </Link>
                  <span>{v.risk_signals} signal(s)</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-6">
        <Table caption="Recent activity">
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Activity</Th>
              <Th>By</Th>
            </tr>
          </thead>
          <tbody>
            {data.recent_activity.map((event, index) => (
              <tr key={`${event.occurred_at}-${index}`}>
                <Td className="whitespace-nowrap text-muted">
                  {formatDateTime(event.occurred_at)}
                </Td>
                <Td>
                  {event.entity_type === "invoice" && event.entity_id ? (
                    <Link
                      href={`/invoices/${event.entity_id}`}
                      className="text-accent hover:underline"
                    >
                      {humanize(event.action)}
                    </Link>
                  ) : (
                    humanize(event.action)
                  )}
                </Td>
                <Td className="text-muted">{event.actor ?? "System"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </>
  );
}
