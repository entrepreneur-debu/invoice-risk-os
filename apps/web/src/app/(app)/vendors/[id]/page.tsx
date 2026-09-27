"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth-context";
import { ReasonDialog } from "@/components/invoice-review";
import {
  Alert,
  Badge,
  Button,
  Card,
  Field,
  Input,
  Loading,
  PageHeader,
  Table,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatDateTime, formatMoney, humanize } from "@/lib/format";
import type { AuditEvent, BankAccount, Page, VendorDetail } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const BANK_TONES = {
  pending_verification: "danger",
  verified: "success",
  rejected: "neutral",
  superseded: "neutral",
} as const;

function BankChangeForm({ vendorId, onDone }: { vendorId: string; onDone: () => void }) {
  const [v, setV] = useState({
    account_holder_name: "",
    account_number: "",
    ifsc: "",
    bank_name: "",
    change_reason: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof v) => (e: { target: { value: string } }) =>
    setV((s) => ({ ...s, [key]: e.target.value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/vendors/${vendorId}/bank-accounts`, {
        json: { ...v, bank_name: v.bank_name || null },
      });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <Alert tone="warning" title="High-sensitivity change">
        The new account is recorded as unverified, invoices paying to it are flagged, and approvers
        are notified. Confirm the change with the vendor through a known contact, not the email that
        requested it.
      </Alert>
      {error ? <Alert tone="danger">{error}</Alert> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Account holder">
          {(p) => (
            <Input
              id={p.id}
              required
              value={v.account_holder_name}
              onChange={set("account_holder_name")}
            />
          )}
        </Field>
        <Field label="Account number">
          {(p) => (
            <Input
              id={p.id}
              required
              inputMode="numeric"
              autoComplete="off"
              value={v.account_number}
              onChange={set("account_number")}
            />
          )}
        </Field>
        <Field label="IFSC">
          {(p) => (
            <Input id={p.id} required value={v.ifsc} onChange={set("ifsc")} className="uppercase" />
          )}
        </Field>
        <Field label="Bank name">
          {(p) => <Input id={p.id} value={v.bank_name} onChange={set("bank_name")} />}
        </Field>
      </div>
      <Field label="Reason for the change">
        {(p) => (
          <Textarea
            id={p.id}
            required
            rows={2}
            value={v.change_reason}
            onChange={set("change_reason")}
          />
        )}
      </Field>
      <Button type="submit" loading={busy}>
        Record bank change
      </Button>
    </form>
  );
}

export default function VendorPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const vendor = useApi<VendorDetail>(`/vendors/${id}`);
  const accounts = useApi<BankAccount[]>(`/vendors/${id}/bank-accounts`);
  const history = useApi<Page<AuditEvent>>(
    `/audit-events?entity_type=vendor&entity_id=${id}&limit=50`,
  );
  const [changing, setChanging] = useState(false);
  const [deciding, setDeciding] = useState<{ account: BankAccount; approve: boolean } | null>(null);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    vendor.reload();
    accounts.reload();
    history.reload();
  };
  if (vendor.loading && !vendor.data) return <Loading />;
  if (vendor.error || !vendor.data) return <Alert tone="danger">{vendor.error}</Alert>;
  const v = vendor.data;

  const reveal = async (account: BankAccount) => {
    setError(null);
    try {
      const result = await api<{ account_number: string }>(
        `/vendors/${id}/bank-accounts/${account.id}/reveal`,
        { method: "POST" },
      );
      setRevealed((r) => ({ ...r, [account.id]: result.account_number }));
      history.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <>
      <PageHeader
        title={v.name}
        description={
          <>
            {v.gstin ? <span className="font-mono">{v.gstin}</span> : "No GSTIN"} · state{" "}
            {v.state_code ?? "—"} · PAN {v.pan ?? "—"}
          </>
        }
        actions={
          <Link
            href={`/invoices?vendor_id=${v.id}`}
            className="rounded-md border border-border px-3 py-2 text-sm"
          >
            View invoices
          </Link>
        }
      />
      {error ? (
        <div className="mb-4">
          <Alert tone="danger">{error}</Alert>
        </div>
      ) : null}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card>
          <p className="text-xs uppercase text-muted">Invoices</p>
          <p className="text-xl font-semibold">{v.risk.invoice_count}</p>
        </Card>
        <Card>
          <p className="text-xs uppercase text-muted">Total invoiced</p>
          <p className="text-xl font-semibold">{formatMoney(v.risk.total_invoiced)}</p>
        </Card>
        <Card>
          <p className="text-xs uppercase text-muted">Open high signals</p>
          <p className={`text-xl font-semibold ${v.risk.open_high_signals ? "text-danger" : ""}`}>
            {v.risk.open_high_signals}
          </p>
        </Card>
        <Card>
          <p className="text-xs uppercase text-muted">Signals (90 days)</p>
          <p className="text-xl font-semibold">{v.risk.signals_last_90_days}</p>
        </Card>
      </div>
      {v.risk.pending_bank_verification ? (
        <div className="mb-6">
          <Alert tone="danger" title="Bank account pending verification">
            Invoices to this vendor are flagged high-risk until an authorised person verifies the
            account.
          </Alert>
        </div>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Bank accounts (full history)"
          actions={
            can("vendor.write") && !changing ? (
              <Button variant="secondary" onClick={() => setChanging(true)}>
                Change bank account
              </Button>
            ) : null
          }
        >
          {changing ? (
            <BankChangeForm
              vendorId={v.id}
              onDone={() => {
                setChanging(false);
                reload();
              }}
            />
          ) : null}
          <ul className="mt-2 space-y-3">
            {(accounts.data ?? []).map((a) => (
              <li key={a.id} className="rounded-md border border-border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono">{revealed[a.id] ?? a.account_number_masked}</span>
                  <span>{a.ifsc}</span>
                  <Badge tone={BANK_TONES[a.status]}>{humanize(a.status)}</Badge>
                  {a.is_current ? <Badge tone="info">Current</Badge> : null}
                </div>
                <p className="mt-1 text-muted">
                  Added {formatDateTime(a.created_at)} by {a.created_by_email ?? "system"}
                  {a.change_reason ? ` · reason: “${a.change_reason}”` : ""}
                </p>
                {a.verified_at ? (
                  <p className="text-muted">
                    {a.status === "rejected" ? "Rejected" : "Verified"} by {a.verified_by_email} on{" "}
                    {formatDateTime(a.verified_at)}: “{a.verification_note}”
                  </p>
                ) : null}
                <div className="mt-2 flex flex-wrap gap-2">
                  {a.status === "pending_verification" && can("vendor.bank_verify") ? (
                    <>
                      <Button onClick={() => setDeciding({ account: a, approve: true })}>
                        Verify
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => setDeciding({ account: a, approve: false })}
                      >
                        Reject
                      </Button>
                    </>
                  ) : null}
                  {can("vendor.bank_reveal") && !revealed[a.id] ? (
                    <Button variant="ghost" onClick={() => void reveal(a)}>
                      Reveal number (audited)
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Vendor history">
          <Table caption="Vendor audit history">
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Event</Th>
                <Th>By</Th>
              </tr>
            </thead>
            <tbody>
              {(history.data?.items ?? []).map((e) => (
                <tr key={e.id}>
                  <Td className="whitespace-nowrap text-muted">{formatDate(e.occurred_at)}</Td>
                  <Td>{humanize(e.action)}</Td>
                  <Td className="text-muted">{e.actor_label}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      </div>
      {deciding ? (
        <ReasonDialog
          open
          title={deciding.approve ? "Verify bank account" : "Reject bank account"}
          submitLabel={deciding.approve ? "Verify" : "Reject"}
          variant={deciding.approve ? "primary" : "danger"}
          description="Describe how you confirmed this with the vendor (e.g. phone call to a known number)."
          onSubmit={async (note) => {
            await api(
              `/vendors/${id}/bank-accounts/${deciding.account.id}/${deciding.approve ? "verify" : "reject"}`,
              { json: { note } },
            );
            reload();
          }}
          onClose={() => setDeciding(null)}
        />
      ) : null}
    </>
  );
}
