import type { ReactNode } from "react";

export const PRODUCT_NAME = "Invoice Risk & Payment Control OS";

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:rounded focus:bg-foreground focus:px-3 focus:py-2 focus:text-background"
      >
        Skip to main content
      </a>
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-5xl items-center px-4 py-4 sm:px-6">
          <span className="text-sm font-semibold tracking-tight">{PRODUCT_NAME}</span>
        </div>
      </header>
      <main id="main-content" className="mx-auto w-full max-w-5xl flex-1 px-4 py-12 sm:px-6">
        {children}
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto max-w-5xl px-4 py-4 text-xs text-muted sm:px-6">
          Development build
        </div>
      </footer>
    </>
  );
}
