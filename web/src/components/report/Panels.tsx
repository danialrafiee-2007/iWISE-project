import type { ReactNode } from "react";
import { BLAME, GRADE_COLOR, LANE, num, pct, STAGES, STATUS, VERDICT } from "../../lib/format";
import type { Claim, Report } from "../../lib/types";

export function Panel({ title, children, className = "", tone, tour }: { title?: ReactNode; children: ReactNode; className?: string; tone?: string; tour?: string }) {
  return (
    <section data-tour={tour} className={`card flex flex-col gap-3 p-5 ${className}`} style={tone ? { borderColor: `color-mix(in oklab, ${tone} 40%, transparent)` } : undefined}>
      {title && <h3 className="m-0 text-[13px] font-normal text-fog-400">{title}</h3>}
      {children}
    </section>
  );
}

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 rounded-full bg-ink-600" aria-hidden="true">
      <div className="h-1.5 rounded-full transition-[width] duration-500" style={{ width: `${Math.max(3, Math.min(100, value * 100))}%`, background: color }} />
    </div>
  );
}

export function RiskGauge({ report }: { report: Report }) {
  const risk = report.domain?.calibrated_risk ?? report.risk;
  const color = VERDICT[report.verdict].color;
  const marks: [string, number][] = report.guarantee
    ? [["catch", report.guarantee.catch_threshold], ["alarm", report.guarantee.alarm_threshold]]
    : [["decision", report.domain?.decision ?? report.response_threshold]];
  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-2.5 rounded-full bg-ink-600" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={risk} aria-label="Hallucination risk">
        <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-700" style={{ width: `${risk * 100}%`, background: color }} />
        {marks.map(([name, x]) => (
          <div key={name} className="absolute -inset-y-1 w-0.5 bg-fog-100" style={{ left: `${Math.min(99.5, x * 100)}%` }} title={`${name} line ${x.toFixed(2)}`} />
        ))}
      </div>
      <div className="flex justify-between font-mono text-[11px] text-fog-400">
        <span>0</span>
        {marks.map(([name, x]) => (
          <span key={name}>
            {name} {x.toFixed(2)}
          </span>
        ))}
        <span>1</span>
      </div>
    </div>
  );
}

export function VerdictCard({ report }: { report: Report }) {
  const v = VERDICT[report.verdict];
  const grade = report.card?.grade;
  const risk = report.domain?.calibrated_risk ?? report.risk;
  const g = report.guarantee;
  return (
    <Panel tone={v.color} tour="verdict">
      <div className="flex items-center gap-4">
        {grade && (
          <div className="grid h-[72px] w-[72px] shrink-0 place-items-center rounded-[18px] text-[40px] font-medium" style={{ background: `color-mix(in oklab, ${GRADE_COLOR[grade]} 16%, transparent)`, color: GRADE_COLOR[grade] }} aria-label={`Grade ${grade}`}>
            {grade}
          </div>
        )}
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-lg font-medium" style={{ color: v.color }}>
            {v.label}
          </span>
          <span className="text-[13px] text-fog-300">
            Risk {risk.toFixed(2)}
            {report.domain
              ? ` for ${report.domain.name}, from its profile of ${report.domain.examples} labelled answers${report.domain.model_risk != null ? ` (the RAGTruth model alone: ${report.domain.model_risk.toFixed(2)})` : ""}: the probability that this answer contains a hallucination.`
              : ": the model's probability that this answer contains a hallucination."}
          </span>
        </div>
      </div>
      <RiskGauge report={report} />
      {g && (
        <p className="m-0 text-[13px] leading-relaxed text-fog-300">
          {g.flagged_with_alarm_guarantee
            ? `Above the alarm line: at most ${pct(g.alpha)} of grounded answers score this high.`
            : g.flagged_with_catch_guarantee
              ? `Above the catch line: flagging here misses at most ${pct(g.alpha)} of hallucinated answers.`
              : `Below the catch line: answers this low are where at most ${pct(g.alpha)} of hallucinated answers fall.`}{" "}
          <span className="text-fog-400">Conformal guarantee, calibrated on {g.calibrated_on}.</span>
        </p>
      )}
      {report.triage && (
        <div className="flex items-start gap-3 rounded-2xl bg-ink-700/70 px-4 py-3">
          <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ background: `color-mix(in oklab, ${LANE[report.triage.lane].color} 18%, transparent)`, color: LANE[report.triage.lane].color }}>
            {LANE[report.triage.lane].label}
          </span>
          <span className="text-[13px] leading-relaxed text-fog-300">{report.triage.reason}</span>
        </div>
      )}
    </Panel>
  );
}

