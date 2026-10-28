import type { ReactNode } from "react";
import { formatNumber, languageName, t, useI18n, type MessageKey } from "../../i18n";
import { BLAME, GRADE_COLOR, LANE, num, pct, STAGES, STATUS, VERDICT } from "../../lib/format";
import type { Claim, Report } from "../../lib/types";

export function Panel({ title, children, className = "", tone, tour }: { title?: ReactNode; children: ReactNode; className?: string; tone?: string; tour?: string }) {
  return (
    <section data-tour={tour} className={`card flex flex-col gap-3 p-5 ${className}`} style={tone ? { borderColor: `color-mix(in oklab, ${tone} 40%, transparent)` } : undefined}>
      {title && <h3 className="m-0 text-[13px] font-normal font-sans text-fog-400">{title}</h3>}
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
  useI18n();
  const risk = report.domain?.calibrated_risk ?? report.risk;
  const color = VERDICT[report.verdict].color;
  const marks: [string, number][] = report.guarantee
    ? [["catch", report.guarantee.catch_threshold], ["alarm", report.guarantee.alarm_threshold]]
    : [["decision", report.domain?.decision ?? report.response_threshold]];
  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-2.5 rounded-full bg-ink-600" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={risk} aria-label={t("panels.riskMeter")}>
        <div className="absolute inset-y-0 start-0 rounded-full transition-[width] duration-700" style={{ width: `${risk * 100}%`, background: color }} />
        {marks.map(([name, x]) => (
          <div key={name} className="absolute -inset-y-1 w-0.5 bg-fog-100" style={{ insetInlineStart: `${Math.min(99.5, x * 100)}%` }} title={t("panels.markTitle", { name: t(`panels.mark.${name}` as MessageKey), x: num(x) })} />
        ))}
      </div>
      <div className="flex justify-between font-mono text-[11px] text-fog-400">
        <span>{formatNumber(0)}</span>
        {marks.map(([name, x]) => (
          <span key={name}>
            {t(`panels.mark.${name}` as MessageKey)} {num(x)}
          </span>
        ))}
        <span>{formatNumber(1)}</span>
      </div>
    </div>
  );
}

export function VerdictCard({ report }: { report: Report }) {
  useI18n();
  const v = VERDICT[report.verdict];
  const grade = report.card?.grade;
  const risk = report.domain?.calibrated_risk ?? report.risk;
  const g = report.guarantee;
  return (
    <Panel tone={v.color} tour="verdict">
      <div className="flex items-center gap-4">
        {grade && (
          <div className="grid h-[72px] w-[72px] shrink-0 place-items-center rounded-[18px] text-[40px] font-medium" style={{ background: `color-mix(in oklab, ${GRADE_COLOR[grade]} 16%, transparent)`, color: GRADE_COLOR[grade] }} aria-label={t("panels.grade", { g: grade })}>
            {grade}
          </div>
        )}
        <div className="flex min-w-0 flex-col gap-1">
          <span className="text-lg font-medium" style={{ color: v.color }}>
            {v.label}
          </span>
          <span className="text-[13px] text-fog-300">
            {report.domain
              ? t("panels.riskDomain", { r: num(risk), name: report.domain.name, n: formatNumber(report.domain.examples), alone: report.domain.model_risk != null ? t("panels.riskAlone", { m: num(report.domain.model_risk) }) : "" })
              : t("panels.riskModel", { r: num(risk) })}
          </span>
        </div>
      </div>
      <RiskGauge report={report} />
      {g && (
        <p className="m-0 text-[13px] leading-relaxed text-fog-300">
          {g.flagged_with_alarm_guarantee
            ? t("panels.alarm", { a: pct(g.alpha) })
            : g.flagged_with_catch_guarantee
              ? t("panels.catchAbove", { a: pct(g.alpha) })
              : t("panels.catchBelow", { a: pct(g.alpha) })}{" "}
          <span className="text-fog-400">{t("panels.conformal", { on: g.calibrated_on })}</span>
        </p>
      )}
      {report.triage && (
        <div className="flex items-start gap-3 rounded-2xl bg-ink-700/70 px-4 py-3">
          <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ background: `color-mix(in oklab, ${LANE[report.triage.lane].color} 18%, transparent)`, color: LANE[report.triage.lane].color }}>
            {LANE[report.triage.lane].label}
          </span>
          <span className="text-[13px] leading-relaxed text-fog-300" dir="auto">{report.triage.reason}</span>
        </div>
      )}
    </Panel>
  );
}

