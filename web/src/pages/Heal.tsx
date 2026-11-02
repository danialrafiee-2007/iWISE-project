import { useEffect, useState } from "react";
import { BackToCheck } from "../components/CheckLinks";
import { InputForm } from "../components/InputForm";
import { AnswerView } from "../components/report/AnswerView";
import { Panel, RiskGauge, WarnIcon } from "../components/report/Panels";
import { Riffle } from "../layers/Gradients";
import { formatNumber, useI18n } from "../i18n";
import { Heading } from "../layers/Heading";
import { api, checkBody } from "../lib/api";
import { GRADE_COLOR, num, pct, VERDICT } from "../lib/format";
import type { Change, Healing, Report } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useRouter } from "../lib/router";
import type { CheckInput } from "../lib/types";
import { useWorkspace } from "../lib/workspace";
import { downloadJson, ExamplePicker, exampleInput } from "./Analyze";
import type { ExampleBrief } from "../lib/types";
import type { ModelCard } from "../lib/api";

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

export default function Heal() {
  const { input, setInput, health, busy } = useWorkspace();
  const [examples, setExamples] = useState<ExampleBrief[]>([]);
  const [card, setCard] = useState<ModelCard | null>(null);
  const [round, setRound] = useState(0);
  const heal = useStream<Healing & { report?: Report }>();
  const { search, consume } = useRouter();
  const ready = health?.state === "ready";
  const { t, tp } = useI18n();

  useEffect(() => {
    api.examples().then((e) => setExamples(e.answers)).catch(() => {});
    api.modelCard().then(setCard).catch(() => {});
  }, []);

  const run = async (value: CheckInput = input) => {
    setRound(0);
    const result = await heal.run("/api/heal", checkBody(value), (r) => r.rounds[r.rounds.length - 1].report.verdict);
    if (result) setRound(result.rounds.length - 1);
  };

  // ?example=<id> heals that example; ?auto=1 heals the answer handed over from Analyze.
  useEffect(() => {
    const params = new URLSearchParams(search);
    const id = params.get("example");
    if (!ready || heal.running || (!id && params.get("auto") !== "1")) return;
    consume();
    if (id) {
      api.example(id).then(({ example }) => {
        const value = exampleInput(example);
        setInput(value);
        run(value);
      }).catch(() => {});
    } else if (input.answer.trim()) {
      run();
    }
  }, [ready, search]);

  const pick = async (id: string) => {
    const { example } = await api.example(id);
    setInput(exampleInput(example));
    heal.reset();
  };

  const result = heal.result;
  const checks = heal.events.filter((e) => e.type === "check").length;
  const answers = result?.rounds.map((r) => r.answer) ?? [];
  const shown = result?.rounds[round];
  const before = result && round > 0 ? answers[round - 1] : null;
  const healing = card?.healing?.hallucinated;

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <BackToCheck />
      <div className="relative isolate overflow-hidden rounded-[28px] border border-hair">
        <div className="absolute inset-0 -z-10 opacity-80">
          <Riffle paused={busy} />
        </div>
        <div className="flex flex-col gap-2 bg-gradient-to-r from-ink-950/85 via-ink-950/50 to-transparent px-6 py-7 sm:px-8">
          <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">{t("heal.title")}</Heading>
          <p className="m-0 max-w-2xl text-[15px] leading-relaxed text-fog-300">
            {t("heal.lead")}
          </p>
        </div>
      </div>

      {!result && !heal.running && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <Panel title={t("heal.pick")}>
            <ExamplePicker examples={examples} current={input.exampleId} onPick={pick} />
          </Panel>
          <Panel title={t("common.orOwn")}>
            <InputForm value={input} onChange={setInput} onSubmit={run} disabled={!ready} submitLabel={ready ? t("heal.submit") : t("common.loadingModels")} />
          </Panel>
        </div>
      )}

      {heal.running && (
        <Panel title={t("heal.healing")}>
          <p className="m-0 text-sm text-fog-300" aria-live="polite">
            {heal.queued ? t("panels.waiting") : checks <= 1 ? t("heal.checkingOriginal") : t("heal.checkingRound", { i: formatNumber(checks - 1) })}
          </p>
          <div className="h-1 overflow-hidden rounded-full bg-ink-600">
            <div className="h-1 w-1/3 animate-[slide_1.4s_ease-in-out_infinite] rounded-full bg-beam-400" />
          </div>
        </Panel>
      )}

      {heal.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
          {t("heal.failed", { error: heal.error })}
        </div>
      )}

      {result && shown && (
        <div key={`${result.original}:${result.answer}`} className="flex flex-col gap-6">
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
              <button type="button" className="btn btn-ghost" onClick={() => downloadJson("truth-guardian-healing.json", { input, healing: result })}>
                {t("common.download")}
              </button>
              <button type="button" className="btn btn-primary" onClick={() => heal.reset()}>
                {t("heal.another")}
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
                <Panel key={round} title={t("heal.why")}>
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
      )}
    </div>
  );
}
