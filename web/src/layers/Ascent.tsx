import { useEffect, useRef, type ReactNode } from "react";

// The "Roadmap Ascent" section (docs/CREDITS.md), adapted to a component: a spine with rows sliding past a fixed glowing node whose ring
// fills with progress, a readout that rises in when the active row changes, and the pixel-cube field. Driven by a
// value (row index as a float) instead of page scroll; recoloured through --tone. With onToggle, each row's label and
// the node open that row: the row holds still, the node's arrow turns to point right and `panel` takes the place of
// the row's description.

export interface AscentRow {
  label: string;
  chip: string;
  title: string;
  sub: ReactNode;
}

// Two looks: the app's light one, and the section's original night (the landing page, on its dark ground).
const LOOKS = {
  light: { ground: "#f6f1e4", frame: "border-hair", spine: "rgba(44,58,52,.16)", tick: "bg-fog-400/40", track: "rgba(44,58,52,.1)", disc: "border-hair bg-[radial-gradient(120%_120%_at_50%_18%,#fdfcfa,#ece4d2_82%)] shadow-[0_14px_40px_-10px_rgba(44,58,52,.35)]" },
  night: { ground: "#05070b", frame: "border-white/8", spine: "rgba(233,240,233,.16)", tick: "bg-white/30", track: "rgba(255,255,255,.09)", disc: "border-white/10 bg-[radial-gradient(120%_120%_at_50%_18%,#1a1f27,#0a0d12_82%)] shadow-[0_14px_40px_-10px_rgba(0,0,0,.75)]" },
};

