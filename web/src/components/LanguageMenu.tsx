import { useEffect, useId, useRef, useState } from "react";
import { LANGUAGES, setLang, useI18n } from "../i18n";

// The language switch at the end of the top bar (top right, or top left on right-to-left pages): a globe with the
// current language's name, opening the list of languages. The list reads left to right on every page; Arabic and
// Persian are named in English (lang="en"), the others in their own script.

const nameLang = (l: (typeof LANGUAGES)[number]) => (l.dir === "rtl" ? "en" : l.code);

export function LanguageMenu() {
  const { lang, t } = useI18n();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const listId = useId();
  const current = LANGUAGES.find((l) => l.code === lang) ?? LANGUAGES[0];

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    root.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus();
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const moveFocus = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = [...(root.current?.querySelectorAll<HTMLButtonElement>("[role=menuitemradio]") ?? [])];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    items[(at + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
  };

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        className="chip whitespace-nowrap"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={listId}
        title={t("lang.choose")}
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18M12 3c2.6 2.6 3.9 5.6 3.9 9s-1.3 6.4-3.9 9c-2.6-2.6-3.9-5.6-3.9-9s1.3-6.4 3.9-9z" />
        </svg>
        <span className="sr-only">{`${t("lang.label")}: `}</span>
        <span lang={nameLang(current)}>{current.name}</span>
      </button>
      {open && (
        <div
          id={listId}
          role="menu"
          aria-label={t("lang.label")}
          onKeyDown={moveFocus}
          dir="ltr"
          className="absolute end-0 top-[calc(100%+8px)] z-50 flex min-w-[168px] flex-col gap-0.5 rounded-2xl border border-hair bg-ink-850 p-1.5 shadow-[0_18px_44px_-16px_rgba(44,58,52,.35)] font-sans"
        >
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              type="button"
              role="menuitemradio"
              aria-checked={l.code === lang}
              lang={nameLang(l)}
              className={`flex min-h-10 items-center justify-between gap-3 rounded-xl px-3 text-start text-sm ${l.code === lang ? "bg-beam-400/12 text-beam-300" : "text-fog-200 hover:bg-ink-700"}`}
              onClick={() => {
                setLang(l.code);
                setOpen(false);
              }}
            >
              {l.name}
              {l.code === lang && (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                  <path d="M5 12.5l4.5 4.5L19 7.5" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
