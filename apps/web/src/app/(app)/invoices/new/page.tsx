"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Card, Field, Input, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { InvoiceDetail } from "@/lib/types";

const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";
const MAX_MB = 15;

export default function NewInvoicePage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"upload" | "url" | null>(null);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`The file is larger than ${MAX_MB} MB.`);
      return;
    }
    setError(null);
    setBusy("upload");
    try {
      const form = new FormData();
      form.append("file", file);
      const invoice = await api<InvoiceDetail>("/invoices/upload", { form });
      router.push(`/invoices/${invoice.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(null);
    }
  }

  async function importUrl(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy("url");
    try {
      const invoice = await api<InvoiceDetail>("/invoices/import-url", { json: { url } });
      router.push(`/invoices/${invoice.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Add invoice"
        description="The original document is stored, extracted and checked by the risk engine before review."
      />
      {error ? (
        <div className="mb-4">
          <Alert tone="danger" title="Could not add the invoice">
            {error}
          </Alert>
        </div>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Upload a file">
          <form onSubmit={upload} className="space-y-4">
            <Field
              label="Invoice document"
              hint={`PDF, PNG or JPEG, up to ${MAX_MB} MB. Password-protected PDFs are not accepted.`}
            >
              {(p) => (
                <Input
                  id={p.id}
                  aria-describedby={p.describedBy}
                  type="file"
                  accept={ACCEPT}
                  required
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              )}
            </Field>
            <Button type="submit" loading={busy === "upload"} disabled={!file || busy !== null}>
              Upload and analyse
            </Button>
          </form>
        </Card>
        <Card title="Import from a link">
          <form onSubmit={importUrl} className="space-y-4">
            <Field
              label="HTTPS link to the invoice"
              hint="The server downloads the file. Links to internal or private networks are blocked."
            >
              {(p) => (
                <Input
                  id={p.id}
                  aria-describedby={p.describedBy}
                  type="url"
                  inputMode="url"
                  required
                  placeholder="https://vendor.example/invoices/INV-1029.pdf"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              )}
            </Field>
            <Button
              type="submit"
              variant="secondary"
              loading={busy === "url"}
              disabled={!url || busy !== null}
            >
              Import
            </Button>
          </form>
        </Card>
      </div>
      <p className="mt-6 text-sm text-muted">
        Invoices can also be emailed to your organization&apos;s inbound address (see Settings →
        Email ingestion).
      </p>
    </>
  );
}
