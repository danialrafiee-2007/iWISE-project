import { useEffect, useMemo, useState } from "react";
import { Panel, StageProgress } from "../components/report/Panels";
import { CardsCascade, type CascadeCard } from "../layers/CardsCascade";
import { Heading } from "../layers/Heading";
import { SceneFrame } from "../layers/SceneFrame";
import { api, ApiError, type ModelCard } from "../lib/api";
import { KIND_LABEL, pct } from "../lib/format";
import type { FoolAnswer, FoolResult } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useWorkspace } from "../lib/workspace";
import { ReportView } from "./Analyze";

const KINDS = ["number", "entity", "negation", "role_swap", "addition", "antonym", "quantifier", "certainty"] as const;
const HINT: Record<string, string> = {
  number: "Change a year, an amount or a count.",
  entity: "Replace a person, place or organisation with another one.",
  negation: "Turn a statement into its negation.",
  role_swap: "Keep every word, swap who did what to whom.",
  addition: "Add a plausible claim the sources never make.",
  antonym: "Replace a word with its opposite.",
  quantifier: "Turn 'some' into 'most', 'often' into 'always'.",
  certainty: "Drop a hedge such as 'may' or 'reportedly'.",
};
const FILL: Record<string, string> = {
  number: "linear-gradient(150deg,#0f766e,#134e4a 55%,#042f2e)",
  entity: "linear-gradient(150deg,#1d4ed8,#1e3a8a 55%,#0b1437)",
  negation: "linear-gradient(150deg,#be123c,#7f1d1d 55%,#2a0a0f)",
  role_swap: "linear-gradient(150deg,#7c3aed,#4c1d95 55%,#1a0b33)",
  addition: "linear-gradient(150deg,#b45309,#78350f 55%,#2a1405)",
  antonym: "linear-gradient(150deg,#0e7490,#164e63 55%,#06202a)",
  quantifier: "linear-gradient(150deg,#4d7c0f,#365314 55%,#121c06)",
  certainty: "linear-gradient(150deg,#a21caf,#701a75 55%,#24062a)",
};

type Edit = { start: number; end: number; new: string; original: string } | null;

function readScore(): { tries: number; fooled: number } {
  try {
    return JSON.parse(localStorage.getItem("tg-fool-score") ?? "") as { tries: number; fooled: number };
  } catch {
    return { tries: 0, fooled: 0 };
  }
}

