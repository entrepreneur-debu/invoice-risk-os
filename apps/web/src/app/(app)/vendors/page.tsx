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
import type { Page, Vendor } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function VendorsPage() {
  const { can } = useAuth();
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useApi<Page<Vendor>>(
    `/vendors?limit=25&offset=${offset}${query ? `&q=${encodeURIComponent(query)}` : ""}`,
  );
  return (
    <>
      <PageHeader
        title="Vendors"
        description="The vendor master: identity, GSTIN and verified payment details."
        actions={
          can("vendor.write") ? (
            <Link
              href="/vendors/new"
              className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground"
            >
              Add vendor
            </Link>
          ) : null
        }
      />
      <label className="mb-4 block max-w-sm text-sm">
        <span className="mb-1 block text-muted">Search vendors</span>
        <Input
          type="search"
          placeholder="Name or GSTIN"
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
        <EmptyState title="No vendors found" />
      ) : (
        <>
          <Table caption="Vendors">
            <thead>
              <tr>
                <Th>Vendor</Th>
                <Th>GSTIN</Th>
                <Th>Bank account</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((v) => (
                <tr key={v.id}>
                  <Td>
                    <Link
                      href={`/vendors/${v.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {v.name}
                    </Link>
                  </Td>
                  <Td className="font-mono text-xs">{v.gstin ?? "—"}</Td>
                  <Td>
                    {v.current_bank_account ? (
                      <span className="flex items-center gap-2">
                        {v.current_bank_account.account_number_masked}
                        {v.current_bank_account.status === "pending_verification" ? (
                          <Badge tone="danger">Unverified</Badge>
                        ) : (
                          <Badge tone="success">Verified</Badge>
                        )}
                      </span>
                    ) : (
                      <span className="text-muted">None on file</span>
                    )}
                  </Td>
                  <Td>
                    <Badge tone={v.status === "active" ? "neutral" : "warning"}>{v.status}</Badge>
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
