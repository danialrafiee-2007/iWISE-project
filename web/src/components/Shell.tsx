import type { ReactNode } from "react";
import { GuardianOrb } from "../layers/GuardianOrb";
import { Link, useRouter } from "../lib/router";
import { useWorkspace } from "../lib/workspace";

export const NAV = [
  { to: "/analyze", label: "Analyze" },
  { to: "/heal", label: "Heal" },
  { to: "/fool", label: "Fool the Guardian" },
  { to: "/agent", label: "Agent guardian" },
  { to: "/audit", label: "Audit" },
  { to: "/model", label: "Model card" },
];

export function ShieldMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="var(--color-beam-400)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </svg>
  );
}

function EngineStatus() {
  const { health, offline } = useWorkspace();
  let color = "var(--color-warn)";
  let text = "connecting";
  if (offline) {
    color = "var(--color-bad)";
    text = "server not reachable";
  } else if (health?.state === "ready") {
    color = "var(--color-ok)";
    text = "offline · models ready";
  } else if (health?.state === "failed") {
    color = "var(--color-bad)";
    text = "models failed to load";
  } else if (health) {
    text = health.state === "warming" ? "warming up the models" : "loading the models";
  }
  return (
    <span className="flex items-center gap-2 font-mono text-xs text-fog-400" role="status" aria-live="polite">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} aria-hidden="true" />
      <span key={text}>{text}</span>
    </span>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { path } = useRouter();
  const { mood } = useWorkspace();
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-beam-400 focus:px-4 focus:py-2 focus:text-beam-900">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-white/5 bg-ink-950/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-2.5 sm:px-8">
          <Link to="/" className="flex items-center gap-2.5 text-fog-100 no-underline">
            <ShieldMark />
            <span className="text-[17px] font-medium tracking-tight">Truth Guardian</span>
          </Link>
          <nav aria-label="Main" className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto [scrollbar-width:none] lg:order-none lg:w-auto">
            {NAV.map((item) => {
              const active = path.startsWith(item.to);
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  className={`whitespace-nowrap rounded-full px-3.5 py-2 text-sm no-underline transition-colors ${active ? "bg-beam-400/12 text-beam-300" : "text-fog-300 hover:text-fog-100"}`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center gap-3">
            <EngineStatus />
            <GuardianOrb mood={mood} diameter={40} />
          </div>
        </div>
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-white/5 px-4 py-6 text-center text-xs text-fog-400 sm:px-8">
        Truth Guardian · iWISE 2026 AI Challenge 4 · runs entirely on this computer, no data leaves it
      </footer>
    </div>
  );
}
