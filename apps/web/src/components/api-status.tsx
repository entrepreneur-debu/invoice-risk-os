"use client";

import { useEffect, useState } from "react";

import {
  BACKEND_STATUS_PATH,
  type BackendStatus,
  type BackendStatusResponse,
} from "@/lib/backend-status";

type DisplayStatus = BackendStatus | "checking";

const LABELS: Record<DisplayStatus, string> = {
  checking: "Checking API connection…",
  ok: "API connection healthy",
  unavailable: "API unavailable",
};

const DOT_CLASSES: Record<DisplayStatus, string> = {
  checking: "bg-neutral-400",
  ok: "bg-green-600",
  unavailable: "bg-red-600",
};

export function ApiStatus() {
  const [status, setStatus] = useState<DisplayStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch(BACKEND_STATUS_PATH, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = (await response.json()) as BackendStatusResponse;
        setStatus(body.status === "ok" ? "ok" : "unavailable");
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.warn("API status check failed", error);
          setStatus("unavailable");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <p
      role="status"
      aria-live="polite"
      className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-sm"
    >
      <span aria-hidden="true" className={`size-2 rounded-full ${DOT_CLASSES[status]}`} />
      {LABELS[status]}
    </p>
  );
}
