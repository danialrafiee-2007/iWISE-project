import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "../lib/router";

// A guided tour for judges and first-time users: it opens each tool on a ready-made example, dims the page around the
// part that matters and explains it. Autoplay advances by itself, for a hands-free demo or a screen recording. The
// page stays usable underneath; only the explanation card takes clicks.

interface Step {
  url: string;
  target?: string;
  title: string;
  body: string;
  seconds?: number;
}

const STEPS: Step[] = [
  {
    url: "/",
    title: "Welcome to Truth Guardian",
    body: "It checks an AI answer against the sources it was given, claim by claim, explains every flag and fixes what it can, entirely on this computer. This tour takes about three minutes. Use the arrow keys or the buttons; Esc leaves.",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "answer",
    title: "Every claim, checked",
    body: "The answer is split into claims. The underline colour is the verdict, and the highlighted words are exactly what the sources do not support: here, the year.",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "claim",
    title: "Why, and how to fix it",
    body: "Each flag comes with the closest source sentence, a plain-language reason and, when a source has the right value, a fix taken from it.",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "verdict",
    title: "A grade, a guarantee, a lane",
    body: "The risk is calibrated, so it reads as a probability. The conformal guarantee bounds how many hallucinations slip past the line, and the triage lane says whether the answer can go out, needs a person, or should be blocked.",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "blame",
    title: "Who is to blame",
    body: "Retrieval or the language model? Here the sources do answer the question, so the fault lies with the generator. When the sources miss the question, retrieval is blamed instead.",
  },
  {
    url: "/analyze?example=library",
    target: "conflicts",
    title: "When the sources disagree",
    body: "Two sources give different years. The claim is marked contested rather than hallucinated: the answer did not invent it, but someone has to check which source is right.",
  },
  {
    url: "/heal?example=anne-frank",
    target: "heal-rounds",
    title: "Heal, then check again",
    body: "Fixes are applied round by round and the whole answer is checked again after each one. Every change says why, and the risk is shown for every round.",
    seconds: 10,
  },
  {
    url: "/fool",
    target: "tricks",
    title: "Try to fool it",
    body: "Pick a trick, apply it to a grounded answer and see whether the guardian finds the exact words. Each card shows how often that trick is caught on the test suite, weak ones included.",
  },
  {
    url: "/agent?example=agent-liberation",
    target: "agent-timeline",
    title: "Stop an agent in time",
    body: "Steps arrive one by one, each checked only against what came before it. When the agent states a fact no tool returned, the guardian stops the run before the answer reaches anyone.",
    seconds: 12,
  },
  {
    url: "/model",
    target: "headline",
    title: "Measured, limits included",
    body: "Every number on this page is read from the evaluation files: accuracy against baselines, data the model never saw, the guarantees, and the limits we found.",
  },
  {
    url: "/analyze",
    target: "upload",
    title: "Your turn",
    body: "Drop a PDF or Word document as a source, paste an answer and check it. Nothing leaves this computer.",
  },
];

const DEFAULT_SECONDS = 8;
const PAD = 10;
const HEADER = 96;

const TourContext = createContext<{ start: (autoplay?: boolean) => void; active: boolean }>({ start: () => {}, active: false });
export const useTour = () => useContext(TourContext);

