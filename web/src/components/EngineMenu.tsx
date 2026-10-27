import { useEffect, useId, useRef, useState } from "react";
import { useI18n, type MessageKey } from "../i18n";
import { Link, useRouter } from "../lib/router";

// "AI engine" in the top bar: the tools, listed as soon as the pointer rests on it (no click needed). A click or a
// tap opens it too, for touch screens, and the keyboard reaches it with Enter, Space or the down arrow.

export const TOOLS: { to: string; label: MessageKey }[] = [
  { to: "/analyze", label: "nav.analyze" },
  { to: "/heal", label: "nav.heal" },
  { to: "/fool", label: "nav.fool" },
  { to: "/agent", label: "nav.agent" },
  { to: "/audit", label: "nav.audit" },
  { to: "/model", label: "nav.model" },
];

const CLOSE_DELAY = 180;

export function EngineMenu({ className }: { className: string }) {
  const { t } = useI18n();
  const { path } = useRouter();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  // Opened by a click or tap rather than by resting the pointer: then leaving with the pointer does not close it.
  const pinned = useRef(false);
  const listId = useId();
  const current = TOOLS.some((tool) => path.startsWith(tool.to));

  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  // A short delay lets the pointer cross the gap between the label and the list.
  const hide = () => {
    window.clearTimeout(timer.current);
    if (!pinned.current) timer.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY);
  };
  const close = () => {
    pinned.current = false;
    setOpen(false);
  };
  // The pointer has usually opened the list on its way to a click, so a click keeps it open; a second click closes it.
  const toggle = () => {
    window.clearTimeout(timer.current);
    if (open && pinned.current) close();
    else {
      pinned.current = true;
      setOpen(true);
    }
  };

  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(close, [path]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        root.current?.querySelector<HTMLButtonElement>("button")?.focus();
      }
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const moveFocus = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [...(root.current?.querySelectorAll<HTMLAnchorElement>("[role=menuitem]") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLAnchorElement);
    items[(at + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
  };

  return (
    <div ref={root} className="relative" onPointerEnter={(e) => e.pointerType === "mouse" && show()} onPointerLeave={(e) => e.pointerType === "mouse" && hide()} onKeyDown={moveFocus}>
      <button
        type="button"
        className={`${className} inline-flex items-center gap-1.5 ${current ? "bg-beam-400/12 text-beam-300" : open ? "text-fog-100" : "text-fog-300 hover:text-fog-100"}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={listId}
        onClick={toggle}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            pinned.current = true;
            setOpen(true);
            window.setTimeout(() => root.current?.querySelector<HTMLAnchorElement>("[role=menuitem]")?.focus());
          }
        }}
      >
        {t("nav.engine")}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`transition-transform ${open ? "rotate-180" : ""}`}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div id={listId} role="menu" aria-label={t("nav.engine")} className="absolute start-0 top-full z-50 pt-2">
          <div className="flex min-w-[220px] flex-col gap-0.5 rounded-2xl border border-hair bg-ink-850 p-1.5 font-sans shadow-[0_18px_44px_-16px_rgba(44,58,52,.35)]">
            {TOOLS.map((tool) => {
              const active = path.startsWith(tool.to);
              return (
                <Link
                  key={tool.to}
                  to={tool.to}
                  role="menuitem"
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-10 items-center rounded-xl px-3 text-sm no-underline ${active ? "bg-beam-400/12 text-beam-300" : "text-fog-200 hover:bg-ink-700"}`}
                  onClick={close}
                >
                  {t(tool.label)}
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
