import { useCallback, useEffect, useRef, useState } from "react";
import { stream, type StreamEvent } from "./api";
import { useWorkspace } from "./workspace";

export interface StreamState<T> {
  result: T | null;
  events: StreamEvent[];
  running: boolean;
  queued: boolean;
  error: string | null;
}

/** Runs one streamed request at a time, keeps its events, and drives the app's busy flag. */
export function useStream<T extends object>() {
  const { setBusy } = useWorkspace();
  const [state, setState] = useState<StreamState<T>>({ result: null, events: [], running: false, queued: false, error: null });
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const run = useCallback(
    async (path: string, body: unknown) => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      setState({ result: null, events: [], running: true, queued: false, error: null });
      setBusy(true);
      try {
        const result = await stream<T>(path, body, (event) => setState((s) => ({ ...s, events: [...s.events, event], queued: event.type === "queued" ? true : event.type === "stage" || event.type === "check" ? false : s.queued })), controller.signal);
        setState((s) => ({ ...s, result, running: false, queued: false }));
        return result;
      } catch (e) {
        if (controller.signal.aborted) return null;
        setState((s) => ({ ...s, running: false, queued: false, error: e instanceof Error ? e.message : String(e) }));
        return null;
      } finally {
        if (abort.current === controller) setBusy(false);
      }
    },
    [setBusy],
  );

  /** Drop any request still in flight (the server then skips it) and show `result` instead. */
  const reset = useCallback(
    (result: T | null = null) => {
      if (abort.current) {
        abort.current.abort();
        abort.current = null;
        setBusy(false);
      }
      setState({ result, events: [], running: false, queued: false, error: null });
    },
    [setBusy],
  );
  return { ...state, run, reset };
}
