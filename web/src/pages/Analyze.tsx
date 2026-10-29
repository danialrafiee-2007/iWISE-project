import { Suspense, useEffect, useRef, useState } from "react";
import { InputForm } from "../components/InputForm";
import { AnswerView, StatusLegend } from "../components/report/AnswerView";
import { ClaimDetail, ConflictsPanel, DiagnosisPanel, LanguageNote, OmissionsPanel, OnlinePanel, Panel, ReliabilityCard, SharesPanel, StageProgress, VerdictCard, WarningsPanel } from "../components/report/Panels";
import { Loupe } from "../layers/Gradients";
import { useI18n } from "../i18n";
import { Heading } from "../layers/Heading";
import { api, checkBody } from "../lib/api";
import { num, VERDICT } from "../lib/format";
import { lazyPage } from "../lib/lazyPage";
import { useRouter } from "../lib/router";
import type { CheckInput, Example, ExampleBrief, Report, Task } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useWorkspace } from "../lib/workspace";

const GlassHalo = lazyPage(() => import("../layers/scenes/GlassHalo"));

type Result = { report: Report; seconds: number; cached: boolean };
type View = Result & { input: CheckInput; gold: Example | null };

export function exampleInput(e: Example): CheckInput {
  const task = (["qa", "summary", "data2text"].includes(e.task) ? e.task : "other") as Task;
  return { question: e.question ?? "", sources: e.sources.length ? e.sources : [""], answer: e.answer, task, profile: e.profile ?? null, exampleId: e.id };
}

export function downloadJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  URL.revokeObjectURL(url);
}

