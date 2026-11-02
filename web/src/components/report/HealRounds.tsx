import { useEffect, useState } from "react";
import { formatNumber, useI18n } from "../../i18n";
import { api, type ModelCard } from "../../lib/api";
import { GRADE_COLOR, num, pct, VERDICT } from "../../lib/format";
import type { Change, CheckInput, Healing, Report } from "../../lib/types";
import { AnswerView } from "./AnswerView";
import { Panel, RiskGauge, WarnIcon } from "./Panels";

// The rounds of healing an answer, shown on the Check an answer page in place of its report: each round's changes and
// why, and the risk after each.

type Piece = { text: string; kind: "same" | "removed" | "added"; reason?: string };

/** The previous answer with one round's changes shown inline: removed text struck through, new text marked. */
function diff(before: string, changes: Change[]): Piece[] {
  const out: Piece[] = [];
  let at = 0;
  for (const c of [...changes].sort((a, b) => a.start - b.start)) {
    if (c.start > at) out.push({ text: before.slice(at, c.start), kind: "same" });
    if (c.original) out.push({ text: c.original, kind: "removed", reason: c.reason });
    if (c.new) out.push({ text: c.new, kind: "added", reason: c.reason });
    at = Math.max(at, c.end);
  }
  if (at < before.length) out.push({ text: before.slice(at), kind: "same" });
  return out;
}

function Verdict({ report }: { report: Report }) {
  const { t } = useI18n();
  const v = VERDICT[report.verdict];
  const grade = report.card?.grade;
  return (
    <div className="flex items-center gap-3">
      {grade && (
        <span className="grid h-12 w-12 place-items-center rounded-2xl text-2xl font-medium" style={{ background: `color-mix(in oklab, ${GRADE_COLOR[grade]} 16%, transparent)`, color: GRADE_COLOR[grade] }}>
          {grade}
        </span>
      )}
      <div className="flex flex-col">
        <span className="font-medium" style={{ color: v.color }}>
          {v.label}
        </span>
        <span className="font-mono text-xs text-fog-400">{t("heal.risk", { r: num(report.risk) })}</span>
      </div>
    </div>
  );
}

export function HealRounds({ result, input, onDownload }: { result: Healing; input: CheckInput; onDownload: (name: string, data: unknown) => void }) {
  const { t, tp } = useI18n();
  const [card, setCard] = useState<ModelCard | null>(null);
  const [round, setRound] = useState(result.rounds.length - 1);

  useEffect(() => {
    api.modelCard().then(setCard).catch(() => {});
  }, []);

  const answers = result.rounds.map((r) => r.answer);
  const shown = result.rounds[round];
  const before = round > 0 ? answers[round - 1] : null;
  const healing = card?.healing?.hallucinated;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label={t("heal.rounds")} className="flex flex-wrap gap-1 rounded-full border border-hair bg-ink-800 p-1">
          {result.rounds.map((_, i) => (
            <button
              key={i}
              role="tab"
              aria-selected={round === i}
              className={`min-h-10 rounded-full px-4 text-sm transition-colors ${round === i ? "bg-beam-400 text-beam-900" : "text-fog-300 hover:text-fog-100"}`}
              onClick={() => setRound(i)}
            >
              {i === 0 ? t("heal.original") : t("heal.round", { i: formatNumber(i) })}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn btn-ghost" onClick={() => navigator.clipboard?.writeText(result.answer)}>
            {t("heal.copy")}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => onDownload("truth-guardian-healing.json", { input, healing: result })}>
            {t("common.download")}
          </button>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Panel key={round} title={round === 0 ? t("heal.originalAnswer") : tp("heal.roundTitle", shown.changes.length, { i: formatNumber(round) })}>
            {round === 0 || !before ? (
              <AnswerView answer={answers[0]} claims={shown.report.claims} />
            ) : (
              <p className="m-0 whitespace-pre-wrap text-[19px] leading-[1.95] text-fog-200" dir="auto">
                {diff(before, shown.changes).map((p, i) =>
                  p.kind === "same" ? (
                    <span key={i}>{p.text}</span>
                  ) : p.kind === "removed" ? (
                    <del key={i} title={p.reason} className="text-fog-400 decoration-bad decoration-2">
                      {p.text}
                    </del>
                  ) : (
                    <ins key={i} title={p.reason} className="rounded-[4px] bg-ok/15 px-0.5 text-ok-ink no-underline">
                      {p.text}
                    </ins>
                  ),
                )}
              </p>
            )}
          </Panel>
          {round > 0 && (
            <Panel key={`why-${round}`} title={t("heal.why")}>
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {shown.changes.map((c, i) => (
                  <li key={i} className="flex flex-col gap-1 rounded-2xl bg-ink-700/70 px-4 py-3">
                    <span className="font-mono text-[13px] text-fog-200" dir="auto">{c.new ? `“${c.original}” → “${c.new}”` : `− “${c.original.length > 120 ? c.original.slice(0, 117) + "…" : c.original}”`}</span>
                    <span className="text-[13px] text-fog-400" dir="auto">{c.reason[0].toUpperCase() + c.reason.slice(1)}.</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          {round === result.rounds.length - 1 && round > 0 && (
            <Panel title={t("heal.healed")}>
              <AnswerView answer={result.answer} claims={shown.report.claims} />
              {shown.report.verdict !== "grounded" && (
                <div className="flex gap-2.5 rounded-2xl border border-warn/25 bg-warn/8 px-4 py-3 text-sm leading-relaxed text-warn-ink">
                  <WarnIcon />
                  <span>{t("heal.stopped")}</span>
                </div>
              )}
            </Panel>
          )}
        </div>
        <aside className="flex min-w-0 flex-col gap-4">
          <Panel title={t("heal.riskRounds")} tour="heal-rounds">
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {result.rounds.map((r, i) => (
                <li key={i}>
                  <button type="button" onClick={() => setRound(i)} className={`flex w-full flex-col gap-2 rounded-2xl p-3 text-start ${round === i ? "bg-ink-700" : "hover:bg-ink-700/50"}`}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-fog-300">{i === 0 ? t("heal.original") : t("heal.round", { i: formatNumber(i) })}</span>
                      <Verdict report={r.report} />
                    </div>
                    <RiskGauge report={r.report} />
                  </button>
                </li>
              ))}
            </ol>
          </Panel>
          {healing && (
            <Panel title={t("heal.measuredTitle")}>
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {t("heal.measured", { n: formatNumber(healing.n as number), a: pct(healing.grounded_after_among_flagged as number), b: pct(healing.edit_recall as number), c: pct(healing.edit_precision as number) })}
              </p>
            </Panel>
          )}
        </aside>
      </div>
    </div>
  );
}
