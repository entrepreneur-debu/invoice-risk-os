"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useApi } from "@/lib/use-api";

import { useAuth } from "./auth-context";
import { Select } from "./ui";

export const PRODUCT_NAME = "Invoice Risk & Payment Control OS";

interface NavItem {
  href: string;
  label: string;
  permission?: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/invoices", label: "Invoices" },
  { href: "/approvals", label: "Approvals" },
  { href: "/vendors", label: "Vendors" },
  { href: "/purchase-orders", label: "Purchase orders" },
  { href: "/risk", label: "Risk" },
  { href: "/notifications", label: "Notifications" },
  { href: "/audit", label: "Audit log", permission: "audit.read" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { me, can, logout, switchOrganization } = useAuth();
  const unread = useApi<{ unread: number }>(
    `/notifications/unread-count?path=${encodeURIComponent(pathname)}`,
  );

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-foreground focus:px-3 focus:py-2 focus:text-background"
      >
        Skip to main content
      </a>
      <aside className="border-b border-border bg-surface md:w-60 md:shrink-0 md:border-b-0 md:border-r">
        <div className="px-4 py-4">
          <p className="text-sm font-semibold leading-tight">{PRODUCT_NAME}</p>
          <p className="mt-1 text-xs text-muted">Every invoice checked before you pay.</p>
        </div>
        <nav aria-label="Main">
          <ul className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:overflow-visible">
            {NAV.filter((item) => !item.permission || can(item.permission)).map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={isActive(item.href) ? "page" : undefined}
                  className={`flex items-center justify-between whitespace-nowrap rounded-md px-3 py-2 text-sm ${
                    isActive(item.href)
                      ? "bg-accent/10 font-medium text-accent"
                      : "hover:bg-background"
                  }`}
                >
                  {item.label}
                  {item.href === "/notifications" && unread.data && unread.data.unread > 0 ? (
                    <span className="ml-2 rounded-full bg-danger px-1.5 text-xs text-white">
                      <span className="sr-only">Unread: </span>
                      {unread.data.unread}
                    </span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-end gap-3 border-b border-border bg-surface px-4 py-2 sm:px-6">
          {me.organizations.length > 1 ? (
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted">Organization</span>
              <Select
                value={me.organization?.id}
                onChange={(event) => void switchOrganization(event.target.value)}
                className="w-auto"
              >
                {me.organizations.map((org) => (
                  <option key={org.id} value={org.id}>
                    {org.name}
                  </option>
                ))}
              </Select>
            </label>
          ) : (
            <span className="text-sm font-medium">{me.organization?.name}</span>
          )}
          <span className="text-sm text-muted">
            {me.full_name} · <span className="capitalize">{me.organization?.role}</span>
          </span>
          <button
            type="button"
            onClick={() => void logout()}
            className="text-sm text-accent hover:underline"
          >
            Sign out
          </button>
        </header>
        <main id="main-content" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}
