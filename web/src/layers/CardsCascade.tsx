import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { formatNumber, t } from "../i18n";
import { useWheelTurn } from "./useWheelTurn";

// GetLayers "Cards Cascade", adapted: the same fold geometry (a back stack that lies away from the crest, dismissed
// cards folding forward over the lip into the pit), driven by the chosen card instead of page scroll, so it fits a
// tool page. The mouse wheel over it turns the cards, round and round (useWheelTurn), and it draws only while they
// move. Cards carry our content; their faces are gradients instead of the bundle's photos.

const G = { crestTilt: -18, crestY: 0.2, crestZ: 0.02, backDecay: 0.8, backTilt: 50, backRise: 1.02, backDepth: 1.05, backShrink: 0.16, frontDrop: 0.86, frontFold: 120, frontFwd: 0.3, fadeStart: 1.3, fadeEnd: 2.2, backFade: 9 };
const EASE = 0.14;
const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

function place(el: HTMLElement, p: number, H: number) {
  let tilt: number, ty: number, tz: number, scale: number, opacity: number, sheen: number, z: number;
  if (p >= 0) {
    const a = 1 - Math.exp(-p * G.backDecay);
    tilt = G.crestTilt - G.backTilt * a;
    ty = H * (G.crestY - G.backRise * a);
    tz = H * (G.crestZ - G.backDepth * a);
    scale = 1 - G.backShrink * a;
    sheen = 0.5 + 0.4 * a;
    opacity = clamp(1 - (p - G.backFade) * 0.5, 0, 1);
    z = 1000 - Math.round(p * 10);
  } else {
    const q = -p;
    tilt = G.crestTilt + G.frontFold * q;
    ty = H * (G.crestY + G.frontDrop * q);
    const fwd = Math.sin(clamp(q, 0, 1) * Math.PI * 0.5);
    tz = H * (G.crestZ + G.frontFwd * fwd);
    scale = 1 + 0.05 * fwd;
    sheen = 0.5 - 0.3 * clamp(q, 0, 1);
    opacity = 1 - clamp((q - G.fadeStart) / (G.fadeEnd - G.fadeStart), 0, 1);
    z = 2000 + Math.round(q * 10);
  }
  el.style.opacity = String(opacity);
  el.style.zIndex = String(z);
  el.style.visibility = opacity < 0.01 ? "hidden" : "visible";
  el.style.setProperty("--sheen", sheen.toFixed(3));
  el.style.transform = `translateY(${ty.toFixed(1)}px) translateZ(${tz.toFixed(1)}px) rotateX(${tilt.toFixed(2)}deg) scale(${scale.toFixed(3)})`;
}

export interface CascadeCard {
  key: string;
  fill: string;
  content: ReactNode;
  label: string;
}

export function CardsCascade({ cards, active, onActive, height = 420 }: { cards: CascadeCard[]; active: number; onActive: (i: number) => void; height?: number }) {
  const root = useRef<HTMLDivElement>(null);
  const refs = useRef<(HTMLElement | null)[]>([]);
  const progress = useRef(active);
  const cardH = Math.round(height * 0.6);
  const cardW = Math.round(cardH / 1.16);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    const render = () => {
      progress.current += (active - progress.current) * (reduce ? 1 : EASE);
      if (Math.abs(active - progress.current) < 0.0005) progress.current = active;
      refs.current.forEach((el, i) => el && place(el, i - progress.current, cardH));
      if (progress.current !== active) raf = requestAnimationFrame(render);
    };
    render();
    return () => cancelAnimationFrame(raf);
  }, [cardH, active]);

  useWheelTurn(root, (direction) => onActive((active + direction + cards.length) % cards.length));

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") onActive(Math.min(cards.length - 1, active + 1));
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") onActive(Math.max(0, active - 1));
    else return;
    e.preventDefault();
  };

  return (
    <div ref={root} className="relative flex items-stretch gap-4" style={{ height }}>
      <div className="relative min-w-0 flex-1 overflow-hidden rounded-[24px] bg-[radial-gradient(130%_100%_at_50%_10%,#e4ece1_0%,#efe6d3_78%)]" style={{ perspective: Math.max(1200, height * 2.8), perspectiveOrigin: "50% 38%" }} tabIndex={0} onKeyDown={onKey} aria-roledescription="carousel" aria-label={t("fool.tricks")}>
        <div className="absolute left-1/2 top-[44%] h-0 w-0" style={{ transformStyle: "preserve-3d" }}>
          {cards.map((c, i) => (
            <article
              key={c.key}
              ref={(el) => {
                refs.current[i] = el;
              }}
              aria-hidden={i !== active}
              className="absolute"
              style={{ width: cardW, height: cardH, left: -cardW / 2, top: -cardH / 2, transformStyle: "preserve-3d", willChange: "transform, opacity", backfaceVisibility: "hidden" }}
              onClick={() => onActive(i)}
            >
              <div className="cascade-face absolute inset-0 overflow-hidden rounded-[26px]" style={{ background: c.fill }}>
                <div className="absolute inset-0 bg-[linear-gradient(to_top,rgba(8,10,18,.82)_0%,rgba(8,10,18,.3)_34%,rgba(8,10,18,0)_60%)]" />
                <div className="relative z-[2] flex h-full flex-col justify-between p-5 text-white">{c.content}</div>
              </div>
            </article>
          ))}
        </div>
        <div className="sr-only" aria-live="polite">
          {t("fool.trickOf", { i: formatNumber(active + 1), n: formatNumber(cards.length), label: cards[active]?.label ?? "" })}
        </div>
      </div>
      <div className="flex flex-col items-center justify-center gap-3" role="tablist" aria-label={t("fool.chooseTrick")}>
        <span className="font-mono text-2xl font-medium tabular-nums text-fog-100">
          <span key={active}>{String(active + 1).padStart(2, "0")}</span>
          <span className="text-sm text-fog-400">/{String(cards.length).padStart(2, "0")}</span>
        </span>
        {cards.map((c, i) => (
          <button
            key={c.key}
            type="button"
            role="tab"
            aria-selected={i === active}
            aria-label={c.label}
            title={c.label}
            onClick={() => onActive(i)}
            className={`grid h-6 w-6 place-items-center rounded-full ${i === active ? "" : "hover:bg-ink-700"}`}
          >
            <span className={`block rounded-full transition-all ${i === active ? "h-3 w-3 bg-beam-400 shadow-[0_0_0_4px_rgb(69_107_86_/_0.18),0_0_12px_rgb(69_107_86_/_0.45)]" : "h-1.5 w-1.5 bg-ink-500"}`} />
          </button>
        ))}
      </div>
    </div>
  );
}
