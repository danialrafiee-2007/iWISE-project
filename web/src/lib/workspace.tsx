import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { AskTurn, CheckInput, Health } from "./types";

interface Workspace {
  health: Health | null;
  offline: boolean;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  input: CheckInput;
  setInput: (input: CheckInput) => void;
  /** The conversation with the documents, kept here so a visit to another page does not lose it. */
  turns: AskTurn[];
  setTurns: (update: (turns: AskTurn[]) => AskTurn[]) => void;
  reducedMotion: boolean;
}

export const EMPTY_INPUT: CheckInput = { question: "", sources: [""], answer: "", task: "qa", profile: null, exampleId: null };

const WorkspaceContext = createContext<Workspace | null>(null);

function usePrefersReducedMotion() {
  const query = "(prefers-reduced-motion: reduce)";
  const [reduced, setReduced] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => setReduced(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState<CheckInput>(EMPTY_INPUT);
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    let timer: number | undefined;
    let stopped = false;
    const poll = async () => {
      try {
        const h = await api.health();
        if (stopped) return;
        setHealth(h);
        setOffline(false);
        if (h.state === "ready" || h.state === "failed") return;
      } catch {
        if (stopped) return;
        setOffline(true);
      }
      timer = window.setTimeout(poll, 1500);
    };
    poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, []);

  const value = useMemo(
    () => ({ health, offline, busy, setBusy, input, setInput, turns, setTurns, reducedMotion }),
    [health, offline, busy, input, turns, reducedMotion],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ws = useContext(WorkspaceContext);
  if (!ws) throw new Error("useWorkspace needs WorkspaceProvider");
  return ws;
}