export function Ascent({
  rows, value, night = false, tone = night ? "#5eead4" : "#456b56", metric, icon, height = 460, compact = false, open = null, onToggle, panel, cta, closeLabel,
}: {
  rows: AscentRow[]; value: number; night?: boolean; tone?: string; metric?: ReactNode; icon?: ReactNode; height?: number; compact?: boolean;
  open?: number | null; onToggle?: (row: number) => void; panel?: ReactNode; cta?: string; closeLabel?: string;
}) {
  const look = night ? LOOKS.night : LOOKS.light;
  const opened = open != null && onToggle != null;
  value = open != null && onToggle ? open : value;
  const wrap = useRef<HTMLDivElement>(null);
  const labels = useRef<(HTMLDivElement | null)[]>([]);
  const ticks = useRef<(HTMLDivElement | null)[]>([]);
  const ring = useRef<HTMLDivElement>(null);
  const glow = useRef<HTMLDivElement>(null);
  const pix = useRef<HTMLCanvasElement>(null);
  const target = useRef(value);
  target.current = value;
  const active = Math.max(0, Math.min(rows.length - 1, Math.round(value)));
  const N = rows.length;

  useEffect(() => {
    const el = wrap.current;
    const canvas = pix.current;
    if (!el || !canvas) return;
    const ctx = canvas.getContext("2d")!;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let cur = target.current, raf = 0;
    let cells: { x: number; y: number; s: number; d: number; ph: number }[] = [];
    const build = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(devicePixelRatio, 2);
      canvas.width = r.width * dpr;
      canvas.height = r.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const gap = Math.max(11, r.width / 40);
      let seed = 8.31;
      const rnd = () => ((seed = Math.sin(seed * 91.7 + 3) * 43758.5), seed - Math.floor(seed));
      cells = [];
      for (let x = 0; x < r.width; x += gap)
        for (let y = 0; y < r.height; y += gap) {
          const d = Math.hypot(1 - x / r.width, y / r.height);
          if (rnd() < 1.05 - d * 0.92) cells.push({ x, y, s: gap * (0.4 + rnd() * 0.42), d, ph: rnd() * 6.28 });
        }
    };
    const observer = new ResizeObserver(build);
    observer.observe(canvas);
    build();
    const loop = (t: number) => {
      cur += (target.current - cur) * (reduce ? 1 : 0.085);
      if (Math.abs(target.current - cur) < 1e-4) cur = target.current;
      const h = el.clientHeight, cy = h / 2, spacing = Math.max(64, Math.min(h * 0.17, 104));
      labels.current.forEach((label, i) => {
        if (!label) return;
        const d = i - cur, ad = Math.abs(d), prox = Math.max(0, 1 - ad);
        label.style.top = `${cy + d * spacing}px`;
        label.style.transform = `translateY(-50%) translateX(${(-18 * prox).toFixed(1)}px) scale(${(1 + 0.09 * prox).toFixed(3)})`;
        label.style.opacity = Math.max(0.14, 1 - ad * 0.32).toFixed(3);
        const tick = ticks.current[i];
        if (tick) {
          tick.style.top = `${cy + d * spacing}px`;
          tick.style.opacity = Math.max(0, Math.min(1, (ad - 0.55) / 0.8)).toFixed(3);
        }
      });
      ring.current?.style.setProperty("--p", (N > 1 ? cur / (N - 1) : 1).toFixed(4));
      if (glow.current) glow.current.style.opacity = reduce ? "0.85" : (0.7 + 0.3 * Math.sin(t * 0.0018)).toFixed(3);
      const r = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, r.width, r.height);
      const rgb = getComputedStyle(el).getPropertyValue("--tone-rgb").trim() || "94,234,212";
      const intensity = 0.3 + 0.7 * (N > 1 ? cur / (N - 1) : 1);
      for (const c of cells) {
        const a = Math.max(0, 1 - c.d * 0.82) * (0.5 + 0.5 * Math.sin((reduce ? 0 : t) * 0.0015 + c.ph + c.d * 4)) * intensity;
        if (a <= 0.02) continue;
        ctx.fillStyle = `rgba(${rgb},${(a * 0.55).toFixed(3)})`;
        ctx.fillRect(c.x, c.y, c.s, c.s);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [N]);

  const toneRgb = (() => {
    const n = parseInt(tone.replace("#", ""), 16);
    return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
  })();
  const row = rows[active];
  const spineX = compact ? "26%" : "30%";

  return (
    <div
      ref={wrap}
      className={`relative overflow-hidden rounded-[24px] border ${look.frame}`}
      style={{ height, ["--tone" as string]: tone, ["--tone-rgb" as string]: toneRgb, ["--ground" as string]: look.ground, background: `radial-gradient(70% 80% at 96% 0%, rgba(${toneRgb},.18), transparent 52%), radial-gradient(60% 90% at 100% 50%, rgba(${toneRgb},.08), transparent 60%), ${look.ground}` }}
    >
      <canvas ref={pix} className="pointer-events-none absolute right-0 top-0 h-full w-[56%]" aria-hidden="true" />
      <div className="pointer-events-none absolute top-0 h-full w-px" style={{ left: spineX, background: `linear-gradient(180deg, transparent, ${look.spine} 16%, ${look.spine} 84%, transparent)` }} />
      <div className={`pointer-events-none absolute inset-0 [mask:linear-gradient(180deg,transparent_2%,#000_26%,#000_74%,transparent_98%)] ${opened ? "max-md:invisible" : ""}`} aria-hidden={onToggle ? undefined : true}>
        {rows.map((r, i) => (
          <div key={`l${i}`}>
            <div
              ref={(el) => {
                labels.current[i] = el;
              }}
              // The left padding leaves room for the active label's lift to the left; long labels wrap rather than run off the card.
              className="absolute left-0 origin-right pl-8 text-right text-sm font-medium leading-tight text-fog-100"
              style={{ width: `calc(${spineX} - 60px)` }}
            >
              {onToggle ? (
                <button type="button" className="pointer-events-auto cursor-pointer rounded-md bg-transparent p-1 text-inherit hover:text-[var(--tone)]" aria-expanded={opened && open === i} onClick={() => onToggle(i)}>
                  {r.label}
                </button>
              ) : (
                r.label
              )}
            </div>
            <div
              ref={(el) => {
                ticks.current[i] = el;
              }}
              className={`absolute h-px w-3.5 -translate-y-1/2 ${look.tick}`}
              style={{ left: `calc(${spineX} - 7px)` }}
            />
          </div>
        ))}
      </div>
      <div ref={glow} className="pointer-events-none absolute top-1/2 h-[280px] w-[280px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[3px]" style={{ left: spineX, background: `radial-gradient(circle, rgba(${toneRgb},.42) 0%, rgba(${toneRgb},.11) 36%, transparent 66%)` }} />
      <div className="pointer-events-none absolute top-1/2 grid h-[72px] w-[72px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full" style={{ left: spineX }}>
        <div ref={ring} className="absolute inset-0 rounded-full [mask:radial-gradient(farthest-side,transparent_calc(100%-3px),#000_calc(100%-3px))]" style={{ background: `conic-gradient(var(--tone) calc(var(--p, 0) * 360deg), ${look.track} 0)` }} />
        {onToggle ? (
          <button
            type="button"
            className={`pointer-events-auto absolute inset-[5px] grid cursor-pointer place-items-center rounded-full border ${look.disc} hover:brightness-125`}
            aria-expanded={opened}
            aria-label={opened ? closeLabel : rows[active]?.label}
            onClick={() => onToggle(active)}
          >
            {/* The arrow points up while the rows scroll past, and turns to point right at the open row's panel. */}
            <span className="grid h-[42%] w-[42%] place-items-center transition-transform duration-300" style={{ transform: opened ? "rotate(90deg)" : "none" }}>
              <svg viewBox="0 0 24 24" className={`h-full w-full ${opened ? "" : "animate-[bob_2.6s_ease-in-out_infinite]"}`} fill="none" stroke="#e6efe1" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M6 13l6-6 6 6M6 18l6-6 6 6" />
              </svg>
            </span>
          </button>
        ) : (
          <div className={`absolute inset-[5px] grid place-items-center rounded-full border ${look.disc}`}>
            {icon ?? (
              <svg viewBox="0 0 24 24" className="h-[42%] w-[42%] animate-[bob_2.6s_ease-in-out_infinite]" fill="none" stroke="#e6efe1" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M6 13l6-6 6 6M6 18l6-6 6 6" />
              </svg>
            )}
          </div>
        )}
      </div>
      <div
        // Open, the panel fills the card beside the spine; on a narrow screen it covers the spine too, on the card's own ground.
        className={opened ? `absolute inset-y-[22px] left-[3%] right-[3%] z-10 flex flex-col max-md:rounded-[16px] max-md:bg-[var(--ground)] ${compact ? "md:left-[36%]" : "md:left-[40%]"}` : "absolute flex flex-col"}
        style={opened ? undefined : { left: compact ? "36%" : "40%", right: "5%", top: "50%", transform: metric ? "translateY(calc(-100% - 10px))" : "translateY(-50%)" }}
        aria-live={opened ? undefined : "polite"}
      >
        <div key={`r${active}${opened ? "o" : ""}`} className={`flex flex-col animate-[rise_.6s_cubic-bezier(.22,.61,.36,1)_both] ${opened ? "min-h-0 flex-1" : ""}`}>
          <div className="flex items-start justify-between gap-3">
            <span className="inline-flex items-center gap-2 self-start rounded-full border px-3 py-1.5 text-xs font-semibold tracking-wide" style={{ color: `rgb(${toneRgb})`, borderColor: `rgba(${toneRgb},.3)`, background: `rgba(${toneRgb},.08)` }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: tone, boxShadow: `0 0 8px ${tone}` }} />
              {row?.chip}
            </span>
            {opened && (
              <button type="button" className="grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-full text-fog-300 hover:bg-white/10 hover:text-fog-100" aria-label={closeLabel} title={closeLabel} onClick={() => onToggle(active)}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            )}
          </div>
          <h3 className={`m-0 font-semibold leading-[1.08] tracking-tight text-fog-100 ${opened ? "mt-3 text-[clamp(20px,2vw,26px)]" : "mt-4 text-[clamp(22px,2.6vw,34px)]"}`}>{row?.title}</h3>
          {opened ? (
            <div className="mt-4 flex min-h-0 flex-1 flex-col">{panel}</div>
          ) : (
            <>
              <div className="mt-3 max-w-[46ch] text-[15px] leading-relaxed text-fog-300">{row?.sub}</div>
              {onToggle && cta && (
                <button type="button" className="mt-5 inline-flex cursor-pointer items-center gap-2 self-start rounded-full border px-4 py-2 text-sm font-medium" style={{ color: `rgb(${toneRgb})`, borderColor: `rgba(${toneRgb},.35)` }} onClick={() => onToggle(active)}>
                  {cta}
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="rtl:-scale-x-100">
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </svg>
                </button>
              )}
            </>
          )}
        </div>
      </div>
      {metric && (
        <div className="absolute" style={{ left: compact ? "36%" : "40%", right: "5%", top: "50%", transform: "translateY(14px)" }}>
          {metric}
        </div>
      )}
    </div>
  );
}
