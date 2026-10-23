import { useEffect, useRef, type ReactNode } from "react";

// GetLayers "Roadmap Ascent", adapted to a component: a spine with rows sliding past a fixed glowing node whose ring
// fills with progress, a readout that rises in when the active row changes, and the pixel-cube field. Driven by a
// value (row index as a float) instead of page scroll; recoloured through --tone.

export interface AscentRow {
  label: string;
  chip: string;
  title: string;
  sub: ReactNode;
}

export function Ascent({ rows, value, tone = "#5eead4", metric, icon, height = 460, compact = false }: { rows: AscentRow[]; value: number; tone?: string; metric?: ReactNode; icon?: ReactNode; height?: number; compact?: boolean }) {
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
      className="relative overflow-hidden rounded-[24px] border border-white/8"
      style={{ height, ["--tone" as string]: tone, ["--tone-rgb" as string]: toneRgb, background: `radial-gradient(70% 80% at 96% 0%, rgba(${toneRgb},.18), transparent 52%), radial-gradient(60% 90% at 100% 50%, rgba(${toneRgb},.08), transparent 60%), #05070b` }}
    >
      <canvas ref={pix} className="pointer-events-none absolute right-0 top-0 h-full w-[56%]" aria-hidden="true" />
      <div className="pointer-events-none absolute top-0 h-full w-px" style={{ left: spineX, background: "linear-gradient(180deg, transparent, rgba(233,240,233,.16) 16%, rgba(233,240,233,.16) 84%, transparent)" }} />
      <div className="pointer-events-none absolute inset-0 [mask:linear-gradient(180deg,transparent_2%,#000_26%,#000_74%,transparent_98%)]" aria-hidden="true">
        {rows.map((r, i) => (
          <div key={`l${i}`}>
            <div
              ref={(el) => {
                labels.current[i] = el;
              }}
              className="absolute left-0 origin-right whitespace-nowrap text-right text-sm font-medium text-fog-100"
              style={{ width: `calc(${spineX} - 60px)` }}
            >
              {r.label}
            </div>
            <div
              ref={(el) => {
                ticks.current[i] = el;
              }}
              className="absolute h-px w-3.5 -translate-y-1/2 bg-white/30"
              style={{ left: `calc(${spineX} - 7px)` }}
            />
          </div>
        ))}
      </div>
      <div ref={glow} className="pointer-events-none absolute top-1/2 h-[280px] w-[280px] -translate-x-1/2 -translate-y-1/2 rounded-full blur-[3px]" style={{ left: spineX, background: `radial-gradient(circle, rgba(${toneRgb},.42) 0%, rgba(${toneRgb},.11) 36%, transparent 66%)` }} />
      <div className="pointer-events-none absolute top-1/2 grid h-[72px] w-[72px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full" style={{ left: spineX }}>
        <div ref={ring} className="absolute inset-0 rounded-full [mask:radial-gradient(farthest-side,transparent_calc(100%-3px),#000_calc(100%-3px))]" style={{ background: `conic-gradient(var(--tone) calc(var(--p, 0) * 360deg), rgba(255,255,255,.09) 0)` }} />
        <div className="absolute inset-[5px] grid place-items-center rounded-full border border-white/10 bg-[radial-gradient(120%_120%_at_50%_18%,#1a1f27,#0a0d12_82%)] shadow-[0_14px_40px_-10px_rgba(0,0,0,.75)]">
          {icon ?? (
            <svg viewBox="0 0 24 24" className="h-[42%] w-[42%] animate-[bob_2.6s_ease-in-out_infinite]" fill="none" stroke="#e6efe1" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 13l6-6 6 6M6 18l6-6 6 6" />
            </svg>
          )}
        </div>
      </div>
      <div className="absolute flex flex-col" style={{ left: compact ? "36%" : "40%", right: "5%", top: "50%", transform: metric ? "translateY(calc(-100% - 10px))" : "translateY(-50%)" }} aria-live="polite">
        <div key={`r${active}`} className="flex flex-col animate-[rise_.6s_cubic-bezier(.22,.61,.36,1)_both]">
          <span className="inline-flex items-center gap-2 self-start rounded-full border px-3 py-1.5 text-xs font-semibold tracking-wide" style={{ color: `rgb(${toneRgb})`, borderColor: `rgba(${toneRgb},.3)`, background: `rgba(${toneRgb},.08)` }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: tone, boxShadow: `0 0 8px ${tone}` }} />
            {row?.chip}
          </span>
          <h3 className="m-0 mt-4 text-[clamp(22px,2.6vw,34px)] font-semibold leading-[1.08] tracking-tight text-fog-100">{row?.title}</h3>
          <div className="mt-3 max-w-[46ch] text-[15px] leading-relaxed text-fog-300">{row?.sub}</div>
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
