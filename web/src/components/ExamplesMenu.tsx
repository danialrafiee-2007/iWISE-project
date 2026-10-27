import { Suspense, useEffect, useId, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { lazyPage } from "../lib/lazyPage";

// A temporary home for the ready-made examples, which used to sit on the landing page: a button in the top bar opens
// the card deck in a panel under the bar. The deck's code loads the first time the panel opens.

const ExamplesDeck = lazyPage(() => import("./ExamplesDeck"));

export function ExamplesMenu() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const panelId = useId();

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
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    // Not positioned itself, so the panel spans the whole (sticky) header beneath the bar.
    <div ref={root}>
      <button type="button" className="chip whitespace-nowrap" aria-expanded={open} aria-controls={panelId} title={t("examples.title")} onClick={() => setOpen((o) => !o)}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true">
          <rect x="7" y="4" width="10" height="16" rx="2" />
          <path d="M4 7v10M20 7v10" strokeLinecap="round" />
        </svg>
        <span className="sr-only xl:not-sr-only">{t("examples.button")}</span>
      </button>
      {open && (
        <div id={panelId} role="region" aria-label={t("examples.title")} className="absolute inset-x-0 top-full max-h-[calc(100dvh-80px)] overflow-y-auto border-b border-hair bg-ink-950/97 shadow-[0_24px_50px_-30px_rgba(44,58,52,.5)] backdrop-blur-md">
          <div className="mx-auto flex max-w-[1320px] flex-col gap-4 px-4 py-6 sm:px-8">
            <div className="flex items-center justify-between gap-4">
              <h2 className="eyebrow m-0">{t("examples.title")}</h2>
              <button type="button" className="grid h-9 w-9 place-items-center rounded-full text-fog-400 hover:bg-ink-700 hover:text-fog-100" aria-label={t("examples.close")} onClick={() => setOpen(false)}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            </div>
            <Suspense fallback={<div className="h-[440px]" />}>
              <ExamplesDeck onPick={() => setOpen(false)} />
            </Suspense>
          </div>
        </div>
      )}
    </div>
  );
}
