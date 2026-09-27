import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { AuthProvider } from "@/components/auth-context";

export default function AuthenticatedLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <AuthProvider>
      <AppShell>{children}</AppShell>
    </AuthProvider>
  );
}
