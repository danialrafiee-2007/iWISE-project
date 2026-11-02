import { useEffect, useMemo, useRef, useState } from "react";
import { Panel, StageProgress } from "../components/report/Panels";
import { CardsCascade, type CascadeCard } from "../layers/CardsCascade";
import { formatNumber, useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { SceneFrame } from "../layers/SceneFrame";
import { api, ApiError, type ModelCard } from "../lib/api";
import { KIND_LABEL, num, pct } from "../lib/format";
import { glide } from "../lib/glide";
import type { FoolAnswer, FoolResult } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useWorkspace } from "../lib/workspace";
import { ReportView } from "./Analyze";

// Signal Array's studio field is near-black; a warm grey one makes the lamp read as a product photo on the light page.
// The values are in the scene's linear working space, so they render lighter than they look here.
const STUDIO = { bgTop: "#d6c9a8", bgBottom: "#9c8f6c" };

const KINDS = ["number", "entity", "negation", "role_swap", "addition", "antonym", "quantifier", "certainty"] as const;
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
  const results = useRef<HTMLDivElement>(null);
  const check = useStream<FoolResult>();
  const ready = health?.state === "ready";
  const current = answers[index];
  const { lang, t } = useI18n();

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
              <span className="rounded-lg border border-hair bg-white/15 px-2 py-1 font-mono text-xs font-medium tracking-widest backdrop-blur">{t("fool.cardCount", { i: formatNumber(i + 1, 0, 2), n: formatNumber(KINDS.length, 0, 2) })}</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/80">{rates?.[kind] ? t("fool.caughtRate", { p: pct(rates[kind].detected) }) : ""}</span>
            </div>
            <div>
              <p className="m-0 mb-1.5 font-mono text-[11px] uppercase tracking-[0.18em] text-white/70">{t("fool.trick", { i: formatNumber(i + 1, 0, 2) })}</p>
              <h3 className="m-0 text-[28px] font-semibold leading-[1.05] tracking-tight text-white">{KIND_LABEL[kind]}</h3>
              <p className="m-0 mt-2 max-w-[30ch] text-[13px] text-white/75">{t(`fool.hint.${kind}` as MessageKey)}</p>
            </div>
          </>
        ),
      })),
    [rates, lang],
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
      setNotice(e instanceof ApiError ? e.message : t("fool.trickFailed"));
    }
  };

  useEffect(() => {
    if (check.running) glide(results.current);
  }, [check.running]);

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
      ? { signal: "amber" as const, title: t("fool.noneTitle"), text: t("fool.noneText") }
      : result.caught && result.located
        ? { signal: "green" as const, title: t("fool.locatedTitle"), text: t("fool.locatedText") }
        : result.caught
          ? { signal: "amber" as const, title: t("fool.flaggedTitle"), text: t("fool.flaggedText") }
          : result.cautioned
            ? { signal: "amber" as const, title: t("fool.cautionedTitle"), text: t("fool.cautionedText") }
            : { signal: "red" as const, title: t("fool.fooledTitle"), text: t("fool.fooledText") };

  return (
    <div className="page-in mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-2xl flex-col gap-2">
          <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">{t("fool.title")}</Heading>
          <p className="m-0 text-[15px] leading-relaxed text-fog-300">
            {t("fool.lead")}
          </p>
        </div>
        <div className="card flex items-center gap-5 px-5 py-3" aria-live="polite">
          <div className="flex flex-col">
            <span className="font-mono text-2xl">{formatNumber(score.tries)}</span>
            <span className="text-xs text-fog-400">{t("fool.tries")}</span>
          </div>
          <div className="flex flex-col">
            <span className="font-mono text-2xl text-bad-ink">{formatNumber(score.fooled)}</span>
            <span className="text-xs text-fog-400">{t("fool.through")}</span>
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
              {t("fool.apply", { trick: KIND_LABEL[KINDS[trick]] })}
            </button>
            <span className="text-xs text-fog-400">
              {rates?.[KINDS[trick]] ? t("fool.suite", { n: formatNumber(rates[KINDS[trick]].n), c: pct(rates[KINDS[trick]].detected), l: pct(rates[KINDS[trick]].located) }) : ""}
            </span>
          </div>
          {notice && (
            <p role="alert" className="m-0 text-sm text-warn-ink">
              {`${notice[0].toUpperCase() + notice.slice(1)}.`}
            </p>
          )}
        </div>

        <Panel key={current?.id ?? "loading"} title={current ? t("fool.answerTitle") : t("fool.loadingAnswers")}>
          {current && (
            <>
              {current.question && (
                <p className="m-0 text-[15px]">
                  <span className="text-fog-400">{t("fool.question")}</span>
                  <span dir="auto">{current.question}</span>
                </p>
              )}
              <details className="rounded-2xl bg-ink-700/60 px-4 py-3 text-sm text-fog-300">
                <summary className="cursor-pointer text-fog-200">{t("fool.sources", { n: formatNumber(current.sources.length) })}</summary>
                <div className="mt-2 flex max-h-56 flex-col gap-2 overflow-y-auto pe-2">
                  {current.sources.map((s, i) => (
                    <p key={i} className="m-0 leading-relaxed" dir="auto">
                      <span className="font-mono text-beam-400">[{formatNumber(i + 1)}]</span> {s}
                    </p>
                  ))}
                </div>
              </details>
              <label htmlFor="fool-answer" className="label">
                {t("fool.answerLabel")}
              </label>
              <textarea id="fool-answer" className="field min-h-[180px] resize-y" dir="auto" maxLength={5000} value={text} onChange={(e) => { setText(e.target.value); setEdit(null); check.reset(); }} />
              {edit && (
                <span className="self-start rounded-lg bg-bad/12 px-2.5 py-1 font-mono text-[13px] text-bad-ink" dir="auto">
                  {edit.original ? t("fool.edited", { a: edit.original, b: edit.new }) : t("fool.added", { x: edit.new })}
                </span>
              )}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn btn-primary" onClick={run} disabled={!ready || check.running || !text.trim()}>
                  {check.running ? t("fool.checking") : t("fool.check")}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setText(current.answer)} disabled={check.running || text === current.answer}>
                  {t("fool.undo")}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => setIndex((index + 1) % answers.length)} disabled={check.running}>
                  {t("fool.another")}
                </button>
              </div>
            </>
          )}
        </Panel>
      </div>

      <div ref={results} className="flex flex-col gap-6">
      {check.running && (
        <Panel title={t("fool.checkingEdit")}>
          <StageProgress stages={check.events.flatMap((e) => (e.type === "stage" ? [{ stage: e.stage, t: e.t }] : []))} queued={check.queued} />
        </Panel>
      )}

      {check.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
          {t("common.checkFailed", { error: check.error })}
        </div>
      )}

      {result && outcome && current && (
        <div key={`${current.id}:${text}:${result.report.risk}`} className="page-in flex flex-col gap-6">
          <div className="card grid overflow-hidden md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <div className="relative h-[300px] md:h-auto md:min-h-[320px]">
              <SceneFrame name="signal-array" signal={outcome.signal} config={STUDIO} paused={false} interactive={false} delay={450} />
            </div>
            <div className="flex flex-col justify-center gap-3 p-7" aria-live="polite">
              <span className="font-mono text-xs uppercase tracking-[0.18em]" style={{ color: outcome.signal === "green" ? "var(--color-ok)" : outcome.signal === "red" ? "var(--color-bad)" : "var(--color-warn)" }}>
                {outcome.signal === "green" ? t("fool.signalCaught") : outcome.signal === "red" ? t("fool.signalThrough") : t("fool.signalPartly")}
              </span>
              <h2 className="m-0 text-[28px] font-normal leading-tight">{outcome.title}</h2>
              <p className="m-0 text-[15px] leading-relaxed text-fog-300">{outcome.text}</p>
              <p className="m-0 font-mono text-xs text-fog-400">
                {t("fool.meta", { r: num(result.report.risk), d: num(result.report.response_threshold), s: num(result.seconds, 1) })}
                {card?.fool_the_guardian ? t("fool.controls", { p: pct(card.fool_the_guardian.controls_flagged) }) : ""}
              </p>
            </div>
          </div>
          <ReportView report={result.report} input={{ question: current.question ?? "", sources: current.sources, answer: text, task: "other" }} />
        </div>
      )}
      </div>
    </div>
  );
}