const DIMENSIONS = new Set(["grounding", "claims supported", "source relevance", "completeness", "certainty", "source agreement", "citations", "agent trajectory"]);

export function ReliabilityCard({ report }: { report: Report }) {
  useI18n();
  if (!report.card) return null;
  return (
    <Panel title={t("panels.reliability")}>
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        {report.card.dimensions.map((d) => {
          const color = d.score == null ? "var(--color-ink-500)" : d.score < 0.4 ? "var(--color-bad)" : d.score < 0.8 ? "var(--color-warn)" : "var(--color-ok)";
          return (
            <li key={d.name} className="flex flex-col gap-1.5" title={d.note}>
              <div className="flex justify-between gap-3 text-sm">
                <span>{DIMENSIONS.has(d.name) ? t(`dimension.${d.name}` as MessageKey) : d.name}</span>
                <span className="font-mono text-fog-300">{num(d.score)}</span>
              </div>
              <Bar value={d.score ?? 0} color={color} />
              <span className="text-xs text-fog-400" dir="auto">{d.note}</span>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

export function DiagnosisPanel({ report }: { report: Report }) {
  useI18n();
  const d = report.diagnosis;
  if (!d) return null;
  return (
    <Panel title={t("panels.blame")} tour="blame">
      <span className="text-base font-medium">{BLAME[d.blame]}</span>
      <span className="text-sm leading-relaxed text-fog-300" dir="auto">{d.message}</span>
      {d.relevance != null && <span className="font-mono text-xs text-fog-400">{t("panels.relevance", { r: num(d.relevance), t: num(0.43) })}</span>}
    </Panel>
  );
}

export function OmissionsPanel({ report }: { report: Report }) {
  useI18n();
  const c = report.completeness;
  if (!c || (!c.missing.length && !c.omitted_caveats.length)) return null;
  return (
    <Panel title={t("panels.omissions")}>
      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-sm leading-relaxed text-fog-200">
        {c.omitted_caveats.map((x) => (
          <li key={`c-${x}`} className="rounded-xl bg-warn/8 px-3 py-2 text-warn-ink">
            {t("panels.dropped", { x })}
          </li>
        ))}
        {c.missing.map((x) => (
          <li key={x} dir="auto">
            {t("panels.quote", { x })}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function ConflictsPanel({ report }: { report: Report }) {
  useI18n();
  if (!report.conflicts.length) return null;
  return (
    <Panel title={t("panels.conflicts")} tone="var(--color-split)" tour="conflicts">
      {report.conflicts.map((c, i) => (
        <div key={i} className="flex flex-col gap-1.5 text-sm leading-relaxed">
          <span>
            <b className="font-medium text-split">{c.first_value}</b>
            {t("panels.conflictIn", { doc: c.first_document, text: c.first })}
          </span>
          <span>
            <b className="font-medium text-split">{c.second_value}</b>
            {t("panels.conflictIn", { doc: c.second_document, text: c.second })}
          </span>
        </div>
      ))}
    </Panel>
  );
}

export function SharesPanel({ report }: { report: Report }) {
  useI18n();
  const shares = report.claims
    .map((c, i) => ({ i, text: c.text, value: c.contribution }))
    .filter((s): s is { i: number; text: string; value: number } => s.value != null && s.value > 0.005)
    .sort((a, b) => b.value - a.value)
    .slice(0, 5);
  if (!shares.length) return null;
  const top = shares[0].value;
  return (
    <Panel title={t("panels.shares")}>
      <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
        {shares.map((s) => (
          <li key={s.i} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-3 text-[13px]">
              <span className="truncate text-fog-200" dir="auto">{s.text}</span>
              <span className="font-mono text-fog-300" dir="ltr">+{num(s.value)}</span>
            </div>
            <Bar value={s.value / top} color="var(--color-bad)" />
          </li>
        ))}
      </ul>
      <span className="text-xs text-fog-400">{t("panels.sharesNote")}</span>
    </Panel>
  );
}

/** Which check read the answer, when it was not the English engine on English texts: the multilingual check (D-138),
 *  a language without labelled answers, or a text too short to tell. */
export function languageLines(report: Report): string[] {
  const found = report.language;
  if (!found || (found.check === "english" && !found.guessed)) return [];
  const language = languageName(found.answer ?? "en");
  return [
    ...(found.guessed ? [t("check.guessed", { language })] : []),
    ...(found.check === "multilingual" ? [t("check.multilingual", { language })] : []),
    ...(found.measured ? [] : [t("check.unmeasured", { language })]),
  ];
}

export function LanguageNote({ report }: { report: Report }) {
  useI18n();
  const lines = languageLines(report);
  if (!lines.length) return null;
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-sm leading-relaxed text-warn-ink" role="note">
      {lines.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </div>
  );
}

export function WarningsPanel({ report }: { report: Report }) {
  if (!report.warnings.length) return null;
  return (
    <div className="flex flex-col gap-2" role="note">
      {report.warnings.map((w) => (
        <div key={w} className="flex gap-2.5 rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-sm leading-relaxed text-warn-ink">
          <WarnIcon />
          <span dir="auto">{w}</span>
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

export function ClaimDetail({ claim, sources }: { claim: Claim; sources: string[] }) {
  useI18n();
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
          {t("panels.claimRisk", { r: num(claim.risk) })}
          {claim.contribution != null && t("panels.adds", { v: `${claim.contribution >= 0 ? "+" : ""}${num(claim.contribution)}` })}
        </span>
      </div>
      <p className="m-0 text-[15px] leading-relaxed" dir="auto">{claim.explanation[0]?.toUpperCase() + claim.explanation.slice(1)}.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 rounded-2xl bg-ink-700/70 px-4 py-3">
          <span className="text-xs text-fog-400">
            {t("panels.evidence")}
            {docIndex ? t("panels.evidenceSource", { i: formatNumber(Number(docIndex)) }) : claim.evidence?.document_id ? ` · ${claim.evidence.document_id}` : ""}
          </span>
          <span className="text-sm leading-relaxed text-fog-200" dir="auto">{claim.evidence ? claim.evidence.text : t("panels.noEvidence")}</span>
        </div>
        <div className="flex flex-col gap-2 rounded-2xl bg-ink-700/70 px-4 py-3">
          <span className="text-xs text-fog-400">{t("panels.suggested")}</span>
          <span className="text-sm leading-relaxed text-fog-200">{t(`action.${claim.action}` as MessageKey)}</span>
          {fixes.map((f) => (
            <span key={f.start} className="self-start rounded-lg bg-ok/12 px-2.5 py-1 font-mono text-[13px] text-ok-ink" dir="ltr">
              {f.original} → {f.replacement}
            </span>
          ))}
        </div>
      </div>
      {claim.cautions.map((c) => (
        <div key={c} className="flex gap-2.5 rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-sm leading-relaxed text-warn-ink">
          <WarnIcon />
          <span dir="auto">{c[0].toUpperCase() + c.slice(1)}.</span>
        </div>
      ))}
      {sources.length > 0 && claim.citation && (
        <span className="text-xs text-fog-400">
          {t("panels.cites", { list: claim.citation.cited.map((c) => formatNumber(c)).join(t("common.comma")) })}
          {claim.citation.supported ? t("panels.citesOk") : t("panels.citesBetter", { d: formatNumber(Number(claim.citation.better_document)) })}
        </span>
      )}
    </Panel>
  );
}

export function StageProgress({ stages, queued }: { stages: { stage: string; t: number }[]; queued: boolean }) {
  useI18n();
  const order = Object.keys(STAGES);
  const seen = new Set(stages.map((s) => s.stage));
  const current = stages[stages.length - 1]?.stage;
  const took = (stage: string) => {
    const i = stages.findIndex((s) => s.stage === stage);
    return i >= 0 && i + 1 < stages.length ? stages[i + 1].t - stages[i].t : null;
  };
  return (
    <ol className="m-0 flex list-none flex-col gap-2 p-0" aria-live="polite">
      {queued && <li className="text-sm text-warn-ink">{t("panels.waiting")}</li>}
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
            {done && <span className="ms-auto font-mono text-xs text-fog-400">{t("common.seconds", { s: num(took(stage), 1) })}</span>}
          </li>
        );
      })}
    </ol>
  );
}
