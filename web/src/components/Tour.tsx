import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useI18n, type MessageKey } from "../i18n";
import { useRouter } from "../lib/router";
import { moveFocus, useHoverMenu } from "../lib/useHoverMenu";
import { MediumIcon, NARROW, type Medium } from "./EngineMenu";

// A guided tour for judges and first-time users: it opens each tool on a ready-made example, dims the page around the
// part that matters and explains it. Autoplay advances by itself, for a hands-free demo or a screen recording. The
// page stays usable underneath; only the explanation card takes clicks.

interface Step {
  url: string;
  target?: string;
  title: MessageKey;
  body: MessageKey;
  seconds?: number;
}

const STEPS: Step[] = [
  {
    url: "/",
    title: "tour.s1.title",
    body: "tour.s1.body",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "answer",
    title: "tour.s2.title",
    body: "tour.s2.body",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "claim",
    title: "tour.s3.title",
    body: "tour.s3.body",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "verdict",
    title: "tour.s4.title",
    body: "tour.s4.body",
  },
  {
    url: "/analyze?example=anne-frank",
    target: "blame",
    title: "tour.s5.title",
    body: "tour.s5.body",
  },
  {
    url: "/analyze?example=library",
    target: "conflicts",
    title: "tour.s6.title",
    body: "tour.s6.body",
  },
  {
    url: "/heal?example=anne-frank",
    target: "heal-rounds",
    title: "tour.s7.title",
    body: "tour.s7.body",
    seconds: 10,
  },
  {
    url: "/fool",
    target: "tricks",
    title: "tour.s8.title",
    body: "tour.s8.body",
  },
  {
    url: "/agent?example=agent-liberation",
    target: "agent-timeline",
    title: "tour.s9.title",
    body: "tour.s9.body",
    seconds: 12,
  },
  {
    url: "/model",
    target: "headline",
    title: "tour.s10.title",
    body: "tour.s10.body",
  },
  {
    url: "/analyze",
    target: "upload",
    title: "tour.s11.title",
    body: "tour.s11.body",
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
  const { t } = useI18n();

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
                style={{ top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2, boxShadow: "0 0 0 9999px rgb(44 58 52 / 0.42)" }}
              />
            ) : (
              <div className="absolute inset-0 bg-[rgb(44_58_52_/_0.38)]" />
            )}
            <div
              ref={card}
              role="dialog"
              aria-modal="false"
              aria-labelledby="tour-title"
              tabIndex={-1}
              className="pointer-events-auto absolute flex flex-col gap-3 rounded-[20px] border border-beam-400/40 bg-ink-850 p-5 shadow-[0_24px_60px_-20px_rgba(44,58,52,.45)] outline-none"
              style={cardStyle}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-xs text-beam-300">{t("tour.count", { i: index! + 1, n: STEPS.length })}</span>
                <button type="button" className="grid h-8 w-8 place-items-center rounded-full text-fog-400 hover:bg-ink-700 hover:text-fog-100" aria-label={t("tour.close")} onClick={stop}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                </button>
              </div>
              <h2 id="tour-title" key={`t${index}`} className="m-0 text-lg font-medium text-fog-100">
                {t(step.title)}
              </h2>
              <p key={`b${index}`} className="m-0 text-sm leading-relaxed text-fog-300">
                {t(step.body)}
              </p>
              {step.target && !found && <p className="m-0 text-xs text-warn-ink">{t("tour.opening")}</p>}
              {autoplay && (
                <div className="h-1 overflow-hidden rounded-full bg-ink-600" aria-hidden="true">
                  <div className="h-1 rounded-full bg-beam-400" style={{ width: `${Math.min(100, (elapsed / seconds) * 100)}%` }} />
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <button type="button" className="btn btn-ghost min-h-9 px-4 text-sm" onClick={() => go(-1)} disabled={index === 0}>
                  {t("tour.back")}
                </button>
                <button type="button" className="btn btn-ghost min-h-9 px-4 text-sm" onClick={() => setAutoplay((a) => !a)} aria-pressed={autoplay}>
                  {autoplay ? t("common.pause") : t("tour.autoplay")}
                </button>
                <button type="button" className="btn btn-primary min-h-9 px-4 text-sm" onClick={() => go(1)}>
                  {index === STEPS.length - 1 ? t("tour.finish") : t("tour.next")}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </TourContext.Provider>
  );
}

// The tours, one per input. Only the text tour is written so far; the others are listed, switched off and
// marked as coming, until their pages are settled.
const TOURS: { medium: Medium; label: MessageKey; ready: boolean }[] = [
  { medium: "text", label: "tour.text", ready: true },
  { medium: "audio", label: "tour.audio", ready: false },
  { medium: "image", label: "tour.image", ready: false },
];

/** "Tour" in the top bar: the list of tours opens while the pointer rests on it, or on a click or tap. */
export function TourMenu() {
  const { start, active } = useTour();
  const { t } = useI18n();
  const menu = useHoverMenu();
  const listId = useId();
  return (
    <div ref={menu.root} className="relative" {...menu.hover} onKeyDown={(e) => moveFocus(e, menu.root.current)}>
      <button
        type="button"
        className="chip nav-glow whitespace-nowrap"
        aria-haspopup="menu"
        aria-expanded={menu.open}
        aria-controls={listId}
        disabled={active}
        title={t("tour.start")}
        onClick={menu.toggle}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            menu.pin();
            window.setTimeout(() => menu.root.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus());
          }
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M10 8.5l5 3.5-5 3.5z" fill="currentColor" />
        </svg>
        {t("tour.button")}
      </button>
      {menu.open && (
        <div ref={menu.list} id={listId} role="menu" aria-label={t("tour.start")} className={`${NARROW} absolute end-0 top-full z-50 pt-2`} style={{ translate: `${menu.shift}px` }}>
          <div className="flex min-w-[230px] flex-col gap-0.5 rounded-2xl border border-hair bg-ink-850 p-1.5 font-sans shadow-[0_18px_44px_-16px_rgba(44,58,52,.35)]">
            {TOURS.map((tour) => (
              <button
                key={tour.medium}
                type="button"
                role="menuitem"
                aria-disabled={!tour.ready}
                className={`flex min-h-10 items-center gap-2.5 rounded-xl px-3 text-start text-sm ${tour.ready ? "nav-glow text-fog-200" : "cursor-default text-fog-400"}`}
                onClick={() => {
                  if (!tour.ready) return;
                  menu.close();
                  start(false);
                }}
              >
                <MediumIcon medium={tour.medium} />
                <span className="flex-1">{t(tour.label)}</span>
                {!tour.ready && <span className="rounded-full border border-hair px-2 py-0.5 text-[11px]">{t("tour.soon")}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
