import { useCallback, useState } from "react";
import { ApiError } from "./client";

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
        setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
        return undefined;
      } finally {
        setLoading(false);
      }
    },
    [fn]
  );

  return { run, loading, error, setError };
}
