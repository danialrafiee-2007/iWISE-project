import { useEffect, useId, useState, type ReactNode } from "react";
import { useI18n, type MessageKey } from "../i18n";
import { Link, useRouter } from "../lib/router";
import { moveFocus, useHoverMenu } from "../lib/useHoverMenu";

// "AI engine" in the top bar: its three inputs, text first (the challenge's own), then sound and images (the project's
// additions), and beside the one the pointer rests on (or that a tap chose), the parts of the engine behind it. Text
// holds what Challenge 4 asks for and nothing else: checking an answer against its documents, checking an agent's logs,
// and how reliable the result is (D-143); sound and images each hold a page that reads a file and one that says which
// models do it and what they have been shown to do.

export type Medium = "text" | "audio" | "image";
type Item = { to: string; label: MessageKey; within?: string[] };

export const TOOLS: Item[] = [
  // The same check used another way lives inside this one (CheckLinks), so those pages count as being here.
  { to: "/analyze", label: "nav.analyze", within: ["/heal", "/fool", "/audit", "/examples"] },
  { to: "/agent", label: "nav.agent" },
  { to: "/model", label: "nav.model" },
];

const ICONS: Record<Medium, ReactNode> = {
  text: <path d="M5 6h14M5 10h14M5 14h9M5 18h6" />,
  audio: <path d="M12 4a3 3 0 013 3v4a3 3 0 01-6 0V7a3 3 0 013-3zM6 11a6 6 0 0012 0M12 17v3" />,
  image: <path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2zM4 16l5-5 4 4 2-2 5 5M15 9h.01" />,
};

export const SECTIONS: { medium: Medium; label: MessageKey; items: Item[] }[] = [
  { medium: "text", label: "nav.text", items: TOOLS },
  { medium: "audio", label: "nav.audio", items: [{ to: "/audio", label: "nav.audioRead" }, { to: "/audio/models", label: "nav.models" }] },
  { medium: "image", label: "nav.image", items: [{ to: "/image", label: "nav.imageRead" }, { to: "/image/models", label: "nav.models" }] },
];

/** On a phone a top-bar menu opens across the screen just under the bar (the header's blur makes it the frame that a
 *  fixed element is placed in), rather than from its label, where it could reach past the screen's edge. */
export const NARROW = "max-sm:fixed max-sm:inset-x-3 max-sm:top-full";

export function MediumIcon({ medium, size = 16 }: { medium: Medium; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICONS[medium]}
    </svg>
  );
}

export function EngineMenu({ className }: { className: string }) {
  const { t } = useI18n();
  const { path } = useRouter();
  const menu = useHoverMenu();
  const listId = useId();
  const isHere = (item: Item) => item.to === path || !!item.within?.includes(path);
  const here = SECTIONS.find((s) => s.items.some(isHere));
  const [chosen, setChosen] = useState<Medium | null>(null);
  // Each opening starts on the input of the page shown, or on text.
  useEffect(() => {
    if (!menu.open) setChosen(null);
  }, [menu.open]);
  const shown = SECTIONS.find((s) => s.medium === (chosen ?? here?.medium ?? "text"))!;

  return (
    <div
      ref={menu.root}
      className="relative"
      {...menu.hover}
      onKeyDown={(e) => moveFocus(e, menu.root.current)}
    >
      <button
        type="button"
        className={`${className} nav-glow inline-flex items-center gap-1.5 ${here ? "bg-beam-400/12 text-beam-300" : menu.open ? "text-fog-100" : "text-fog-300 hover:text-fog-100"}`}
        aria-haspopup="menu"
        aria-expanded={menu.open}
        aria-controls={listId}
        onClick={menu.toggle}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            menu.pin();
            window.setTimeout(() => menu.root.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus());
          }
        }}
      >
        {t("nav.engine")}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`transition-transform ${menu.open ? "rotate-180" : ""}`}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {menu.open && (
        <div ref={menu.list} id={listId} role="menu" aria-label={t("nav.engine")} className={`${NARROW} absolute start-0 top-full z-50 pt-2`} style={{ translate: `${menu.shift}px` }}>
          {/* The four inputs on one side, the chosen input's parts on the other, so nothing opens off the screen. */}
          <div className="flex w-[min(470px,calc(100vw-24px))] max-sm:w-full rounded-2xl border border-hair bg-ink-850 p-1.5 font-sans shadow-[0_18px_44px_-16px_rgba(44,58,52,.35)]">
            <div className="flex w-[40%] shrink-0 flex-col gap-0.5 border-e border-hair pe-1.5">
              {SECTIONS.map((section) => {
                const active = section.medium === shown.medium;
                return (
                  <button
                    key={section.medium}
                    type="button"
                    role="menuitem"
                    aria-haspopup="menu"
                    aria-expanded={active}
                    onPointerEnter={() => setChosen(section.medium)}
                    onFocus={() => setChosen(section.medium)}
                    onClick={() => setChosen(section.medium)}
                    className={`nav-glow flex min-h-11 items-center gap-2.5 rounded-xl px-3 text-start text-sm ${active ? "bg-beam-400/12 text-beam-300" : "text-fog-200"}`}
                  >
                    <MediumIcon medium={section.medium} />
                    <span className="flex-1">{t(section.label)}</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`rtl:-scale-x-100 ${active ? "opacity-90" : "opacity-40"}`}>
                      <path d="M9 6l6 6-6 6" />
                    </svg>
                  </button>
                );
              })}
            </div>
            <div role="group" aria-label={t(shown.label)} className="flex min-w-0 flex-1 flex-col gap-0.5 ps-1.5">
              {shown.items.map((item) => {
                const active = isHere(item);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    role="menuitem"
                    aria-current={active ? "page" : undefined}
                    className={`nav-glow flex min-h-10 items-center rounded-xl px-3 text-sm no-underline ${active ? "bg-beam-400/12 text-beam-300" : "text-fog-200"}`}
                    onClick={menu.close}
                  >
                    {t(item.label)}
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
