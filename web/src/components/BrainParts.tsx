import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useI18n, type MessageKey } from "../i18n";
import { NeuralBrain, type BrainSpot } from "../layers/brain/NeuralBrain";

// The landing page's brain, made to answer: a click on it brings it forward and parts it into four, one part per
// challenge input (upper left text, upper right sound, lower left images, lower right video, mirrored on right-to-left
// pages). Under the pointer a part lights up and shows its name; held there, a small card says what the engine does
// with that input, joined to the part by a line, after iridology.app's iris chart. A click outside, Escape or
// scrolling on closes it. The names and cards sit above the page; the brain itself stays in its background layer.

const PARTS: { name: MessageKey; about: MessageKey }[] = [
  { name: "nav.text", about: "brain.text" },
  { name: "nav.audio", about: "brain.audio" },
  { name: "nav.image", about: "brain.image" },
  { name: "nav.video", about: "brain.video" },
];
const DWELL = 450; // ms the pointer rests on a part before its card opens
const CARD = 260;
const GAP = 44;
const EDGE = 16;
// Pointer tests in units of the parts' reach (the centre's distance to the farthest part's centre), which follows the
// brain's drawn size: the closed brain answers within 1.35 of it, the open one within 1.4, and a click past 1.6
// closes it.
const CLOSED = 1.35;
const OPEN = 1.4;
const OUTSIDE = 1.6;
const reachOf = (s: BrainSpot) => Math.max(...s.pieces.map((p) => Math.hypot(p.x - s.x, p.y - s.y)), 1);
// The pointer on the page's own controls or on the opening words never reaches the brain.
const CONTROLS = "a, button, input, textarea, select, label, header, [role=dialog], [role=menu], .hero-words";

