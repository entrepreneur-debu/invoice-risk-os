"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AuthCard, AuthFooterLink, LoginForm } from "@/components/auth-forms";

function Login() {
  const params = useSearchParams();
  return (
    <AuthCard
      title="Sign in"
      footer={
        <>
          New here? <AuthFooterLink href="/signup">Create an organization</AuthFooterLink>
        </>
      }
    >
      <LoginForm next={params.get("next") ?? "/"} />
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}
