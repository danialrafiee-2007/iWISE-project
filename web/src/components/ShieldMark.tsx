import { useId } from "react";

const SHIELD = "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z";
const CHECK = "M8.5 12l2.5 2.5 4.5-5";

/** The shield, drawn solid and in depth: a darker copy below and to the side as its edge, a lit face with a bright
 *  rim, and a raised check mark. In the top bar it turns once about its upright axis every three seconds
 *  (styles.css, .shield-3d); `turning={false}` keeps it still, as in the footer. */
export function ShieldMark({ size = 36, turning = true }: { size?: number; turning?: boolean }) {
  const id = useId();
  return (
    <svg width={size} height={size} viewBox="3 1.5 19 21.5" className={`${turning ? "shield-3d" : "shield-still"} shrink-0`} aria-hidden="true">
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
