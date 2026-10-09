import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';

/**
 * A tiny stale-while-revalidate cache.
 *
 * Every screen used to refetch from scratch on focus, and a round-trip to
 * Neon costs about a second, so switching tabs meant staring at a spinner
 * each time. Cached data is rendered immediately and refreshed in the
 * background, which is what makes navigation feel instant.
 *
 * Deliberately not react-query: one module-level Map and a version counter
 * cover this app's needs without adding a dependency and its provider.
 */
type Entry = { data: unknown; at: number };

const cache = new Map<string, Entry>();

/** How long a cached value is served without a background refresh. */
const FRESH_MS = 30_000;

/** Drop everything; used on sign-out so one account cannot see another's data. */
export function clearApiCache(): void {
  cache.clear();
}

/** Invalidate by key prefix, after a write that changes a list. */
export function invalidate(prefix: string): void {
  for (const key of [...cache.keys()]) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
}

type Options = {
  /** Cache key. Omit to disable caching for this call. */
  key?: string;
  /** Skip the automatic refetch when the screen regains focus. */
  refetchOnFocus?: boolean;
};

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: Options = {},
) {
  const { key, refetchOnFocus = true } = options;

  const cached = key ? (cache.get(key) as Entry | undefined) : undefined;
  const [data, setData] = useState<T | null>((cached?.data as T) ?? null);
  const [error, setError] = useState<string | null>(null);
  // Only the very first paint with nothing cached is a "loading" state; a
  // revalidation behind existing data must not blank the screen.
  const [loading, setLoading] = useState(!cached);
  const [refreshing, setRefreshing] = useState(false);

  // Guards against a slow response from an earlier render overwriting a
  // newer one, which shows stale data after a filter change.
  const requestId = useRef(0);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fetcher, deps);

  const load = useCallback(
    async (mode: 'initial' | 'refresh' = 'initial') => {
      const id = ++requestId.current;
      if (mode === 'refresh') setRefreshing(true);
      try {
        const next = await run();
        if (!mounted.current || id !== requestId.current) return;
        if (key) cache.set(key, { data: next, at: Date.now() });
        setData(next);
        setError(null);
      } catch (err) {
        if (!mounted.current || id !== requestId.current) return;
        setError((err as Error).message);
      } finally {
        if (mounted.current && id === requestId.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [run, key],
  );

  useEffect(() => {
    const entry = key ? cache.get(key) : undefined;
    if (entry) {
      // Paint what we have, then quietly bring it up to date if it is old.
      setData(entry.data as T);
      setLoading(false);
      if (Date.now() - entry.at > FRESH_MS) load('refresh');
    } else {
      load('initial');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const first = useRef(true);
  useFocusEffect(
    useCallback(() => {
      // The effect above already covers the first focus.
      if (first.current) {
        first.current = false;
        return;
      }
      if (refetchOnFocus) load('refresh');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [load, refetchOnFocus]),
  );

  return {
    data,
    error,
    loading,
    refreshing,
    refresh: useCallback(() => load('refresh'), [load]),
    reload: useCallback(() => load('initial'), [load]),
    setData: useCallback((next: T) => {
      if (key) cache.set(key, { data: next, at: Date.now() });
      setData(next);
    }, [key]),
  };
}