export function BrainParts({ progress, paused, mirror }: { progress: number; paused: boolean; mirror: boolean }) {
  const { t } = useI18n();
  const [spot, setSpot] = useState<BrainSpot | null>(null);
  const [open, setOpen] = useState(false);
  const [piece, setPiece] = useState(-1);
  const [over, setOver] = useState(false);
  const [told, setTold] = useState(false);
  const spotRef = useRef(spot);
  const openRef = useRef(open);
  spotRef.current = spot;
  openRef.current = open;

  // Only in the opening frame: once the page scrolls on, the camera flies away and the brain closes.
  const away = progress > 0.02;
  useEffect(() => {
    if (away) setOpen(false);
  }, [away]);
  useEffect(() => {
    if (!open) setPiece(-1);
  }, [open]);
  useEffect(() => {
    setTold(false);
    if (piece < 0) return;
    const timer = window.setTimeout(() => setTold(true), DWELL);
    return () => window.clearTimeout(timer);
  }, [piece]);

  useEffect(() => {
    const nearest = (s: BrainSpot, x: number, y: number) => {
      let best = -1;
      let distance = Infinity;
      s.pieces.forEach((p, i) => {
        const d = Math.hypot(x - p.x, y - p.y);
        if (d < distance) [best, distance] = [i, d];
      });
      return best;
    };
    const onMove = (e: PointerEvent) => {
      const s = spotRef.current;
      if (!s || e.pointerType !== "mouse") return;
      const onControl = (e.target as Element | null)?.closest?.(CONTROLS);
      const d = Math.hypot(e.clientX - s.x, e.clientY - s.y) / reachOf(s);
      if (!openRef.current) {
        setOver(!onControl && d < CLOSED);
        return;
      }
      setOver(false);
      setPiece(!onControl && d < OPEN ? nearest(s, e.clientX, e.clientY) : -1);
    };
    const onClick = (e: MouseEvent) => {
      const s = spotRef.current;
      if (!s || (e.target as Element | null)?.closest?.(CONTROLS)) return;
      const d = Math.hypot(e.clientX - s.x, e.clientY - s.y) / reachOf(s);
      if (!openRef.current) {
        if (d < CLOSED) {
          setOpen(true);
          setOver(false);
        }
      } else if (d > OUTSIDE) setOpen(false);
      else {
        // A tap (no hover on touch screens) picks the part and opens its card at once.
        setPiece(nearest(s, e.clientX, e.clientY));
        window.setTimeout(() => setTold(true));
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("click", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("click", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  // The brain is drawn behind the page, so the hand cursor is set on the whole page while it can be clicked.
  const pointing = over || piece >= 0;
  useEffect(() => {
    if (!pointing) return;
    document.documentElement.style.cursor = "pointer";
    return () => {
      document.documentElement.style.cursor = "";
    };
  }, [pointing]);

  const shown = spot && !away ? spot : null;
  // Hints go under the brain, kept above the window's bottom edge.
  const below = shown ? Math.min(shown.y + reachOf(shown) * (open ? 1.55 : 1.4), window.innerHeight - 56) : 0;
  return (
    <>
      <NeuralBrain progress={progress} paused={paused} mirror={mirror} open={open} piece={piece} onSpot={setSpot} />
      {shown &&
        createPortal(
          <div className="theme-night pointer-events-none fixed inset-0 z-30" aria-hidden="true">
            {!open && over && <Hint x={shown.x} y={below} text={t("brain.hint")} />}
            {open && piece < 0 && <Hint x={shown.x} y={below} text={t("brain.pick")} />}
            {open &&
              shown.pieces.map((p, i) => (
                <span
                  key={i}
                  className={`absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap font-sans font-semibold transition-[opacity,font-size] duration-300 ${
                    i === piece ? "text-[28px] text-[#eafff6] opacity-100 [text-shadow:0_0_12px_rgba(57,255,136,.85),0_0_28px_rgba(20,184,166,.6)]" : "text-sm text-fog-200 opacity-55 [text-shadow:0_1px_6px_rgba(0,0,0,.8)]"
                  }`}
                  style={{ left: p.x, top: p.y }}
                >
                  {t(PARTS[i].name)}
                </span>
              ))}
            {open && piece >= 0 && told && <Callout spot={shown} piece={piece} title={t(PARTS[piece].name)} text={t(PARTS[piece].about)} mirror={mirror} />}
          </div>,
          document.body,
        )}
    </>
  );
}

function Hint({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <span className="absolute -translate-x-1/2 animate-[rise_.4s_ease-out_both] whitespace-nowrap rounded-full border border-[#5eead4]/35 bg-black/55 px-3.5 py-1.5 font-sans text-xs text-fog-100 backdrop-blur-sm" style={{ left: x, top: y }}>
      {text}
    </span>
  );
}

/** A ringed marker on the part, a line, and the card: on the side away from the page's words (right of the marker on
 *  left-to-right pages) when the screen has room there, else on the other; kept inside the window. */
function Callout({ spot, piece, title, text, mirror }: { spot: BrainSpot; piece: number; title: string; text: string; mirror: boolean }) {
  const at = spot.pieces[piece];
  const away = mirror ? -1 : 1;
  const room = away > 0 ? window.innerWidth - at.x - GAP - EDGE : at.x - GAP - EDGE;
  const side = room >= CARD ? away : -away;
  const left = Math.min(Math.max(EDGE, side > 0 ? at.x + GAP : at.x - GAP - CARD), window.innerWidth - CARD - EDGE);
  const top = Math.min(Math.max(EDGE + 72, at.y - 20), window.innerHeight - 150); // below the top bar
  const end = { x: side > 0 ? left : left + CARD, y: top + 16 };
  return (
    <>
      <svg className="absolute inset-0 h-full w-full overflow-visible">
        <line x1={at.x} y1={at.y} x2={end.x} y2={end.y} stroke="#5eead4" strokeWidth="1.2" strokeOpacity="0.85" />
        <circle cx={at.x} cy={at.y} r="15" fill="none" stroke="#5eead4" strokeOpacity="0.35" />
        <circle cx={at.x} cy={at.y} r="9" fill="rgba(94,234,212,.18)" stroke="#5eead4" strokeOpacity="0.8" />
        <circle cx={at.x} cy={at.y} r="3.5" fill="#eafff6" />
      </svg>
      <div className="absolute animate-[rise_.35s_ease-out_both] rounded-2xl border border-[#5eead4]/30 bg-[rgba(4,14,11,.78)] p-4 shadow-[0_18px_40px_-16px_rgba(0,0,0,.8)] backdrop-blur-md" style={{ left, top, width: CARD }}>
        <h3 className="m-0 font-sans text-lg font-semibold text-[#eafff6]">{title}</h3>
        <p className="m-0 mt-1.5 text-[14px] leading-relaxed text-fog-200">{text}</p>
      </div>
    </>
  );
}
