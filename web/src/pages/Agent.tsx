import { useEffect, useRef, useState } from "react";
import { AnswerView } from "../components/report/AnswerView";
import { Panel, VerdictCard } from "../components/report/Panels";
import { Ascent, type AscentRow } from "../layers/Ascent";
import { formatNumber, useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { SceneFrame } from "../layers/SceneFrame";
import { api, type ModelCard } from "../lib/api";
import { num, pct } from "../lib/format";
import type { Example, ExampleBrief, Report, Step } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useRouter } from "../lib/router";
import { useWorkspace } from "../lib/workspace";
import { ExamplePicker } from "./Analyze";

type Policy = "strict" | "lenient";
type Result = { report: Report; seconds: number; cached: boolean };

const CALM = { colIris: "#1f9c8a", colHalo: "#2dd4bf", colAura: "#0f3b3a" };
const ALERT = { colIris: "#e11d48", colHalo: "#fb7185", colAura: "#4c0d1d" };
const STEP_MS = 1400;

const SAMPLE_STEPS: Step[] = [
  { step: 1, kind: "action", content: "call search('opening year of the Marlow Public Library')", observation: "The Marlow Public Library opened in 1932 and holds about 40,000 books." },
  { step: 2, kind: "thought", content: "The library opened in 1932. The question also asks who designed the building." },
  { step: 3, kind: "thought", content: "The building was designed by the architect Helen Ward." },
  { step: 4, kind: "answer", content: "The Marlow Public Library opened in 1932; its building was designed by Helen Ward." },
];

const short = (text: string, n = 180) => (text.length > n ? text.slice(0, n - 1) + "…" : text);

