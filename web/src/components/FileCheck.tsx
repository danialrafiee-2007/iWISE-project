import type { CSSProperties } from "react";
import InputPanel from "./InputPanels";

const TONE = { "--tone": "#5eead4", "--tone-rgb": "94,234,212" } as CSSProperties;

/** Reading a recording or an image and checking an answer about it (D-135): the landing page's panel, full size. It is
 *  drawn for the landing page's night, so it keeps that ground here too. */
export default function FileCheck({ kind }: { kind: "audio" | "image" }) {
  return (
    <div className="theme-night flex h-[min(760px,calc(100dvh-230px))] min-h-[520px] flex-col rounded-[24px] border border-hair bg-ink-950 p-4 shadow-[var(--shadow-card)] sm:p-6" style={TONE}>
      <InputPanel kind={kind} />
    </div>
  );
}
