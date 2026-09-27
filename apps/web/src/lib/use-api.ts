"use client";

import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

interface Result<T> {
  key: string;
  data: T | null;
  error: string | null;
}

/**
 * Loads `path` on mount and whenever it changes (`null` skips loading). Results are keyed
 * by request, so `loading` is derived instead of being set synchronously in the effect.
 * Previous data stays visible while a reload is in flight.
 */
export function useApi<T>(path: string | null): ApiState<T> {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const key = path === null ? null : `${version}:${path}`;

  useEffect(() => {
    if (path === null || key === null) return;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal })
      .then((data) => setResult({ key, data, error: null }))
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setResult((previous) => ({
            key,
            data: previous?.data ?? null,
            error: errorMessage(err),
          }));
        }
      });
    return () => controller.abort();
  }, [path, key]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const setData = useCallback(
    (data: T) => setResult((r) => ({ key: r?.key ?? "", data, error: null })),
    [],
  );
  return {
    data: result?.data ?? null,
    error: result?.key === key ? result.error : null,
    loading: key !== null && result?.key !== key,
    reload,
    setData,
  };
}
