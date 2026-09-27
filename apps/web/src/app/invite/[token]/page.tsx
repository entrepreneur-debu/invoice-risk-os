"use client";

import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthCard } from "@/components/auth-forms";
import { Alert, Button, Field, Input, Loading } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Me, Role } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Preview {
  organization_name: string;
  email: string;
  role: Role;
  existing_user: boolean;
}

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const preview = useApi<Preview>(`/auth/invitations/${encodeURIComponent(token)}`);
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api<Me>(`/auth/invitations/${encodeURIComponent(token)}/accept`, {
        json: { full_name: fullName || null, password },
      });
      router.replace("/");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (preview.loading) return <Loading />;
  if (preview.error || !preview.data) {
    return (
      <AuthCard title="Invitation unavailable">
        <Alert tone="danger">{preview.error ?? "This invitation is invalid or has expired."}</Alert>
      </AuthCard>
    );
  }
  const invite = preview.data;
  return (
    <AuthCard title={`Join ${invite.organization_name}`}>
      <p className="mb-4 text-sm text-muted">
        You were invited as <strong className="capitalize text-foreground">{invite.role}</strong> (
        {invite.email}).
      </p>
      <form onSubmit={submit} className="space-y-4">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        {!invite.existing_user ? (
          <Field label="Your name">
            {(p) => (
              <Input
                id={p.id}
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            )}
          </Field>
        ) : null}
        <Field
          label={invite.existing_user ? "Your existing password" : "Choose a password"}
          hint={invite.existing_user ? undefined : "At least 12 characters."}
        >
          {(p) => (
            <Input
              id={p.id}
              type="password"
              required
              value={password}
              autoComplete={invite.existing_user ? "current-password" : "new-password"}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" loading={submitting} className="w-full">
          Accept invitation
        </Button>
      </form>
    </AuthCard>
  );
}
