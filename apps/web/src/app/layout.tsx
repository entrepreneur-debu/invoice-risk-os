import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Invoice Risk & Payment Control OS", template: "%s · Invoice Risk OS" },
  description: "Every invoice gets checked before your business pays it.",
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  // Dynamic rendering is required so every response carries a fresh CSP nonce.
  await connection();
  return (
    <html lang="en-IN" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
