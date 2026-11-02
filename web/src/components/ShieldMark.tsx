import { useId } from "react";

const SHIELD = "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z";
const CHECK = "M8.5 12l2.5 2.5 4.5-5";

/** The same shield painted on a canvas, its top left at (x, y) and `height` tall (the intro's logo). */
export function paintShield(g: CanvasRenderingContext2D, x: number, y: number, height: number) {
  const unit = height / 21.5;
  const shield = new Path2D(SHIELD);
  const check = new Path2D(CHECK);
  const gradient = (x0: number, y0: number, x1: number, y1: number, stops: [number, string][]) => {
    const fill = g.createLinearGradient(x0, y0, x1, y1);
    for (const [at, colour] of stops) fill.addColorStop(at, colour);
    return fill;
  };
  g.save();
  g.translate(x, y);
  g.scale(unit, unit);
  g.translate(-3, -1.5);
  g.lineCap = g.lineJoin = "round";
  g.save();
  g.translate(0.9, 1.1);
  g.fillStyle = gradient(0, 3, 0, 21, [[0, "#145c37"], [1, "#06301b"]]);
  g.fill(shield);
  g.restore();
  g.fillStyle = gradient(6, 3, 18, 21, [[0, "#9dffc4"], [0.45, "#2fb36a"], [1, "#0f5a34"]]);
  g.fill(shield);
  g.strokeStyle = "rgb(217 255 233 / 0.7)";
  g.lineWidth = 0.7;
  g.stroke(shield);
  g.strokeStyle = "rgb(255 255 255 / 0.75)";
  g.lineWidth = 0.9;
  g.stroke(new Path2D("M12 4.6l5.6 2.4"));
  g.save();
  g.translate(0.35, 0.5);
  g.strokeStyle = "rgb(6 48 27 / 0.55)";
  g.lineWidth = 2.2;
  g.stroke(check);
  g.restore();
  g.strokeStyle = "#f3fff8";
  g.lineWidth = 2;
  g.stroke(check);
  g.restore();
}

/** The shield, drawn solid and in depth: a darker copy below and to the side as its edge, a lit face with a bright
 *  rim, and a raised check mark. In the top bar and the footer it turns once about its upright axis every three
 *  seconds (styles.css, .shield-3d). */
export function ShieldMark({ size = 36 }: { size?: number }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="3 1.5 19 21.5" className="shield-3d shrink-0" aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-face`} x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0" stopColor="#9dffc4" />
          <stop offset="0.45" stopColor="#2fb36a" />
          <stop offset="1" stopColor="#0f5a34" />
        </linearGradient>
        <linearGradient id={`${id}-edge`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#145c37" />
          <stop offset="1" stopColor="#06301b" />
        </linearGradient>
      </defs>
      <path d={SHIELD} fill={`url(#${id}-edge)`} transform="translate(0.9 1.1)" />
      <path d={SHIELD} fill={`url(#${id}-face)`} stroke="#d9ffe9" strokeOpacity="0.7" strokeWidth="0.7" strokeLinejoin="round" />
      <path d="M12 4.6l5.6 2.4" stroke="#ffffff" strokeOpacity="0.75" strokeWidth="0.9" strokeLinecap="round" />
      <path d={CHECK} fill="none" stroke="#06301b" strokeOpacity="0.55" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" transform="translate(0.35 0.5)" />
      <path d={CHECK} fill="none" stroke="#f3fff8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
