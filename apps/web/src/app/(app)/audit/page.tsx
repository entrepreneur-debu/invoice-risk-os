"use client";

import { useState } from "react";

import {
  Alert,
  Button,
  Input,
  Loading,
  PageHeader,
  Pagination,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";
import type { AuditEvent, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Verification {
  valid: boolean;
  events_checked: number;
  first_invalid_sequence: number | null;
  reason: string | null;
}

export default function AuditPage() {
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const { data, error, loading } = useApi<Page<AuditEvent>>(
    `/audit-events?limit=50&offset=${offset}${query ? `&q=${encodeURIComponent(query)}` : ""}`,
  );
  const [verification, setVerification] = useState<Verification | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const verify = async () => {
    setVerifyError(null);
    try {
      setVerification(await api<Verification>("/audit-events/verify"));
    } catch (err) {
      setVerifyError(errorMessage(err));
    }
  };

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Append-only and hash-chained. Entries cannot be edited or deleted through the application."
        actions={
          <Button variant="secondary" onClick={() => void verify()}>
            Verify integrity
          </Button>
        }
      />
      {verification ? (
        <div className="mb-4">
          <Alert
            tone={verification.valid ? "success" : "danger"}
            title={verification.valid ? "Audit chain intact" : "Audit chain broken"}
          >
            {verification.valid
              ? `${verification.events_checked} events verified.`
              : `Problem at event #${verification.first_invalid_sequence}: ${humanize(verification.reason)}.`}
          </Alert>
        </div>
      ) : null}
      {verifyError ? (
        <div className="mb-4">
          <Alert tone="danger">{verifyError}</Alert>
        </div>
      ) : null}
      <label className="mb-4 block max-w-sm text-sm">
        <span className="mb-1 block text-muted">Filter by action or person</span>
        <Input
          type="search"
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
      ) : error || !data ? (
        <Alert tone="danger">{error}</Alert>
      ) : (
        <>
          <Table caption="Audit events">
            <thead>
              <tr>
                <Th>#</Th>
                <Th>When</Th>
                <Th>Action</Th>
                <Th>Actor</Th>
                <Th>Entity</Th>
                <Th>Details</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((e) => (
                <tr key={e.id}>
                  <Td className="tabular-nums text-muted">{e.sequence}</Td>
                  <Td className="whitespace-nowrap">{formatDateTime(e.occurred_at)}</Td>
                  <Td>{humanize(e.action)}</Td>
                  <Td>
                    {e.actor_label ?? e.actor_type}
                    {e.ip_address ? <div className="text-xs text-muted">{e.ip_address}</div> : null}
                  </Td>
                  <Td className="text-xs">
                    {e.entity_type} {e.entity_id?.slice(0, 8)}
                  </Td>
                  <Td>
                    <button
                      type="button"
                      className="text-xs text-accent hover:underline"
                      aria-expanded={expanded === e.id}
                      onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                    >
                      {expanded === e.id ? "Hide" : "Show"}
                    </button>
                    {expanded === e.id ? (
                      <pre className="mt-2 max-w-md overflow-x-auto whitespace-pre-wrap text-xs">
                        {JSON.stringify(e.details, null, 2)}
                      </pre>
                    ) : null}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination total={data.total} limit={50} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}
