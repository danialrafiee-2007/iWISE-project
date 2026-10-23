import { useCallback, useEffect, useRef, useState } from "react";
import { stream, type StreamEvent } from "./api";
import type { Report } from "./types";
import { useWorkspace } from "./workspace";

export interface StreamState<T> {
  result: T | null;
  events: StreamEvent[];
  running: boolean;
  queued: boolean;
  error: string | null;
}

/** Runs one streamed request at a time, keeps its events, and drives the app's busy flag and the orb's mood. */
export function useStream<T extends object>() {
  const { setBusy, setMood } = useWorkspace();
  const [state, setState] = useState<StreamState<T>>({ result: null, events: [], running: false, queued: false, error: null });
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const run = useCallback(
    async (path: string, body: unknown, mood: (result: T) => Report["verdict"] | "idle" = (r) => (r as { report?: Report }).report?.verdict ?? "idle") => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setState({ result: null, events: [], running: true, queued: false, error: null });
      setBusy(true);
      setMood("thinking");
      try {
        const result = await stream<T>(path, body, (event) => setState((s) => ({ ...s, events: [...s.events, event], queued: event.type === "queued" ? true : event.type === "stage" || event.type === "check" || event.type === "progress" ? false : s.queued })), controller.signal);
        setState((s) => ({ ...s, result, running: false, queued: false }));
        setMood(mood(result));
        return result;
      } catch (e) {
        if (controller.signal.aborted) return null;
        setState((s) => ({ ...s, running: false, queued: false, error: e instanceof Error ? e.message : String(e) }));
        setMood("idle");
        return null;
      } finally {
        if (abort.current === controller) setBusy(false);
      }
    },
    [setBusy, setMood],
  );

  const reset = useCallback((result: T | null = null) => setState({ result, events: [], running: false, queued: false, error: null }), []);
  return { ...state, run, reset };
}
