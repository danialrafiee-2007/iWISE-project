import { useId, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { useI18n, type MessageKey } from "../i18n";
import { EngineMenu } from "./EngineMenu";
import { LanguageMenu } from "./LanguageMenu";
import { TourMenu } from "./Tour";
import { Link, useRouter } from "../lib/router";
import { useWorkspace } from "../lib/workspace";

// The top bar's links: Home, the AI engine's tools (a list that opens on hover), About, Team and Contact.
const PAGES: { to: string; label: MessageKey }[] = [
  { to: "/about", label: "nav.about" },
  { to: "/team", label: "nav.team" },
  { to: "/contact", label: "nav.contact" },
];
const LINK = "whitespace-nowrap rounded-full px-3 py-2 font-sans text-[13px] font-medium uppercase tracking-[0.14em] no-underline transition-colors";

const SHIELD = "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z";
const CHECK = "M8.5 12l2.5 2.5 4.5-5";

/** The shield, drawn solid and in depth: a darker copy below and to the side as its edge, a lit face with a bright
 *  rim, and a raised check mark. It turns once about its upright axis every three seconds (styles.css). */
export function ShieldMark({ size = 36 }: { size?: number }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="3 1.5 19 21.5" className="shield-3d shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-face`} x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0" stopColor="#9dffc4" />
          <stop offset="0.45" stopColor="#2fb36a" />
          <stop offset="1" stopColor="#0f5a34" />
        </linearGradient>
        <linearGradient id={`${id}-edge`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#145c37" />
          <stop offset="1" stopColor="#06301b" />
        </linearGradient>
      </defs>
      <path d={SHIELD} fill={`url(#${id}-edge)`} transform="translate(0.9 1.1)" />
      <path d={SHIELD} fill={`url(#${id}-face)`} stroke="#d9ffe9" strokeOpacity="0.7" strokeWidth="0.7" strokeLinejoin="round" />
      <path d="M12 4.6l5.6 2.4" stroke="#ffffff" strokeOpacity="0.75" strokeWidth="0.9" strokeLinecap="round" />
      <path d={CHECK} fill="none" stroke="#06301b" strokeOpacity="0.55" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" transform="translate(0.35 0.5)" />
      <path d={CHECK} fill="none" stroke="#f3fff8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EngineStatus() {
  const { health, offline } = useWorkspace();
  const { t } = useI18n();
  let color = "var(--color-warn)";
  let text = t("engine.connecting");
  if (offline) {
    color = "var(--color-bad)";
    text = t("engine.unreachable");
  } else if (health?.state === "ready") {
    color = "var(--neon)";
    text = t("engine.ready");
  } else if (health?.state === "failed") {
    color = "var(--color-bad)";
    text = t("engine.failed");
  } else if (health) {
    text = health.state === "warming" ? t("engine.warming") : t("engine.loading");
  }
  return (
    <span className="flex items-center gap-2 whitespace-nowrap font-mono text-xs text-fog-400" role="status" aria-live="polite" title={text}>
      {/* Lit like a lamp: the models' state glows in its colour, phosphor green when they are ready. */}
      <span className={`status-lamp h-3.5 w-3.5 rounded-full ${health?.state === "ready" && !offline ? "status-lamp-ready" : ""}`} style={{ background: color, color }} aria-hidden="true" />
      {/* The dot's tooltip and screen readers carry the words: the bar is no wider on wide screens, so it has no room. */}
      <span key={text} className="sr-only">
        {text}
      </span>
    </span>
  );
}

// The links sit on the bar's single row whenever they fit between the name and the controls. When a longer language or a
// narrower window leaves too little room, they move to a row of their own instead of being cut off at the edges.
function useInlineNav(bar: RefObject<HTMLDivElement | null>, nav: RefObject<HTMLElement | null>, lang: string) {
  const [inline, setInline] = useState(true);
  useLayoutEffect(() => {
    const row = bar.current;
    const list = nav.current;
    if (!row || !list) return;
    const measure = () => {
      const [name, , controls] = [...row.children] as HTMLElement[];
      const style = getComputedStyle(row);
      const free = row.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) - name.offsetWidth - controls.offsetWidth - 2 * (parseFloat(style.columnGap) || 0);
      const links = [...list.children] as HTMLElement[];
      const needed = links.reduce((sum, link) => sum + link.offsetWidth, 0) + (links.length - 1) * (parseFloat(getComputedStyle(list).columnGap) || 0);
      setInline(needed <= free);
    };
    measure();
    const observer = new ResizeObserver(measure);
    [row, ...list.children, row.lastElementChild].forEach((el) => el && observer.observe(el));
    document.fonts?.ready.then(measure);
    return () => observer.disconnect();
  }, [bar, nav, lang]);
  return inline;
}

export function Shell({ children }: { children: ReactNode }) {
  const { path } = useRouter();
  const { lang, t } = useI18n();
  const bar = useRef<HTMLDivElement>(null);
  const nav = useRef<HTMLElement>(null);
  const inline = useInlineNav(bar, nav, lang);
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-beam-400 focus:px-4 focus:py-2 focus:text-beam-900">
        {t("shell.skip")}
      </a>
      <header className="sticky top-0 z-40 border-b border-hair bg-ink-950/95 backdrop-blur-md">
        {/* One row when it fits: name at the start, the tools in the middle, the controls at the end (mirrored right to left). */}
        <div ref={bar} className={`mx-auto flex max-w-[1320px] items-center justify-between gap-x-3 gap-y-2 px-4 py-2.5 sm:px-8 ${inline ? "flex-nowrap" : "flex-wrap"}`}>
          <Link to="/" className="brand relative isolate flex shrink-0 items-center gap-2.5 text-fog-100 no-underline">
            {/* A phosphor-green light that glows on and on all round the name and its shield. */}
            <span className="brand-glow" aria-hidden="true" />
            <ShieldMark size={42} />
            <span className="brand-name font-display text-[22px] font-medium tracking-tight" lang="en">
              Truth Guardian
            </span>
          </Link>
          <nav ref={nav} aria-label={t("nav.main")} className={`-mx-1 flex flex-wrap gap-0.5 ${inline ? "min-w-0 flex-1 justify-center" : "order-3 w-full"}`}>
            <Link to="/" aria-current={path === "/" ? "page" : undefined} className={`${LINK} nav-glow ${path === "/" ? "bg-beam-400/12 text-beam-300" : "text-fog-300 hover:text-fog-100"}`}>
              {t("nav.home")}
            </Link>
            <EngineMenu className={LINK} />
            {PAGES.map((item) => {
              const active = path.startsWith(item.to);
              return (
                <Link key={item.to} to={item.to} aria-current={active ? "page" : undefined} className={`${LINK} nav-glow ${active ? "bg-beam-400/12 text-beam-300" : "text-fog-300 hover:text-fog-100"}`}>
                  {t(item.label)}
                </Link>
              );
            })}
          </nav>
          <div className="flex shrink-0 items-center gap-2">
            <EngineStatus />
            <TourMenu />
            <LanguageMenu />
          </div>
        </div>
        {lang !== "en" && (
          <p className="m-0 border-t border-hair px-4 py-1.5 text-center text-xs text-fog-400 sm:px-8" role="note">
            {t("lang.englishOnly")}
          </p>
        )}
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-hair bg-ink-950 px-4 py-6 text-center text-xs text-fog-400 sm:px-8">{t("shell.footer")}</footer>
    </div>
  );
}
