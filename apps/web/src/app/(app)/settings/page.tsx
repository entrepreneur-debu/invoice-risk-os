"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth-context";
import { Alert, Button, Card, Field, Input, Loading, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Organization, OrganizationSettings, RiskLevel } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type NumericKey = Exclude<
  keyof OrganizationSettings,
  | "second_approval_risk_levels"
  | "ai_assistance_enabled"
  | "ai_document_extraction_enabled"
  | "email_ingestion_enabled"
>;

const NUMERIC: { key: NumericKey; label: string; hint: string }[] = [
  {
    key: "high_value_threshold",
    label: "Second approval above (₹)",
    hint: "Invoices at or above this total need a second, different approver.",
  },
  {
    key: "require_po_above",
    label: "PO required above (₹)",
    hint: "Leave empty to never require a purchase order.",
  },
  {
    key: "price_tolerance_percent",
    label: "Price tolerance (%)",
    hint: "Allowed unit-price difference against the PO.",
  },
  {
    key: "quantity_tolerance_percent",
    label: "Quantity tolerance (%)",
    hint: "Allowed over-delivery against the PO.",
  },
  {
    key: "amount_tolerance_absolute",
    label: "Rounding tolerance (₹)",
    hint: "Absolute tolerance for totals and GST arithmetic.",
  },
  { key: "duplicate_window_days", label: "Duplicate look-back (days)", hint: "" },
  { key: "unusual_amount_multiplier", label: "Unusual amount (× vendor median)", hint: "" },
  { key: "price_increase_alert_percent", label: "Price increase alert (%)", hint: "" },
  { key: "split_invoice_window_days", label: "Invoice splitting window (days)", hint: "" },
  { key: "new_vendor_days", label: "New vendor period (days)", hint: "" },
  { key: "bank_change_alert_days", label: "Bank change alert window (days)", hint: "" },
];

export default function SettingsPage() {
  const org = useApi<Organization>("/organization");
  if (org.loading && !org.data) return <Loading />;
  if (org.error || !org.data) return <Alert tone="danger">{org.error}</Alert>;
  return <SettingsForm initial={org.data} onSaved={org.setData} reload={org.reload} />;
}

interface IngestionToken {
  inbound_email_address: string;
  ingestion_token: string;
}