export default function Agent() {
  const { health } = useWorkspace();
  const { search, consume } = useRouter();
  const [examples, setExamples] = useState<ExampleBrief[]>([]);
  const [example, setExample] = useState<Example | null>(null);
  const [custom, setCustom] = useState(JSON.stringify({ question: "When did the Marlow Public Library open, and who designed it?", steps: SAMPLE_STEPS }, null, 2));
  const [customError, setCustomError] = useState<string | null>(null);
  const [policy, setPolicy] = useState<Policy>("strict");
  const [steps, setSteps] = useState<Step[]>([]);
  const [question, setQuestion] = useState("");
  const [finalAnswer, setFinalAnswer] = useState("");
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [card, setCard] = useState<ModelCard | null>(null);
  const run = useStream<Result>();
  const timer = useRef<number | undefined>(undefined);
  const ready = health?.state === "ready";
  const report = run.result?.report;
  const agent = report?.agent;
  const stopAt = agent?.guardian_stop ?? null;
  const stopIndex = stopAt != null ? steps.findIndex((s) => s.step === stopAt) : -1;
  const halted = stopIndex >= 0 && shown > stopIndex;
  const finished = shown >= steps.length;
  const { t } = useI18n();
  const kindName = (kind: string) => ((["thought", "action", "observation", "answer"] as const).includes(kind as never) ? t(`agent.kind.${kind}` as MessageKey) : kind);

  useEffect(() => {
    api.examples().then((e) => setExamples(e.agents)).catch(() => {});
    api.modelCard().then(setCard).catch(() => {});
  }, []);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!playing || !agent) return;
    if (shown >= steps.length || (stopIndex >= 0 && shown === stopIndex + 1)) {
      setPlaying(false);
      return;
    }
    timer.current = window.setTimeout(() => setShown((n) => n + 1), shown === 0 ? 300 : STEP_MS);
    return () => window.clearTimeout(timer.current);
  }, [playing, shown, agent, steps.length, stopIndex]);

  const start = async (body: object, trajectory: Step[], q: string, answer: string) => {
    setSteps(trajectory);
    setFinalAnswer(answer);
    setQuestion(q);
    setShown(0);
    setPlaying(false);
    const result = await run.run("/api/agent", { ...body, policy });
    if (result) setPlaying(true);
  };

  const pick = async (id: string) => {
    const { example: e } = await api.example(id);
    setExample(e);
    await start({ example_id: id }, e.agent_steps, e.question ?? "", e.answer);
  };

  useEffect(() => {
    const id = new URLSearchParams(search).get("example");
    if (id && ready && !run.running) {
      consume();
      pick(id);
    }
  }, [search, ready]);

  const runCustom = async () => {
    try {
      const parsed = JSON.parse(custom) as { question?: string; steps: Step[]; answer?: string };
      if (!Array.isArray(parsed.steps) || !parsed.steps.length) throw new Error(t("agent.stepsError"));
      setCustomError(null);
      setExample(null);
      const answer = parsed.answer ?? [...parsed.steps].reverse().find((s) => s.kind === "answer")?.content ?? "";
      await start({ question: parsed.question ?? null, steps: parsed.steps, answer: parsed.answer ?? null }, parsed.steps, parsed.question ?? "", answer);
    } catch (e) {
      setCustomError(e instanceof Error ? e.message : String(e));
    }
  };

  const alertFor = (step: number) => agent?.alerts.find((a) => a.step === step);
  const rows: AscentRow[] = steps.map((s, i) => {
    const alert = i < shown ? alertFor(s.step) : undefined;
    return {
      label: t("agent.stepLabel", { i: formatNumber(s.step), kind: kindName(s.kind) }),
      chip: alert ? (alert.level === "stop" ? t("agent.stoppedAt", { i: formatNumber(s.step) }) : t("agent.warningAt", { i: formatNumber(s.step) })) : t("agent.stepOf", { i: formatNumber(s.step), n: formatNumber(steps.length), kind: kindName(s.kind) }),
      title: alert ? (alert.level === "stop" ? t("agent.titleStop") : t("agent.titleWarn")) : s.kind === "action" ? t("agent.titleAction") : s.kind === "answer" ? t("agent.titleAnswer") : t("agent.titleReason"),
      sub: alert ? (
        <span dir="auto">
          {alert.reason[0].toUpperCase() + alert.reason.slice(1)}.
        </span>
      ) : (
        <span className="font-mono text-[13px]" dir="auto">{short(s.content)}</span>
      ),
    };
  });
  const tone = halted ? "#c0584a" : rows.length && shown > 0 && alertFor(steps[Math.min(shown, steps.length) - 1]?.step)?.level === "warning" ? "#c39236" : "#456b56";
  const tg = card?.guardian;

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <div className="flex max-w-3xl flex-col gap-2">
        <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">{t("agent.title")}</Heading>
        <p className="m-0 text-[15px] leading-relaxed text-fog-300">
          {t("agent.lead")}
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title={t("agent.pick")}>
          <ExamplePicker examples={examples} current={example?.id} onPick={pick} disabled={!ready || run.running} />
          {example && <p className="m-0 text-sm leading-relaxed text-fog-300" dir="auto">{example.about}</p>}
          <div className="flex flex-wrap items-center gap-2 border-t border-hair pt-3" role="radiogroup" aria-label={t("agent.policyLabel")}>
            <span className="label me-1">{t("agent.policy")}</span>
            {(["strict", "lenient"] as Policy[]).map((p) => (
              <button key={p} type="button" role="radio" aria-checked={policy === p} className="chip" aria-pressed={policy === p} onClick={() => setPolicy(p)}>
                {p === "strict" ? t("agent.strict") : t("agent.lenient")}
              </button>
            ))}
          </div>
        </Panel>
        <Panel title={t("agent.own")}>
          <label htmlFor="agent-json" className="sr-only">
            {t("agent.json")}
          </label>
          <textarea id="agent-json" className="field min-h-[220px] resize-y font-mono text-[12.5px]" dir="ltr" value={custom} onChange={(e) => setCustom(e.target.value)} spellCheck={false} />
          {customError && (
            <p role="alert" className="m-0 text-sm text-warn-ink">
              {customError}
            </p>
          )}
          <button type="button" className="btn btn-primary self-start" onClick={runCustom} disabled={!ready || run.running}>
            {t("agent.run")}
          </button>
        </Panel>
      </div>

      {run.running && (
        <Panel title={t("agent.preparing")}>
          <p className="m-0 text-sm text-fog-300">{t("agent.preparingText")}</p>
        </Panel>
      )}
      {run.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
          {t("agent.failed", { error: run.error })}
        </div>
      )}

      {agent && steps.length > 0 && (
        <div key={`${report?.id}:${question}:${steps.length}:${policy}`} className="flex flex-col gap-6">
          {question && (
            <p className="m-0 text-[15px] text-fog-200">
              <span className="text-fog-400">{t("agent.task")}</span>
              <span dir="auto">{question}</span>
            </p>
          )}
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div data-tour="agent-timeline">
              <Ascent rows={rows} value={Math.max(0, Math.min(steps.length - 1, shown - 1))} tone={tone} height={440} compact />
            </div>
            <div className="card relative min-h-[300px] overflow-hidden">
              <SceneFrame name="halftone-iris" config={halted ? ALERT : CALM} className="ink-invert" />
              <div className="absolute inset-x-0 bottom-0 flex flex-col gap-1 bg-gradient-to-t from-ink-950/95 to-transparent p-5" aria-live="polite">
                <span className="font-mono text-xs uppercase tracking-[0.18em]" style={{ color: halted ? "var(--color-bad)" : "var(--color-beam-400)" }}>
                  {halted ? t("agent.stopped") : finished ? t("agent.finished") : t("agent.watching")}
                </span>
                <span className="text-sm text-fog-200">
                  {halted
                    ? t("agent.stoppedText", { i: formatNumber(stopAt ?? 0) })
                    : finished
                      ? stopAt == null
                        ? t("agent.letFinish")
                        : t("agent.pastStop")
                      : t("agent.progress", { i: formatNumber(Math.max(1, shown)), n: formatNumber(steps.length) })}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary" onClick={() => setPlaying((p) => !p)} disabled={finished || (halted && !playing)}>
              {playing ? t("common.pause") : shown === 0 ? t("agent.play") : t("agent.resume")}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => { setPlaying(false); setShown((n) => Math.min(steps.length, n + 1)); }} disabled={finished}>
              {t("agent.next")}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => { setShown(0); setPlaying(true); }}>
              {t("agent.replay")}
            </button>
            {halted && !finished && (
              <button type="button" className="btn btn-ghost" onClick={() => { setPlaying(false); setShown(steps.length); }}>
                {t("agent.wouldHave")}
              </button>
            )}
          </div>

          <Panel title={t("agent.trajectory")}>
            <ol className="m-0 flex list-none flex-col gap-2 p-0">
              {steps.map((s, i) => {
                const alert = alertFor(s.step);
                const visible = i < shown;
                const afterStop = stopIndex >= 0 && i > stopIndex;
                return (
                  <li key={s.step} className={`rounded-2xl border px-4 py-3 transition-opacity ${visible ? "opacity-100" : "opacity-35"} ${visible && alert ? (alert.level === "stop" ? "border-bad/40 bg-bad/8" : "border-warn/35 bg-warn/6") : "border-hair bg-ink-800"}`}>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-fog-400">
                      <span className="font-mono text-fog-200">{formatNumber(s.step, 0, 2)}</span>
                      <span className="rounded-full bg-ink-600 px-2 py-0.5 text-fog-300">{kindName(s.kind)}</span>
                      {afterStop && visible && <span className="text-bad-ink">{t("agent.wouldNot")}</span>}
                      {finished && agent.suspected_step === s.step && <span className="rounded-full bg-split/15 px-2 py-0.5 text-split">{t("agent.origin")}</span>}
                    </div>
                    {visible ? (
                      <>
                        <p className="m-0 mt-1.5 whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-fog-200" dir="auto">{short(s.content, 600)}</p>
                        {s.observation && <p className="m-0 mt-1.5 whitespace-pre-wrap rounded-xl bg-ink-900 px-3 py-2 font-mono text-[12.5px] leading-relaxed text-fog-300" dir="auto">↳ {short(s.observation, 600)}</p>}
                        {alert && (
                          <p className="m-0 mt-2 text-sm" dir="auto" style={{ color: alert.level === "stop" ? "var(--color-bad)" : "var(--color-warn)" }}>
                            {alert.level === "stop" ? t("agent.alertStop", { reason: alert.reason }) : t("agent.alertWarning", { reason: alert.reason })}
                          </p>
                        )}
                      </>
                    ) : (
                      <p className="m-0 mt-1.5 text-sm text-fog-400">{t("agent.notYet")}</p>
                    )}
                  </li>
                );
              })}
            </ol>
          </Panel>

          {finished && report && (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
              <div className="flex min-w-0 flex-col gap-4">
                <Panel title={t("agent.tracerTitle")}>
                  <ul className="m-0 flex list-none flex-col gap-2 p-0">
                    {agent.steps.map((s) => (
                      <li key={s.step} className="grid grid-cols-[60px_minmax(0,1fr)_48px] items-center gap-3 text-sm">
                        <span className="font-mono text-fog-300">{t("agent.step", { i: formatNumber(s.step) })}</span>
                        <div className="h-2 rounded-full bg-ink-600">
                          <div className="h-2 rounded-full" style={{ width: `${Math.max(2, s.suspicion * 100)}%`, background: s.step === agent.suspected_step ? "var(--color-split)" : "var(--color-ink-500)" }} />
                        </div>
                        <span className="text-end font-mono text-xs text-fog-400">{num(s.suspicion)}</span>
                      </li>
                    ))}
                  </ul>
                  <span className="text-xs text-fog-400">{t("agent.tracerNote")}</span>
                </Panel>
                <Panel title={t("agent.finalTitle")}>
                  <AnswerView answer={finalAnswer} claims={report.claims} />
                </Panel>
              </div>
              <aside className="flex flex-col gap-4">
                <VerdictCard report={report} />
                {tg && (
                  <Panel title={t("agent.measuredTitle")}>
                    <p className="m-0 text-sm leading-relaxed text-fog-300">
                      {t("agent.measured", { a: pct(tg.strict?.stop_tpr), b: pct(tg.strict?.stop_fpr), c: pct(tg.strict?.stop_on_responsible_step), d: pct(tg.lenient?.stop_tpr), e: pct(tg.lenient?.stop_fpr) })}
                    </p>
                  </Panel>
                )}
              </aside>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