const DIMENSION_LABEL: Record<string, string> = {
  grounding: "Grounding",
  "claims supported": "Claims supported",
  "source relevance": "Source relevance",
  completeness: "Completeness",
  certainty: "Certainty",
  "source agreement": "Source agreement",
  citations: "Citations",
  "agent trajectory": "Agent trajectory",
};

export function ReliabilityCard({ report }: { report: Report }) {
  if (!report.card) return null;
  return (
    <Panel title="Reliability card">
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {report.card.dimensions.map((d) => {
          const color = d.score == null ? "var(--color-ink-500)" : d.score < 0.4 ? "var(--color-bad)" : d.score < 0.8 ? "var(--color-warn)" : "var(--color-ok)";
          return (
            <li key={d.name} className="flex flex-col gap-1.5" title={d.note}>
              <div className="flex justify-between gap-3 text-sm">
                <span>{DIMENSION_LABEL[d.name] ?? d.name}</span>
                <span className="font-mono text-fog-300">{d.score == null ? "n/a" : d.score.toFixed(2)}</span>
              </div>
              <Bar value={d.score ?? 0} color={color} />
              <span className="text-xs text-fog-400">{d.note}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function DiagnosisPanel({ report }: { report: Report }) {
  const d = report.diagnosis;
  if (!d) return null;
  return (
    <Panel title="Who is to blame" tour="blame">
      <span className="text-base font-medium">{BLAME[d.blame]}</span>
      <span className="text-sm leading-relaxed text-fog-300">{d.message}</span>
      {d.relevance != null && <span className="font-mono text-xs text-fog-400">source relevance {d.relevance.toFixed(2)} (retrieval is blamed below 0.43)</span>}
    </Panel>
  );
}

export function OmissionsPanel({ report }: { report: Report }) {
  const c = report.completeness;
  if (!c || (!c.missing.length && !c.omitted_caveats.length)) return null;
  return (
    <Panel title="Left out of the answer">
      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-sm leading-relaxed text-fog-200">
        {c.omitted_caveats.map((x) => (
          <li key={`c-${x}`} className="rounded-xl bg-warn/8 px-3 py-2 text-warn">
            Dropped condition: “{x}”
          </li>
        ))}
        {c.missing.map((x) => (
          <li key={x}>“{x}”</li>
        ))}
      </ul>
    </Panel>
  );
}

export function ConflictsPanel({ report }: { report: Report }) {
  if (!report.conflicts.length) return null;
  return (
    <Panel title="The sources disagree" tone="var(--color-split)" tour="conflicts">
      {report.conflicts.map((c, i) => (
        <div key={i} className="flex flex-col gap-1.5 text-sm leading-relaxed">
          <span>
            <b className="font-medium text-split">{c.first_value}</b> in {c.first_document}: “{c.first}”
          </span>
          <span>
            <b className="font-medium text-split">{c.second_value}</b> in {c.second_document}: “{c.second}”
          </span>
        </div>
      ))}
    </Panel>
  );
}

export function SharesPanel({ report }: { report: Report }) {
  const shares = report.claims
    .map((c, i) => ({ i, text: c.text, value: c.contribution }))
    .filter((s): s is { i: number; text: string; value: number } => s.value != null && s.value > 0.005)
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
  if (!shares.length) return null;
  const top = shares[0].value;
  return (
    <Panel title="Where the risk comes from">
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
        {shares.map((s) => (
          <li key={s.i} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-3 text-[13px]">
              <span className="truncate text-fog-200">{s.text}</span>
              <span className="font-mono text-fog-300">+{s.value.toFixed(2)}</span>
            </div>
            <Bar value={s.value / top} color="var(--color-bad)" />
          </li>
        ))}
      </ul>
      <span className="text-xs text-fog-400">How much the answer's risk falls when each claim is left out.</span>
    </Panel>
  );
}

export function WarningsPanel({ report }: { report: Report }) {
  if (!report.warnings.length) return null;
  return (
    <div className="flex flex-col gap-2" role="note">
      {report.warnings.map((w) => (
        <div key={w} className="flex gap-2.5 rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-sm leading-relaxed text-amber-200">
          <WarnIcon />
          <span>{w}</span>
        </div>
      ))}
    </div>
  );
}

export const WarnIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-warn)" strokeWidth="1.8" aria-hidden="true" className="mt-0.5 shrink-0">
    <path d="M12 9v4M12 17h.01" />
    <path d="M10.3 3.9L2.4 17.5A2 2 0 004.1 20.5h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z" />
  </svg>
);

const ACTION: Record<Claim["action"], string> = {
  keep: "Keep it.",
  replace: "Replace the wrong words with the value in the sources.",
  remove: "Remove it, or find a source that supports it.",
  verify: "Check it against the sources before using it.",
};

export function ClaimDetail({ claim, sources }: { claim: Claim; sources: string[] }) {
  const s = STATUS[claim.status];
  const docIndex = claim.evidence?.document_id?.match(/^source(\d+)$/)?.[1];
  const fixes = claim.fixes.filter((f) => f.replacement);
  return (
    <Panel tone={s.color} tour="claim">
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ background: `color-mix(in oklab, ${s.color} 16%, transparent)`, color: s.color }}>
          {s.label}
        </span>
        <span className="font-mono text-xs text-fog-400">
          claim risk {claim.risk.toFixed(2)}
          {claim.contribution != null && ` · adds ${claim.contribution >= 0 ? "+" : ""}${claim.contribution.toFixed(2)} to the answer's risk`}
        </span>
      </div>
      <p className="m-0 text-[15px] leading-relaxed">{claim.explanation[0]?.toUpperCase() + claim.explanation.slice(1)}.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 rounded-2xl bg-ink-700/70 px-4 py-3">
          <span className="text-xs text-fog-400">
            Closest evidence{docIndex ? ` · source ${docIndex}` : claim.evidence?.document_id ? ` · ${claim.evidence.document_id}` : ""}
          </span>
          <span className="text-sm leading-relaxed text-fog-200">{claim.evidence ? claim.evidence.text : "No source sentence matches this claim."}</span>
        </div>
        <div className="flex flex-col gap-2 rounded-2xl bg-ink-700/70 px-4 py-3">
          <span className="text-xs text-fog-400">Suggested action</span>
          <span className="text-sm leading-relaxed text-fog-200">{ACTION[claim.action]}</span>
          {fixes.map((f) => (
            <span key={f.start} className="self-start rounded-lg bg-ok/12 px-2.5 py-1 font-mono text-[13px] text-emerald-300">
              {f.original} → {f.replacement}
            </span>
          ))}
        </div>
      </div>
      {claim.cautions.map((c) => (
        <div key={c} className="flex gap-2.5 rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-sm leading-relaxed text-amber-200">
          <WarnIcon />
          <span>{c[0].toUpperCase() + c.slice(1)}.</span>
        </div>
      ))}
      {sources.length > 0 && claim.citation && (
        <span className="text-xs text-fog-400">
          Cites source {claim.citation.cited.join(", ")}
          {claim.citation.supported ? ", which supports it." : `, but source ${claim.citation.better_document} is the one that supports it.`}
        </span>
      )}
    </Panel>
  );
}

export function StageProgress({ stages, queued }: { stages: { stage: string; t: number }[]; queued: boolean }) {
  const order = Object.keys(STAGES);
  const seen = new Set(stages.map((s) => s.stage));
  const current = stages[stages.length - 1]?.stage;
  const took = (stage: string) => {
    const i = stages.findIndex((s) => s.stage === stage);
    return i >= 0 && i + 1 < stages.length ? stages[i + 1].t - stages[i].t : null;
  };
  return (
    <ol className="m-0 flex list-none flex-col gap-2 p-0" aria-live="polite">
      {queued && <li className="text-sm text-warn">Waiting for the previous check to finish…</li>}
      {order.map((stage) => {
        const done = seen.has(stage) && stage !== current;
        const active = stage === current;
        return (
          <li key={stage} className={`flex items-center gap-3 text-sm ${done ? "text-fog-300" : active ? "text-fog-100" : "text-fog-400/60"}`}>
            <span className="grid h-5 w-5 place-items-center" aria-hidden="true">
              {done ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-ok)" strokeWidth="2.2">
                  <path d="M5 12.5l4.5 4.5L19 7.5" />
                </svg>
              ) : active ? (
                <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-beam-400" />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-ink-500" />
              )}
            </span>
            {STAGES[stage]}
            {done && <span className="ml-auto font-mono text-xs text-fog-400">{num(took(stage), 1)} s</span>}
          </li>
        );
      })}
    </ol>
  );
}
