import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "./api/client";

/** GETs `path` (null: nothing yet) and keeps the result; `reload` fetches it again and resolves with the data it
 * applied (undefined when the request failed or the result was obsolete). A completion applies only while its request
 * is still the latest (the path may have changed, or a newer reload started), a reload captured for an old path
 * returns without taking over the current load, and the data is exposed only while it belongs to the current path.
 * `status` keeps the failure's HTTP status (0 for a network error) so polling pages can tell a transient failure from
 * a terminal one. */
export function useLoad<T>(path: string | null) {
  const [state, setState] = useState<{ data?: T; error?: string; status?: number; path?: string; settled: number }>({ settled: 0 });
  const generation = useRef(0);
  const current = useRef<string | null>(null); // the path this hook is loading now
  const lastStatus = useRef<number | undefined>(undefined); // the latest settled HTTP status, synchronously, so request runners can stop on a terminal response before the next render
  const reload = useCallback(async (): Promise<T | undefined> => {
    if (path === null || path !== current.current) return undefined; // an obsolete callback must not take over the current load
    const ticket = ++generation.current;
    try {
      const data = await api<T>(path);
      if (ticket === generation.current) {
        lastStatus.current = undefined;
        setState((old) => ({ data, path, settled: old.settled + 1 })); // obsolete response: ignore it
        return data;
      }
    } catch (failure) {
      if (ticket === generation.current) {
        lastStatus.current = failure instanceof ApiError ? failure.status : 0;
        setState((old) => ({
          ...old,
          error: (failure as Error).message,
          status: failure instanceof ApiError ? failure.status : 0,
          settled: old.settled + 1,
        }));
      }
    }
    return undefined; // failed, or overtaken by a newer request
  }, [path]);
  useEffect(() => {
    current.current = path;
    generation.current++; // invalidate anything in flight for the old path
    lastStatus.current = undefined;
    setState({ settled: 0 });
    void reload();
    return () => {
      current.current = null; // this lifetime is over: its captured reloads must not take over the next one
      generation.current++;
    };
  }, [reload]);
  return {
    data: state.path === path ? state.data : undefined,
    error: state.error,
    status: state.status,
    settled: state.settled, // bumps on every settled request, so pollers re-arm even after an identical failure
    lastStatus,
    reload,
  };
}