function SettingsForm({
  initial,
  onSaved,
  reload,
}: {
  initial: Organization;
  onSaved: (org: Organization) => void;
  reload: () => void;
}) {
  const { can } = useAuth();
  const [name, setName] = useState(initial.name);
  const [gstin, setGstin] = useState(initial.gstin ?? "");
  const [settings, setSettings] = useState<OrganizationSettings>(initial.settings);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [ingestion, setIngestion] = useState<IngestionToken | null>(null);
  const editable = can("org.manage_settings");
  const org = { data: initial };

  const setValue = (key: keyof OrganizationSettings, value: unknown) =>
    setSettings((s) => ({ ...s, [key]: value }));
  const toggleLevel = (level: RiskLevel) => {
    const levels = new Set(settings.second_approval_risk_levels);
    if (levels.has(level)) levels.delete(level);
    else levels.add(level);
    setValue("second_approval_risk_levels", [...levels]);
  };

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const normalized = {
        ...settings,
        require_po_above: settings.require_po_above === "" ? null : settings.require_po_above,
      };
      onSaved(
        await api<Organization>("/organization", {
          method: "PATCH",
          json: { name, gstin: gstin || null, settings: normalized },
        }),
      );
      setMessage({
        tone: "success",
        text: "Settings saved. Changes are recorded in the audit log.",
      });
    } catch (err) {
      setMessage({ tone: "danger", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  const rotateToken = async () => {
    try {
      setIngestion(await api("/organization/email-ingestion/token", { method: "POST" }));
      reload();
    } catch (err) {
      setMessage({ tone: "danger", text: errorMessage(err) });
    }
  };

  return (
    <>
      <PageHeader
        title="Settings"
        description="Organization controls. Only owners and admins can change them."
        actions={
          can("members.read") ? (
            <Link
              href="/settings/members"
              className="rounded-md border border-border px-3 py-2 text-sm"
            >
              Members and roles
            </Link>
          ) : null
        }
      />
      <form onSubmit={save} className="space-y-6">
        {message ? <Alert tone={message.tone}>{message.text}</Alert> : null}
        <fieldset disabled={!editable} className="space-y-6">
          <Card title="Organization">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name">
                {(p) => <Input id={p.id} value={name} onChange={(e) => setName(e.target.value)} />}
              </Field>
              <Field
                label="Your GSTIN"
                hint="Used to check the buyer GSTIN and CGST/SGST vs IGST on invoices."
              >
                {(p) => (
                  <Input
                    id={p.id}
                    aria-describedby={p.describedBy}
                    className="font-mono uppercase"
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value)}
                  />
                )}
              </Field>
            </div>
          </Card>
          <Card title="Approval policy and risk rules">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {NUMERIC.map(({ key, label, hint }) => (
                <Field key={key} label={label} hint={hint || undefined}>
                  {(p) => (
                    <Input
                      id={p.id}
                      aria-describedby={p.describedBy}
                      inputMode="decimal"
                      value={String(settings[key] ?? "")}
                      onChange={(e) => setValue(key, e.target.value)}
                    />
                  )}
                </Field>
              ))}
            </div>
            <fieldset className="mt-4">
              <legend className="text-sm font-medium">
                Risk levels that require a second approver
              </legend>
              <div className="mt-2 flex gap-4 text-sm">
                {(["high", "medium", "low"] as RiskLevel[]).map((level) => (
                  <label key={level} className="flex items-center gap-2 capitalize">
                    <input
                      type="checkbox"
                      checked={settings.second_approval_risk_levels.includes(level)}
                      onChange={() => toggleLevel(level)}
                    />
                    {level}
                  </label>
                ))}
              </div>
            </fieldset>
          </Card>
          <Card title="AI assistance (Gemini)">
            <p className="mb-3 text-sm text-muted">
              AI assists reviewers; it never approves, rejects, calculates amounts or decides
              duplicates. Turning these off keeps every deterministic check.
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.ai_document_extraction_enabled}
                onChange={(e) => setValue("ai_document_extraction_enabled", e.target.checked)}
              />
              Send invoice documents to the AI provider for data extraction
            </label>
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.ai_assistance_enabled}
                onChange={(e) => setValue("ai_assistance_enabled", e.target.checked)}
              />
              Generate AI explanations of risk evidence for reviewers
            </label>
          </Card>
          <Card title="Email ingestion">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={settings.email_ingestion_enabled}
                onChange={(e) => setValue("email_ingestion_enabled", e.target.checked)}
              />
              Accept invoices sent to the inbound address
            </label>
            <p className="mt-2 text-sm">
              Inbound address: <span className="font-mono">{org.data.inbound_email_address}</span>
            </p>
            <p className="mt-1 text-xs text-muted">
              Your mail provider forwards raw messages to{" "}
              <span className="font-mono">POST /api/v1/email-ingestion/inbound</span> with the
              ingestion token.
            </p>
            {can("email_ingestion.manage") ? (
              <Button
                type="button"
                variant="secondary"
                className="mt-3"
                onClick={() => void rotateToken()}
              >
                {org.data.email_ingestion_configured
                  ? "Rotate ingestion token"
                  : "Create ingestion token"}
              </Button>
            ) : null}
            {ingestion ? (
              <Alert tone="warning" title="Copy this token now; it will not be shown again">
                <code className="break-all">{ingestion.ingestion_token}</code>
              </Alert>
            ) : null}
          </Card>
        </fieldset>
        {editable ? (
          <Button type="submit" loading={busy}>
            Save settings
          </Button>
        ) : (
          <p className="text-sm text-muted">You can view but not change these settings.</p>
        )}
      </form>
    </>
  );
}
