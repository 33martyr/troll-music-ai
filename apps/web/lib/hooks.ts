"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage } from "./api";

interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Load data on mount and whenever `key` changes. `reload()` refetches. */
export function useLoad<T>(load: () => Promise<T>, key: string = ""): Loaded<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; key: string | null }>({
    data: null,
    error: null,
    key: null,
  });
  const [tick, setTick] = useState(0);
  const requestKey = `${key}#${tick}`;

  useEffect(() => {
    let alive = true;
    load().then(
      (data) => alive && setState({ data, error: null, key: requestKey }),
      (error) => alive && setState((s) => ({ data: s.data, error: errorMessage(error), key: requestKey })),
    );
    return () => {
      alive = false;
    };
    // `load` is intentionally not a dependency: callers pass inline closures.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data: state.data, error: state.error, loading: state.key !== requestKey, reload };
}

export function formatWhen(iso: string): string {
  const then = new Date(iso);
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export const humanize = (value: string) =>
  value.replace(/[_-]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
