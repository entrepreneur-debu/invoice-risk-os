"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";

import { PRODUCT_NAME } from "./app-shell";
import { Alert, Button, Field, Input } from "./ui";

/** Only same-site relative paths are accepted as post-login destinations (no open redirect). */
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  return raw;
}

export function AuthCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <p className="mb-6 text-center text-sm font-semibold text-muted">{PRODUCT_NAME}</p>
        <div className="rounded-lg border border-border bg-surface p-6 shadow-sm">
          <h1 className="mb-6 text-xl font-semibold">{title}</h1>
          {children}
        </div>
        {footer ? <p className="mt-4 text-center text-sm text-muted">{footer}</p> : null}
      </div>
    </main>
  );
}

export function LoginForm({ next, onSuccess }: { next: string; onSuccess?: (me: Me) => void }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const me = await api<Me>("/auth/login", { json: { email, password } });
      if (onSuccess) onSuccess(me);
      else router.replace(safeNext(next));
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "rate_limited"
          ? "Too many sign-in attempts. Please wait a few minutes and try again."
          : errorMessage(err),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error ? (
        <Alert tone="danger" title="Could not sign in">
          {error}
        </Alert>
      ) : null}
      <Field label="Work email">
        {(p) => (
          <Input
            id={p.id}
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        )}
      </Field>
      <Field label="Password">
        {(p) => (
          <Input
            id={p.id}
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        )}
      </Field>
      <Button type="submit" loading={submitting} className="w-full" disabled={!email || !password}>
        Sign in
      </Button>
    </form>
  );
}

export function SignupForm() {
  const router = useRouter();
  const [values, setValues] = useState({
    full_name: "",
    email: "",
    organization_name: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const set = (key: keyof typeof values) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (values.password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }
    setSubmitting(true);
    try {
      await api<Me>("/auth/signup", { json: values });
      router.replace("/");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error ? (
        <Alert tone="danger" title="Could not create the account">
          {error}
        </Alert>
      ) : null}
      <Field label="Your name">
        {(p) => (
          <Input
            id={p.id}
            autoComplete="name"
            required
            value={values.full_name}
            onChange={set("full_name")}
          />
        )}
      </Field>
      <Field label="Work email">
        {(p) => (
          <Input
            id={p.id}
            type="email"
            autoComplete="email"
            required
            value={values.email}
            onChange={set("email")}
          />
        )}
      </Field>
      <Field label="Organization name">
        {(p) => (
          <Input
            id={p.id}
            autoComplete="organization"
            required
            value={values.organization_name}
            onChange={set("organization_name")}
          />
        )}
      </Field>
      <Field label="Password" hint="At least 12 characters.">
        {(p) => (
          <Input
            id={p.id}
            aria-describedby={p.describedBy}
            type="password"
            autoComplete="new-password"
            required
            value={values.password}
            onChange={set("password")}
          />
        )}
      </Field>
      <Button type="submit" loading={submitting} className="w-full">
        Create organization
      </Button>
      <p className="text-xs text-muted">
        You become the organization owner. Invite reviewers and approvers from Settings.
      </p>
    </form>
  );
}

export function AuthFooterLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-accent hover:underline">
      {children}
    </Link>
  );
}