function findTarget(name?: string): HTMLElement | null {
  if (!name) return null;
  const all = [...document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`)];
  return all.find((el) => el.offsetParent !== null || el.getClientRects().length > 0) ?? null;
}

export function TourProvider({ children }: { children: ReactNode }) {
  const { navigate, search } = useRouter();
  const [index, setIndex] = useState<number | null>(null);
  const [autoplay, setAutoplay] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [found, setFound] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const lastUrl = useRef<string | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const step = index === null ? null : STEPS[index];

  const start = useCallback((play = false) => {
    lastUrl.current = null;
    setAutoplay(play);
    setIndex(0);
  }, []);
  const stop = useCallback(() => {
    setIndex(null);
    setAutoplay(false);
  }, []);
  const go = useCallback((delta: number) => setIndex((i) => (i === null ? null : i + delta >= STEPS.length ? null : Math.max(0, i + delta))), []);

  useEffect(() => {
    const mode = new URLSearchParams(search).get("tour");
    if (mode) start(mode === "play");
  }, []);

  // Enter a step: open its page (only when the page or the example changes), then wait for its target.
  useEffect(() => {
    if (!step) return;
    if (step.url !== lastUrl.current) {
      lastUrl.current = step.url;
      navigate(step.url);
    }
    setFound(false);
    setRect(null);
    setElapsed(0);
    card.current?.focus();
    let raf = 0;
    let scrolled = false;
    let last = "";
    const track = () => {
      const el = findTarget(step.target);
      if (el) {
        if (!scrolled) {
          // Bring the target near the top when it and the card fit one under the other; else centre it.
          scrolled = true;
          const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
          const r = el.getBoundingClientRect();
          const room = r.height + (card.current?.offsetHeight ?? 220) + PAD * 2 + HEADER + 40;
          if (room <= window.innerHeight) window.scrollBy({ top: r.top - HEADER - PAD, behavior });
          else el.scrollIntoView({ block: "center", behavior });
        }
        const r = el.getBoundingClientRect();
        const key = [r.top, r.left, r.width, r.height].map(Math.round).join(",");
        if (key !== last) {
          last = key;
          setRect(r);
        }
        setFound(true);
      } else if (step.target && last) {
        last = "";
        setRect(null);
      }
    };
    // Every frame while visible; the interval keeps the tour moving when the window is in the background (no frames).
    const frame = () => {
      track();
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    const timer = window.setInterval(track, 400);
    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(timer);
    };
  }, [index]);

  // Autoplay: count only once the step's target is on screen, so slow steps (healing, the agent) get their time.
  useEffect(() => {
    if (!step || !autoplay || (step.target && !found)) return;
    const seconds = step.seconds ?? DEFAULT_SECONDS;
    const timer = window.setInterval(() => setElapsed((e) => e + 0.1), 100);
    const next = window.setTimeout(() => go(1), seconds * 1000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(next);
    };
  }, [index, autoplay, found]);

  useEffect(() => {
    if (index === null) return;
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && (e.target.closest("input, textarea, select") !== null);
      if (e.key === "Escape") stop();
      else if (typing) return;
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, go, stop]);

  // Place the card where it covers none of the target: below, above, beside, else at the bottom of the screen.
  const vw = window.innerWidth, vh = window.innerHeight;
  const narrow = vw < 640;
  const cardWidth = Math.min(380, vw - 32);
  const cardHeight = card.current?.offsetHeight ?? 220;
  const gap = PAD + 14;
  let cardStyle: React.CSSProperties = { width: cardWidth, left: (vw - cardWidth) / 2, top: Math.max(16, vh / 2 - cardHeight / 2) };
  if (narrow) {
    cardStyle = { left: 16, right: 16, bottom: 16 };
  } else if (rect) {
    const alongX = Math.min(Math.max(16, rect.left), vw - cardWidth - 16);
    const alongY = Math.min(Math.max(16, rect.top), vh - cardHeight - 16);
    if (rect.bottom + gap + cardHeight <= vh - 8) cardStyle = { width: cardWidth, left: alongX, top: rect.bottom + gap };
    else if (rect.top - gap - cardHeight >= 8) cardStyle = { width: cardWidth, left: alongX, top: rect.top - gap - cardHeight };
    else if (vw - rect.right - gap >= cardWidth + 16) cardStyle = { width: cardWidth, left: rect.right + gap, top: alongY };
    else if (rect.left - gap >= cardWidth + 16) cardStyle = { width: cardWidth, left: rect.left - gap - cardWidth, top: alongY };
    else cardStyle = { width: cardWidth, left: vw - cardWidth - 16, top: vh - cardHeight - 16 };
  }
  const seconds = step?.seconds ?? DEFAULT_SECONDS;
  const value = useMemo(() => ({ start, active: index !== null }), [start, index !== null]);

  return (
    <TourContext.Provider value={value}>
      {children}
      {step &&
        createPortal(
          <div className="pointer-events-none fixed inset-0 z-[100]" aria-live="polite">
            {rect ? (
              <div
                className="absolute rounded-[22px] outline outline-2 outline-beam-400 transition-[top,left,width,height] duration-200"
                style={{ top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2, boxShadow: "0 0 0 9999px rgb(3 5 8 / 0.62)" }}
              />
            ) : (
              <div className="absolute inset-0 bg-[rgb(3_5_8_/_0.55)]" />
            )}
            <div
              ref={card}
              role="dialog"
              aria-modal="false"
              aria-labelledby="tour-title"
              tabIndex={-1}
              className="pointer-events-auto absolute flex flex-col gap-3 rounded-[20px] border border-beam-400/40 bg-ink-850 p-5 shadow-[0_24px_60px_-20px_rgba(0,0,0,.9)] outline-none"
              style={cardStyle}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-xs text-beam-300">{`${index! + 1} / ${STEPS.length}`}</span>
                <button type="button" className="grid h-8 w-8 place-items-center rounded-full text-fog-400 hover:bg-ink-700 hover:text-fog-100" aria-label="Close the tour" onClick={stop}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                </button>
              </div>
              <h2 id="tour-title" key={`t${index}`} className="m-0 text-lg font-medium text-fog-100">
                {step.title}
              </h2>
              <p key={`b${index}`} className="m-0 text-sm leading-relaxed text-fog-300">
                {step.body}
              </p>
              {step.target && !found && <p className="m-0 text-xs text-warn">{"Opening this part… (a live check can take a few seconds)"}</p>}
              {autoplay && (
                <div className="h-1 overflow-hidden rounded-full bg-ink-600" aria-hidden="true">
                  <div className="h-1 rounded-full bg-beam-400" style={{ width: `${Math.min(100, (elapsed / seconds) * 100)}%` }} />
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <button type="button" className="btn btn-ghost min-h-9 px-4 text-sm" onClick={() => go(-1)} disabled={index === 0}>
                  Back
                </button>
                <button type="button" className="btn btn-ghost min-h-9 px-4 text-sm" onClick={() => setAutoplay((a) => !a)} aria-pressed={autoplay}>
                  {autoplay ? "Pause" : "Autoplay"}
                </button>
                <button type="button" className="btn btn-primary min-h-9 px-4 text-sm" onClick={() => go(1)}>
                  {index === STEPS.length - 1 ? "Finish" : "Next"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </TourContext.Provider>
  );
}

export function TourButton() {
  const { start, active } = useTour();
  return (
    <button type="button" className="chip whitespace-nowrap" onClick={() => start(false)} disabled={active} aria-label="Start the guided tour">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M10 8.5l5 3.5-5 3.5z" fill="currentColor" />
      </svg>
      Tour
    </button>
  );
}
