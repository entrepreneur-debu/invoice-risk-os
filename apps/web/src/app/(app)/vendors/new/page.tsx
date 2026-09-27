"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input, PageHeader, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Vendor } from "@/lib/types";

const EMPTY = {
  name: "",
  gstin: "",
  pan: "",
  email: "",
  phone: "",
  contact_name: "",
  address: "",
  account_holder_name: "",
  account_number: "",
  ifsc: "",
  bank_name: "",
};

export default function NewVendorPage() {
  const router = useRouter();
  const [v, setV] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setV((s) => ({ ...s, [key]: e.target.value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const orNull = (s: string) => (s.trim() ? s.trim() : null);
    try {
      const vendor = await api<Vendor>("/vendors", {
        json: {
          name: v.name,
          gstin: orNull(v.gstin),
          pan: orNull(v.pan),
          email: orNull(v.email),
          phone: orNull(v.phone),
          contact_name: orNull(v.contact_name),
          address: orNull(v.address),
          bank_account: v.account_number
            ? {
                account_holder_name: v.account_holder_name || v.name,
                account_number: v.account_number,
                ifsc: v.ifsc,
                bank_name: orNull(v.bank_name),
              }
            : null,
        },
      });
      router.push(`/vendors/${vendor.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Add vendor"
        description="GSTIN is validated (format, state code and check digit). Bank details are encrypted and must be verified by another person."
      />
      <form onSubmit={submit} className="space-y-6">
        {error ? (
          <Alert tone="danger" title="Could not save the vendor">
            {error}
          </Alert>
        ) : null}
        <Card title="Vendor details">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Legal name">
              {(p) => <Input id={p.id} required value={v.name} onChange={set("name")} />}
            </Field>
            <Field label="GSTIN" hint="15 characters, e.g. 27AAPFU0939F1ZV">
              {(p) => (
                <Input
                  id={p.id}
                  aria-describedby={p.describedBy}
                  value={v.gstin}
                  onChange={set("gstin")}
                  className="font-mono uppercase"
                />
              )}
            </Field>
            <Field label="PAN" hint="Derived from the GSTIN if left empty">
              {(p) => (
                <Input
                  id={p.id}
                  aria-describedby={p.describedBy}
                  value={v.pan}
                  onChange={set("pan")}
                  className="uppercase"
                />
              )}
            </Field>
            <Field label="Contact name">
              {(p) => <Input id={p.id} value={v.contact_name} onChange={set("contact_name")} />}
            </Field>
            <Field label="Email">
              {(p) => <Input id={p.id} type="email" value={v.email} onChange={set("email")} />}
            </Field>
            <Field label="Phone">
              {(p) => <Input id={p.id} type="tel" value={v.phone} onChange={set("phone")} />}
            </Field>
          </div>
          <div className="mt-4">
            <Field label="Address">
              {(p) => <Textarea id={p.id} rows={2} value={v.address} onChange={set("address")} />}
            </Field>
          </div>
        </Card>
        <Card title="Bank account (optional)">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Account holder name">
              {(p) => (
                <Input
                  id={p.id}
                  value={v.account_holder_name}
                  onChange={set("account_holder_name")}
                />
              )}
            </Field>
            <Field label="Account number">
              {(p) => (
                <Input
                  id={p.id}
                  inputMode="numeric"
                  autoComplete="off"
                  value={v.account_number}
                  onChange={set("account_number")}
                />
              )}
            </Field>
            <Field label="IFSC">
              {(p) => (
                <Input id={p.id} value={v.ifsc} onChange={set("ifsc")} className="uppercase" />
              )}
            </Field>
            <Field label="Bank name">
              {(p) => <Input id={p.id} value={v.bank_name} onChange={set("bank_name")} />}
            </Field>
          </div>
        </Card>
        <Button type="submit" loading={busy}>
          Save vendor
        </Button>
      </form>
    </>
  );
}
