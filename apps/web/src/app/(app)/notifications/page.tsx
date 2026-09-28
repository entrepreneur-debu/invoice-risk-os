"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Button, EmptyState, Loading, PageHeader, Pagination } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Notification, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const TONES = { info: "neutral", low: "neutral", medium: "warning", high: "danger" } as const;

function link(n: Notification): string | null {
  if (n.entity_type === "invoice" && n.entity_id) return `/invoices/${n.entity_id}`;
  if (n.entity_type === "vendor" && n.entity_id) return `/vendors/${n.entity_id}`;
  return null;
}

export default function NotificationsPage() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi<Page<Notification>>(
    `/notifications?limit=25&offset=${offset}`,
  );
  const markAll = async () => {
    await api("/notifications/read-all", { method: "POST" });
    reload();
  };
  const open = async (n: Notification) => {
    if (!n.read_at) await api(`/notifications/${n.id}/read`, { method: "POST" });
  };
  return (
    <>
      <PageHeader
        title="Notifications"
        actions={
          <Button variant="secondary" onClick={() => void markAll()}>
            Mark all as read
          </Button>
        }
      />
      {loading ? (
        <Loading />
      ) : error ? (
        <Alert tone="danger">{error}</Alert>
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="You're all caught up" />
      ) : (
        <>
          <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
            {data.items.map((n) => {
              const href = link(n);
              return (
                <li key={n.id} className={`p-4 ${n.read_at ? "" : "bg-accent/5"}`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={TONES[n.severity]}>{n.severity}</Badge>
                    {!n.read_at ? (
                      <span className="text-xs font-semibold text-accent">New</span>
                    ) : null}
                    <span className="text-xs text-muted">{formatDateTime(n.created_at)}</span>
                  </div>
                  <p className="mt-1 font-medium">
                    {href ? (
                      <Link
                        href={href}
                        onClick={() => void open(n)}
                        className="text-accent hover:underline"
                      >
                        {n.title}
                      </Link>
                    ) : (
                      n.title
                    )}
                  </p>
                  <p className="text-sm text-muted">{n.body}</p>
                </li>
              );
            })}
          </ul>
          <Pagination total={data.total} limit={25} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}