export default function Fool() {
  const { health } = useWorkspace();
  const [answers, setAnswers] = useState<FoolAnswer[]>([]);
  const [index, setIndex] = useState(0);
  const [text, setText] = useState("");
  const [trick, setTrick] = useState(0);
  const [edit, setEdit] = useState<Edit>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [card, setCard] = useState<ModelCard | null>(null);
  const [score, setScore] = useState(readScore);
  const check = useStream<FoolResult>();
  const ready = health?.state === "ready";
  const current = answers[index];

  useEffect(() => {
    api.foolAnswers().then((a) => {
      setAnswers(a);
      setIndex(Math.floor(Math.random() * Math.max(1, a.length)));
    }).catch(() => {});
    api.modelCard().then(setCard).catch(() => {});
  }, []);

  useEffect(() => {
    if (current) setText(current.answer);
    setEdit(null);
    setNotice(null);
    check.reset();
  }, [current?.id]);

  const rates = card?.fool_the_guardian?.edits;
  const cards: CascadeCard[] = useMemo(
    () =>
      KINDS.map((kind, i) => ({
        key: kind,
        label: KIND_LABEL[kind],
        fill: FILL[kind],
        content: (
          <>
            <div className="flex items-center justify-between">
              <span className="rounded-lg border border-white/25 bg-white/15 px-2 py-1 font-mono text-xs font-medium tracking-widest backdrop-blur">{String(i + 1).padStart(2, "0")} / 08</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/80">{rates?.[kind] ? `caught ${pct(rates[kind].detected)}` : ""}</span>
            </div>
            <div>
              <p className="m-0 mb-1.5 font-mono text-[11px] uppercase tracking-[0.18em] text-white/70">Trick {String(i + 1).padStart(2, "0")}</p>
              <h3 className="m-0 text-[28px] font-semibold leading-[1.05] tracking-tight">{KIND_LABEL[kind]}</h3>
              <p className="m-0 mt-2 max-w-[30ch] text-[13px] text-white/75">{HINT[kind]}</p>
            </div>
          </>
        ),
      })),
    [rates],
  );

  const applyTrick = async () => {
    if (!current) return;
    setNotice(null);
    try {
      const result = await api.foolEdit(current.id, KINDS[trick], Math.floor(Math.random() * 1000));
      setText(result.answer);
      setEdit(result.edit);
      check.reset();
    } catch (e) {
      setNotice(e instanceof ApiError ? e.message : "the trick could not be applied");
    }
  };

  const run = async () => {
    if (!current) return;
    const result = await check.run("/api/fool/check", { answer_id: current.id, answer: text });
    if (result && result.edit) {
      const next = { tries: score.tries + 1, fooled: score.fooled + (result.caught ? 0 : 1) };
      setScore(next);
      try {
        localStorage.setItem("tg-fool-score", JSON.stringify(next));
      } catch {
        /* storage unavailable */
      }
    }
  };

  const result = check.result;
  const outcome = !result
    ? null
    : !result.edit
      ? { signal: "amber" as const, title: "Nothing was changed", text: "Edit the answer or apply a trick first: an unedited answer is the control." }
      : result.caught && result.located
        ? { signal: "green" as const, title: "Caught, and it found the exact place", text: "The guardian flagged the answer and marked the claim you edited." }
        : result.caught
          ? { signal: "amber" as const, title: "Flagged, but not at your edit", text: "The answer was flagged as risky, but the edited claim was not the one marked." }
          : result.cautioned
            ? { signal: "amber" as const, title: "Not flagged, only cautioned", text: "The answer passed, with a caution on the claim you edited." }
            : { signal: "red" as const, title: "You fooled it", text: "The guardian judged your edited answer grounded. This is one of its known blind spots; the suite numbers on each card show how often each trick gets through." };

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-2xl flex-col gap-2">
          <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">Can you fool it?</Heading>
          <p className="m-0 text-[15px] leading-relaxed text-fog-300">
            Take a grounded answer, slip one lie into it, and see whether the guardian finds the exact words. Pick a trick, or edit the answer yourself.
          </p>
        </div>
        <div className="card flex items-center gap-5 px-5 py-3" aria-live="polite">
          <div className="flex flex-col">
            <span className="font-mono text-2xl">{score.tries}</span>
            <span className="text-xs text-fog-400">your tries</span>
          </div>
          <div className="flex flex-col">
            <span className="font-mono text-2xl text-bad">{score.fooled}</span>
            <span className="text-xs text-fog-400">got through</span>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3">
          <div data-tour="tricks">
            <CardsCascade cards={cards} active={trick} onActive={setTrick} height={440} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn btn-primary" onClick={applyTrick} disabled={!ready || !current || check.running}>
              {`Apply “${KIND_LABEL[KINDS[trick]]}”`}
            </button>
            <span className="text-xs text-fog-400">
              {rates?.[KINDS[trick]] ? `Suite: ${rates[KINDS[trick]].n} edits, caught ${pct(rates[KINDS[trick]].detected)}, exact place found ${pct(rates[KINDS[trick]].located)}.` : ""}
            </span>
          </div>
          {notice && (
            <p role="alert" className="m-0 text-sm text-warn">
              {`${notice[0].toUpperCase() + notice.slice(1)}.`}
            </p>
          )}
        </div>

        <Panel key={current?.id ?? "loading"} title={current ? "A grounded answer from the development data" : "Loading answers…"}>
          {current && (
            <>
              {current.question && (
                <p className="m-0 text-[15px]">
                  <span className="text-fog-400">Question: </span>
                  {current.question}
                </p>
              )}
              <details className="rounded-2xl bg-ink-700/60 px-4 py-3 text-sm text-fog-300">
                <summary className="cursor-pointer text-fog-200">Sources ({current.sources.length})</summary>
                <div className="mt-2 flex max-h-56 flex-col gap-2 overflow-y-auto pr-2">
                  {current.sources.map((s, i) => (
                    <p key={i} className="m-0 leading-relaxed">
                      <span className="font-mono text-beam-400">[{i + 1}]</span> {s}
                    </p>
                  ))}
                </div>
              </details>
              <label htmlFor="fool-answer" className="label">
                The answer (edit it freely)
              </label>
              <textarea id="fool-answer" className="field min-h-[180px] resize-y" maxLength={5000} value={text} onChange={(e) => { setText(e.target.value); setEdit(null); check.reset(); }} />
              {edit && (
                <span className="self-start rounded-lg bg-bad/12 px-2.5 py-1 font-mono text-[13px] text-rose-300">
                  {edit.original ? `“${edit.original}” → “${edit.new}”` : `added “${edit.new}”`}
                </span>
              )}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn btn-primary" onClick={run} disabled={!ready || check.running || !text.trim()}>
                  {check.running ? "Checking…" : "Check my edit"}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setText(current.answer)} disabled={check.running || text === current.answer}>
                  Undo edits
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setIndex((index + 1) % answers.length)} disabled={check.running}>
                  Another answer
                </button>
              </div>
            </>
          )}
        </Panel>
      </div>

      {check.running && (
        <Panel title="Checking your edit">
          <StageProgress stages={check.events.flatMap((e) => (e.type === "stage" ? [{ stage: e.stage, t: e.t }] : []))} queued={check.queued} />
        </Panel>
      )}

      {check.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-rose-200">
          The check did not finish: {check.error}
        </div>
      )}

      {result && outcome && current && (
        <div key={`${current.id}:${text}:${result.report.risk}`} className="flex flex-col gap-6">
          <div className="card grid overflow-hidden md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="relative h-[300px] md:h-auto md:min-h-[320px]">
              <SceneFrame name="signal-array" signal={outcome.signal} paused={false} interactive={false} />
            </div>
            <div className="flex flex-col justify-center gap-3 p-7" aria-live="polite">
              <span className="font-mono text-xs uppercase tracking-[0.18em]" style={{ color: outcome.signal === "green" ? "var(--color-ok)" : outcome.signal === "red" ? "var(--color-bad)" : "var(--color-warn)" }}>
                {outcome.signal === "green" ? "Caught" : outcome.signal === "red" ? "Got through" : "Partly"}
              </span>
              <h2 className="m-0 text-[28px] font-normal leading-tight">{outcome.title}</h2>
              <p className="m-0 text-[15px] leading-relaxed text-fog-300">{outcome.text}</p>
              <p className="m-0 font-mono text-xs text-fog-400">
                risk {result.report.risk.toFixed(2)} · decision line {result.report.response_threshold.toFixed(2)} · checked in {result.seconds.toFixed(1)} s
                {card?.fool_the_guardian ? ` · unedited answers are flagged ${pct(card.fool_the_guardian.controls_flagged)} of the time` : ""}
              </p>
            </div>
          </div>
          <ReportView report={result.report} input={{ question: current.question ?? "", sources: current.sources, answer: text, task: "other" }} />
        </div>
      )}
    </div>
  );
}
