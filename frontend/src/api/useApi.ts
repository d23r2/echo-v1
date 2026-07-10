import { useCallback, useState } from "react";

export function useApi<T extends (...args: any[]) => Promise<any>>(fn: T) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (...args: Parameters<T>): Promise<Awaited<ReturnType<T>> | undefined> => {
      setLoading(true);
      setError(null);
      try {
        return await fn(...args);
      } catch (err) {
        // Surface whatever we actually got — ApiError/NetworkError messages
        // are already descriptive (status+body, or the failing URL+cause).
        // Fall back to String(err) rather than a generic message so nothing
        // is ever silently swallowed here.
        console.error("[useApi] request failed", err);
        setError(err instanceof Error ? err.message : String(err));
        return undefined;
      } finally {
        setLoading(false);
      }
    },
    [fn]
  );

  return { run, loading, error, setError };
}
