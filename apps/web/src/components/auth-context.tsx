"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";

import { Loading } from "./ui";

interface AuthValue {
  me: Me;
  /** UI hint only. Every permission is enforced again by the API. */
  can: (permission: string) => boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Me>("/auth/me")
      .then((result) => {
        if (!cancelled) setMe(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(errorMessage(err));
        router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const refresh = useCallback(async () => {
    setMe(await api<Me>("/auth/me"));
  }, []);

  const value = useMemo<AuthValue | null>(() => {
    if (!me) return null;
    return {
      me,
      can: (permission) => me.permissions.includes(permission),
      refresh,
      logout: async () => {
        await api("/auth/logout", { method: "POST" }).catch(() => undefined);
        router.replace("/login");
      },
      switchOrganization: async (organizationId) => {
        setMe(
          await api<Me>("/auth/switch-organization", { json: { organization_id: organizationId } }),
        );
        router.push("/");
      },
    };
  }, [me, refresh, router]);

  if (!value) return <Loading label={error ?? "Loading your workspace…"} />;
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
