import { useEffect, useRef, useState, type ReactNode } from "react";
import { formatNumber, t } from "../i18n";
import { useWheelTurn } from "./useWheelTurn";

// GetLayers "Slider Spectra", adapted: the same ring coverflow (fan geometry, glide, drag with momentum, arrow keys,
// autoplay that pauses on hover and when hidden) and the halo that takes the centre card's colour; the cards hold
// our examples instead of product photos. The mouse wheel over the deck turns it a card per notch (useWheelTurn).
// It sits beside a form and above a report on a page that checks answers on this computer's processor, so it draws
// only while a card moves, and autoplay also waits while `paused` or while someone is typing.

const C = { gap: 164, rotate: 38, depth: 150, drop: 24, shrink: 0.14, fade: 0.26, dim: 0.2, visible: 3, persp: 1680, autoplayMs: 3200, ease: 0.14, sensitivity: 0.0072 };

export interface SpectraCard {
  key: string;
  c1: string;
  c2: string;
  glow: string;
  label: string;
  content: ReactNode;
}

export function SpectraDeck({ cards, onOpen, caption, cta, paused = false }: { cards: SpectraCard[]; onOpen: (i: number) => void; caption: (i: number) => ReactNode; cta: string; paused?: boolean }) {
  const N = cards.length;
  const deck = useRef<HTMLElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const halo = useRef<HTMLDivElement>(null);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const state = useRef({ pos: 0, target: 0, dragging: false, moved: false, lastX: 0, startX: 0, vel: 0, hover: false, scale: 1 });
  const wake = useRef(() => {});
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!N) return;
    const s = state.current;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const wrap = (o: number) => {
      o = ((o % N) + N) % N;
      return o > N / 2 ? o - N : o;
    };
    const paint = () => {
      const w = stage.current?.clientWidth ?? 1180;
      s.scale = Math.max(0.56, Math.min(1, w / 1180));
      for (let i = 0; i < N; i++) {
        const el = refs.current[i];
        if (!el) continue;
        const o = wrap(i - s.pos), ao = Math.abs(o);
        if (ao > C.visible + 0.5) {
          el.style.opacity = "0";
          el.style.pointerEvents = "none";
          continue;
        }
        const sc = Math.max(0.4, 1 - ao * C.shrink);
        el.style.transform = `translateX(${o * C.gap * s.scale}px) translateY(${ao * C.drop * s.scale}px) translateZ(${-ao * C.depth * s.scale}px) rotateY(${-o * C.rotate}deg) scale(${sc})`;
        el.style.opacity = String(Math.max(0, 1 - ao * C.fade));
        el.style.filter = `brightness(${Math.max(0.3, 1 - ao * C.dim)}) saturate(${1 + (1 - Math.min(1, ao)) * 0.25})`;
        el.style.zIndex = String(Math.round(100 - ao * 10));
        el.style.pointerEvents = "auto";
      }
      const a = ((Math.round(s.pos) % N) + N) % N;
      halo.current?.style.setProperty("--halo", cards[a].glow);
      return a;
    };
    let raf = 0, last = -1;
    const frame = () => {
      raf = 0;
      if (!s.dragging) {
        s.pos = reduce ? s.target : s.pos + (s.target - s.pos) * C.ease;
        if (Math.abs(s.target - s.pos) < 0.001) s.pos = s.target;
      }
      const a = paint();
      if (a !== last) {
        last = a;
        setActive(a);
      }
      if (s.dragging || s.pos !== s.target) raf = requestAnimationFrame(frame);
    };
    wake.current = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };
    wake.current();
    const timer = window.setInterval(() => {
      const typing = document.activeElement?.matches("input, textarea, select");
      if (reduce || s.hover || s.dragging || document.hidden || pausedRef.current || typing) return;
      s.target += 1;
      wake.current();
    }, C.autoplayMs);
    const resized = new ResizeObserver(() => wake.current());
    if (stage.current) resized.observe(stage.current);
    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(timer);
      resized.disconnect();
      wake.current = () => {};
    };
  }, [N, cards]);

  useWheelTurn(deck, (direction) => {
    state.current.target += direction;
    wake.current();
  });

  const go =(i: number) => {
    const s = state.current;
    const cur = Math.round(s.target);
    let o = (((i - cur) % N) + N) % N;
    if (o > N / 2) o -= N;
    s.target = cur + o;
    wake.current();
  };

  return (
    <section
      ref={deck}
      className="relative flex flex-col items-center gap-6 overflow-hidden rounded-[28px] border border-hair bg-[radial-gradient(120%_90%_at_50%_0%,#e4ece1,#f6f1e4_70%)] px-4 pb-10 pt-12"
      aria-roledescription="carousel"
      aria-label={t("examples.button")}
      onMouseEnter={() => (state.current.hover = true)}
      onMouseLeave={() => (state.current.hover = false)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") state.current.target += 1;
        else if (e.key === "ArrowLeft") state.current.target -= 1;
        else return;
        e.preventDefault();
        wake.current();
      }}
    >
      <div ref={halo} aria-hidden="true" className="pointer-events-none absolute left-1/2 top-[40%] h-[420px] w-[620px] -translate-x-1/2 -translate-y-1/2 opacity-55 blur-2xl transition-[background] duration-700" style={{ background: "radial-gradient(closest-side, var(--halo, #2dd4bf), transparent 72%)" }} />
      <div
        ref={stage}
        className="relative h-[340px] w-full touch-pan-y select-none"
        style={{ perspective: C.persp }}
        role="group"
        aria-label={t("deck.browse")}
        onPointerDown={(e) => {
          const s = state.current;
          s.dragging = true;
          s.moved = false;
          s.lastX = s.startX = e.clientX;
          s.vel = 0;
          e.currentTarget.setPointerCapture(e.pointerId);
          wake.current();
        }}
        onPointerMove={(e) => {
          const s = state.current;
          if (!s.dragging) return;
          const dx = e.clientX - s.lastX;
          s.lastX = e.clientX;
          if (Math.abs(e.clientX - s.startX) > 5) s.moved = true;
          const d = -dx * C.sensitivity;
          s.pos += d;
          s.vel = d;
        }}
        onPointerUp={() => {
          const s = state.current;
          if (!s.dragging) return;
          s.dragging = false;
          s.target = Math.round(s.pos + s.vel * 8);
          s.vel = 0;
          wake.current();
        }}
        onPointerCancel={() => {
          state.current.dragging = false;
          wake.current();
        }}
      >
        <div className="absolute left-1/2 top-1/2 h-0 w-0" style={{ transformStyle: "preserve-3d" }}>
          {cards.map((c, i) => (
            <button
              key={c.key}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              aria-label={t("deck.item", { label: c.label, i: formatNumber(i + 1), n: formatNumber(N) })}
              className="absolute -left-[130px] -top-[165px] h-[330px] w-[260px] rounded-[26px] p-0 text-left"
              style={{ background: `linear-gradient(160deg, ${c.c1}, ${c.c2})`, boxShadow: "0 30px 60px -22px rgba(44,58,52,.55)" }}
              onClick={() => {
                if (state.current.moved) return;
                if (i === active) onOpen(i);
                else go(i);
              }}
            >
              <span className="absolute inset-0 rounded-[26px] bg-[linear-gradient(to_top,rgba(5,7,12,.85),rgba(5,7,12,0)_60%)]" />
              <span className="relative flex h-full flex-col justify-between p-5 text-white">{c.content}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="relative z-10 flex flex-col items-center gap-4 text-center" aria-live="polite">
        {caption(active)}
        <button type="button" className="btn btn-primary" onClick={() => onOpen(active)}>
          {cta}
        </button>
      </div>
    </section>
  );
}