export function ExamplePicker({ examples, current, onPick, disabled }: { examples: ExampleBrief[]; current?: string | null; onPick: (id: string) => void; disabled?: boolean }) {
  const { t } = useI18n();
  const groups = examples.reduce<Record<string, ExampleBrief[]>>((acc, e) => {
    const group = e.origin.startsWith("written") ? t("common.showcase") : e.origin;
    (acc[group] ??= []).push(e);
    return acc;
  }, {});
  return (
    <div className="flex flex-col gap-3">
      {Object.entries(groups).map(([group, items]) => (
        <div key={group} className="flex flex-col gap-2">
          <span className="label" dir="auto">{group}</span>
          <div className="flex flex-wrap gap-2">
            {items.map((e) => (
              <button key={e.id} type="button" className="chip" aria-pressed={current === e.id} disabled={disabled} onClick={() => onPick(e.id)} dir="auto">
                {e.title}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReportView({ report, input, gold }: { report: Report; input: CheckInput; gold?: Example | null }) {
  const firstFlagged = report.claims.findIndex((c) => c.status !== "supported");
  const [selected, setSelected] = useState<number>(firstFlagged >= 0 ? firstFlagged : 0);
  const [showGold, setShowGold] = useState(false);
  const { t, tp } = useI18n();
  useEffect(() => setSelected(firstFlagged >= 0 ? firstFlagged : 0), [report]);
  const claim = report.claims[selected];
  const goldSpans = gold?.gold_spans.map((s) => [s.start, s.end] as [number, number]) ?? [];

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="flex min-w-0 flex-col gap-4">
        <Panel tour="answer">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="m-0 text-[13px] font-normal font-sans text-fog-400">{t("analyze.answerTitle")}</h2>
            <StatusLegend />
          </div>
          <AnswerView key={showGold ? "gold" : "guardian"} answer={input.answer} claims={report.claims} selected={selected} onSelect={setSelected} gold={goldSpans} showGold={showGold} />
          {gold?.gold && (
            <div className="flex flex-wrap items-center gap-3 border-t border-hair pt-3 text-sm text-fog-300">
              <span>
                {t("analyze.goldPre")}
                <b className="font-medium text-fog-100">{gold.gold in VERDICT ? VERDICT[gold.gold as keyof typeof VERDICT].label : gold.gold}</b>
                {gold.gold_spans.length ? tp("analyze.goldSpans", gold.gold_spans.length) : ""}
                {t("analyze.goldPost")}
              </span>
              {gold.gold_spans.length > 0 && (
                <button type="button" className="chip" aria-pressed={showGold} onClick={() => setShowGold((v) => !v)}>
                  {showGold ? t("analyze.showGuardian") : t("analyze.showGold")}
                </button>
              )}
            </div>
          )}
        </Panel>
        {claim && !showGold && <ClaimDetail key={selected} claim={claim} sources={input.sources} />}
        <LanguageNote report={report} />
        <OnlinePanel report={report} />
        <WarningsPanel report={report} />
        {report.cited_answer && (
          <Panel title={t("analyze.cited")}>
            <p className="m-0 text-[15px] leading-relaxed text-fog-200" dir="auto">{report.cited_answer}</p>
          </Panel>
        )}
      </div>
      <aside className="flex min-w-0 flex-col gap-4" aria-label={t("analyze.reliability")}>
        <VerdictCard report={report} />
        <DiagnosisPanel report={report} />
        <ConflictsPanel report={report} />
        <SharesPanel report={report} />
        <OmissionsPanel report={report} />
        <ReliabilityCard report={report} />
      </aside>
    </div>
  );
}

export function Analyze() {
  const { input, setInput, health, busy } = useWorkspace();
  const { navigate, search, consume } = useRouter();
  const [examples, setExamples] = useState<ExampleBrief[]>([]);
  const [example, setExample] = useState<Example | null>(null);
  const [view, setView] = useState<View | null>(null);
  const picking = useRef(0);
  const check = useStream<Result>();
  const { t } = useI18n();
  const ready = health?.state === "ready";

  useEffect(() => {
    api.examples().then((e) => setExamples(e.answers)).catch(() => {});
  }, []);

  useEffect(() => {
    const id = new URLSearchParams(search).get("example");
    if (id) {
      consume();
      pick(id);
    }
  }, [search]);

  const run = async (value: CheckInput, gold: Example | null = null) => {
    const result = await check.run("/api/analyze", checkBody(value));
    if (result) setView({ ...result, input: value, gold });
  };

  // Only the latest click counts: an earlier example that answers late is ignored, and a check still running for it
  // is cancelled (the server then skips it), so quick clicks never pile up work or show the wrong report.
  const pick = async (id: string) => {
    const turn = ++picking.current;
    try {
      const { example: e, report } = await api.example(id);
      if (turn !== picking.current) return;
      const value = exampleInput(e);
      setExample(e);
      setInput(value);
      if (report) {
        check.reset();
        setView({ report, seconds: 0, cached: true, input: value, gold: e });
      } else if (ready) {
        await run(value, e);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const stages = check.events.flatMap((e) => (e.type === "stage" ? [{ stage: e.stage, t: e.t }] : []));

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <div className="relative isolate overflow-hidden rounded-[28px] border border-hair">
        <div className="absolute inset-0 -z-10 opacity-70">
          <Loupe paused={busy} />
        </div>
        <div className="flex flex-col gap-2 bg-gradient-to-r from-ink-950/85 via-ink-950/55 to-transparent px-6 py-7 sm:px-8">
          <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">{t("analyze.title")}</Heading>
          <p className="m-0 max-w-2xl text-[15px] leading-relaxed text-fog-300">
            {t("analyze.lead")}
          </p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <Panel title={t("analyze.try")}>
          <ExamplePicker examples={examples} current={input.exampleId} onPick={pick} />
          {example && input.exampleId === example.id && <p className="m-0 text-sm leading-relaxed text-fog-300" dir="auto">{example.about}</p>}
        </Panel>
        <Panel title={t("common.orOwn")}>
          <InputForm
            value={input}
            onChange={setInput}
            onSubmit={() => {
              picking.current++;
              run(input, example && example.id === input.exampleId ? example : null);
            }}
            disabled={check.running || !ready}
            submitLabel={ready ? t("analyze.submit") : t("common.loadingModels")}
          />
        </Panel>
      </div>

      <div className={check.running ? "grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]" : "hidden"} aria-hidden={!check.running}>
        <div className="card relative grid min-h-[320px] place-items-center overflow-hidden">
          <Suspense fallback={null}>
            <GlassHalo active={check.running} />
          </Suspense>
          <span className="absolute bottom-5 font-mono text-xs text-fog-300">{t("analyze.checking")}</span>
        </div>
        <Panel title={t("analyze.progress")}>
          <StageProgress stages={stages} queued={check.queued} />
        </Panel>
      </div>

      {check.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
          {t("common.checkFailed", { error: check.error })}
        </div>
      )}

      {view && (
        <div className={`flex flex-col gap-6 transition-opacity duration-300 ${check.running ? "pointer-events-none opacity-35" : ""}`} aria-busy={check.running}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-mono text-xs text-fog-400">
              {t("analyze.model", { state: check.running ? t("analyze.previous") : view.cached ? t("analyze.readyMade") : t("analyze.checkedIn", { s: num(view.seconds, 1) }), v: view.report.model_version ?? "" })}
            </span>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-ghost" onClick={() => downloadJson(`truth-guardian-report-${view.report.id}.json`, { input: view.input, report: view.report })}>
                {t("analyze.download")}
              </button>
              {view.report.verdict !== "grounded" && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => {
                    setInput(view.input);
                    navigate("/heal?auto=1");
                  }}
                >
                  {t("analyze.heal")}
                </button>
              )}
            </div>
          </div>
          <ReportView key={`${view.report.id}:${view.input.answer}`} report={view.report} input={view.input} gold={view.gold} />
        </div>
      )}
    </div>
  );
}
