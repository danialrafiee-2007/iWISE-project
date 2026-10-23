import { Fragment, type ReactNode } from "react";
import { STATUS } from "../../lib/format";
import type { Claim } from "../../lib/types";

type Range = [number, number];

const merge = (ranges: Range[]): Range[] => {
  const sorted = ranges.filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  const out: Range[] = [];
  for (const r of sorted) {
    const last = out[out.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else out.push([...r]);
  }
  return out;
};

/** Text of [start, end) with the given absolute ranges wrapped in <mark>. */
function marked(text: string, offset: number, start: number, end: number, ranges: Range[], markClass: string, markStyle?: React.CSSProperties): ReactNode[] {
  const out: ReactNode[] = [];
  let at = start;
  for (const [a, b] of merge(ranges)) {
    const s = Math.max(a, start), e = Math.min(b, end);
    if (e <= s) continue;
    if (s > at) out.push(text.slice(at - offset, s - offset));
    out.push(
      <mark key={s} className={markClass} style={markStyle}>
        {text.slice(s - offset, e - offset)}
      </mark>,
    );
    at = e;
  }
  if (at < end) out.push(text.slice(at - offset, end - offset));
  return out;
}

export function claimWords(claim: Claim): Range[] {
  if (claim.status === "supported") return [];
  const words: Range[] = [...claim.spans, ...claim.fixes.map((f) => [f.start, f.end] as Range)];
  return words.length ? words : claim.focus;
}

export function AnswerView({
  answer,
  claims,
  selected,
  onSelect,
  gold,
  showGold = false,
}: {
  answer: string;
  claims: Claim[];
  selected?: number | null;
  onSelect?: (index: number) => void;
  gold?: Range[];
  showGold?: boolean;
}) {
  const parts: ReactNode[] = [];
  let at = 0;
  claims.forEach((claim, i) => {
    if (claim.start > at) parts.push(<Fragment key={`gap-${i}`}>{marked(answer, 0, at, claim.start, showGold ? gold ?? [] : [], "gold")}</Fragment>);
    const s = STATUS[claim.status];
    const flagged = claim.status !== "supported";
    const isSelected = selected === i;
    const style: React.CSSProperties = {
      textDecorationLine: "underline",
      textDecorationStyle: s.line as React.CSSProperties["textDecorationStyle"],
      textDecorationColor: flagged ? s.color : "color-mix(in oklab, var(--color-ok) 45%, transparent)",
      textDecorationThickness: flagged ? 3 : 1.5,
      textUnderlineOffset: 6,
      background: isSelected ? "rgb(255 255 255 / 0.06)" : "transparent",
      color: isSelected ? "#fff" : "var(--color-fog-200)",
    };
    const words = claimWords(claim);
    const content = showGold && gold ? marked(answer, 0, claim.start, claim.end, gold, "gold") : marked(answer, 0, claim.start, claim.end, words, "rounded-[4px] px-0.5 text-white", { background: `color-mix(in oklab, ${s.color} 26%, transparent)` });
    parts.push(
      onSelect ? (
        <button
          key={`claim-${i}`}
          type="button"
          onClick={() => onSelect(i)}
          aria-pressed={isSelected}
          aria-label={`${s.label} claim, risk ${claim.risk.toFixed(2)}: ${claim.text}`}
          className="inline rounded-[4px] border-0 p-0 text-left [font:inherit] [line-height:inherit] focus-visible:outline-2"
          style={style}
        >
          {content}
        </button>
      ) : (
        <span key={`claim-${i}`} style={style}>
          {content}
        </span>
      ),
    );
    at = claim.end;
  });
  if (at < answer.length) parts.push(<Fragment key="tail">{marked(answer, 0, at, answer.length, showGold ? gold ?? [] : [], "gold")}</Fragment>);
  return <p className="m-0 whitespace-pre-wrap text-[19px] leading-[1.95]">{parts}</p>;
}

export function StatusLegend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-fog-300">
      {Object.entries(STATUS).map(([key, s]) => (
        <span key={key} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block w-5" style={{ borderBottom: `${key === "supported" ? 2 : 3}px ${s.line} ${s.color}` }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}
