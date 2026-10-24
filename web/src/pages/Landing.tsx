import { useEffect, useMemo, useRef, useState } from "react";
import { useTour } from "../components/Tour";
import { Ascent, type AscentRow } from "../layers/Ascent";
import { NeuralBrain } from "../layers/brain/NeuralBrain";
import { Pharos } from "../layers/Gradients";
import { Heading } from "../layers/Heading";
import { SpectraDeck, type SpectraCard } from "../layers/SpectraDeck";
import { api, type ModelCard } from "../lib/api";
import { num, pct, TASK_LABEL } from "../lib/format";
import { Link, useRouter } from "../lib/router";
import type { ExampleBrief } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

const STAGES: AscentRow[] = [
  { label: "Evidence", chip: "Step 1 of 5", title: "Find the evidence for every sentence", sub: "Each sentence of the answer is matched to the source passages that could support it, by keywords (BM25) and by meaning, fused by rank." },
  { label: "Signals", chip: "Step 2 of 5", title: "Read it four different ways", sub: "Word overlap, numbers, names and dates checked one by one, meaning similarity, and HHEM, a model trained to judge factual consistency." },
  { label: "Fusion", chip: "Step 3 of 5", title: "Turn them into one calibrated risk", sub: "A learned ensemble weighs the signals for every sentence and for the whole answer; its risk reads as a probability." },
  { label: "Rules", chip: "Step 4 of 5", title: "Catch what models miss", sub: "Flipped negations and opposites confirmed by NLI, swapped roles, overclaims, sources that disagree, citations that point elsewhere." },
  { label: "Report", chip: "Step 5 of 5", title: "Explain, fix, guarantee", sub: "Exact words, evidence, a fix from the sources, who is to blame, what was left out, a statistical guarantee, a triage lane and a grade." },
];

const GLOW = ["#fb7185", "#c4b5fd", "#a78bfa", "#fbbf24", "#34d399", "#60a5fa", "#2dd4bf", "#f472b6", "#fb923c", "#93c5fd", "#5eead4", "#e879f9"];

function useScrollFraction(ref: React.RefObject<HTMLElement | null>) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let raf = 0;
    const read = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const travel = el.offsetHeight - window.innerHeight;
      setValue(travel > 0 ? Math.min(1, Math.max(0, -rect.top / travel)) : 0);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [ref]);
  return value;
}

export default function Landing() {
  const { health, busy } = useWorkspace();
  const { navigate } = useRouter();
  const tour = useTour();
  const page = useRef<HTMLDivElement>(null);
  const how = useRef<HTMLElement>(null);
  const pageProgress = useScrollFraction(page);
  const howProgress = useScrollFraction(how);
  const [examples, setExamples] = useState<ExampleBrief[]>([]);
  const [card, setCard] = useState<ModelCard | null>(null);

  useEffect(() => {
    api.examples().then((e) => setExamples(e.answers.filter((x) => x.origin.startsWith("written")))).catch(() => {});
    api.modelCard().then(setCard).catch(() => {});
  }, []);

  const cards: SpectraCard[] = useMemo(() => examples.map((e, i) => ({
    key: e.id,
    c1: `color-mix(in oklab, ${GLOW[i % GLOW.length]} 55%, #0b1220)`,
    c2: "#070a10",
    glow: GLOW[i % GLOW.length],
    label: e.title,
    content: (
      <>
        <span className="self-start rounded-lg border border-white/25 bg-white/12 px-2 py-1 font-mono text-[11px] tracking-widest">{String(i + 1).padStart(2, "0")}</span>
        <span className="flex flex-col gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/70">{TASK_LABEL[e.task] ?? e.task}</span>
          <span className="text-[22px] font-semibold leading-tight">{e.title}</span>
          <span className="text-[13px] leading-snug text-white/75">{e.about}</span>
        </span>
      </>
    ),
  })), [examples]);

  const dev = card?.ragtruth_dev;
  const lockedBest = Math.max(0, ...Object.values(card?.locked_baselines ?? {}).map((b) => b.ragtruth ?? 0));
  const results = [
    card?.locked_test
      ? { value: num(card.locked_test.auroc, 3), label: `AUROC on the locked RAGTruth test set, opened once${lockedBest ? ` (best baseline ${num(lockedBest, 3)})` : ""}` }
      : dev && { value: num(dev.auroc, 3), label: `AUROC on RAGTruth dev (best baseline ${num(Math.max(...Object.values(card!.baselines).map((b) => b.auroc)), 3)})` },
    card?.locked_halueval?.qa
      ? { value: num(card.locked_halueval.qa.auroc, 3), label: "AUROC on the locked HaluEval QA set, never trained on" }
      : card?.halueval && { value: num(card.halueval.qa, 3), label: "AUROC on HaluEval QA, never trained on" },
    card?.guarantee && { value: pct(card.guarantee.miss_rate), label: `hallucinations missed at the catch line, as guaranteed (α = ${card.guarantee.alpha})` },
    card?.speed && { value: `${num(card.speed.mean, 1)} s`, label: "per answer on a laptop CPU" },
    { value: "0", label: "calls to the internet" },
  ].filter(Boolean) as { value: string; label: string }[];

  return (
    <div ref={page} className="relative isolate">
      <div className="fixed inset-0 -z-10" aria-hidden="true">
        <NeuralBrain progress={pageProgress} paused={busy} />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(5,7,11,.92)_0%,rgba(5,7,11,.55)_45%,rgba(5,7,11,.05)_75%)]" />
      </div>

      <section className="mx-auto flex min-h-[calc(100dvh-64px)] max-w-[1320px] flex-col justify-center gap-7 px-4 py-16 sm:px-8">
        <span className="self-start rounded-full border border-beam-400/30 px-3 py-1.5 font-mono text-xs tracking-wide text-beam-300">iWISE 2026 · AI Challenge 4 · hallucination detection</span>
        <Heading className="m-0 max-w-[16ch] text-[clamp(44px,6.4vw,84px)] font-normal leading-[1.02] tracking-[-0.035em]">Every claim, checked against its source.</Heading>
        <p className="m-0 max-w-[560px] text-lg leading-relaxed text-fog-300">
          Paste a question, the sources and an AI answer. Truth Guardian marks the exact words that drift from the evidence, says who is to blame, fixes what it can and checks again. It also watches agents while they run.
        </p>
        <div className="flex flex-wrap gap-3">
          <button type="button" className="btn btn-primary" onClick={() => tour.start(false)}>
            Take the 3-minute tour
          </button>
          <Link to="/analyze" className="btn btn-ghost no-underline">
            Check an answer
          </Link>
          <Link to="/fool" className="btn btn-ghost no-underline">
            Try to fool it
          </Link>
          <Link to="/agent" className="btn btn-ghost no-underline">
            Watch an agent
          </Link>
        </div>
        <span className="font-mono text-xs text-fog-400">{health?.state === "ready" ? `models ready · warm-up took ${num(health.warm_seconds, 0)} s · nothing leaves this computer` : "the models are loading in the background; the tools open as soon as they are ready"}</span>
      </section>

      <section ref={how} className="relative h-[320vh]" aria-label="How it works">
        <div className="sticky top-[72px] mx-auto flex h-[calc(100dvh-96px)] max-w-[1320px] flex-col gap-4 px-4 sm:px-8">
          <h2 className="m-0 text-[13px] font-normal uppercase tracking-[0.2em] text-fog-400">How it works</h2>
          <div className="min-h-0 flex-1">
            <Ascent
              rows={STAGES}
              value={howProgress * (STAGES.length - 1)}
              height={Math.max(380, Math.min(620, typeof window !== "undefined" ? window.innerHeight - 160 : 520))}
              metric={dev ? <span className="font-mono text-sm text-fog-400">{STAGES.length} stages · {num(card?.speed?.mean, 1)} s per answer · AUROC {num(dev.auroc, 3)}</span> : undefined}
            />
          </div>
        </div>
      </section>

      <section className="mx-auto flex max-w-[1320px] flex-col gap-5 px-4 py-16 sm:px-8" aria-label="Examples">
        <h2 className="m-0 text-[13px] font-normal uppercase tracking-[0.2em] text-fog-400">Six answers to try</h2>
        {cards.length > 0 && (
          <SpectraDeck
            cards={cards}
            onOpen={(i) => navigate(`/analyze?example=${encodeURIComponent(examples[i].id)}`)}
            caption={(i) => <h3 className="m-0 text-[28px] font-normal tracking-tight">{examples[i]?.title}</h3>}
            cta="Check this example"
          />
        )}
      </section>

      {results.length > 0 && (
        <section className="mx-auto max-w-[1320px] px-4 py-10 sm:px-8" aria-label="Measured results">
          <div className="card grid gap-6 p-7 sm:grid-cols-2 lg:grid-cols-5">
            {results.map((r) => (
              <div key={r.label} className="flex flex-col gap-1.5">
                <span className="font-mono text-[30px] leading-none">{r.value}</span>
                <span className="text-sm text-fog-400">{r.label}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-fog-400">
            Read from the evaluation files; the full picture, limits included, is on the <Link to="/model" className="text-beam-300">model card</Link>.
          </p>
        </section>
      )}

      <section className="mx-auto max-w-[1320px] px-4 pb-20 pt-6 sm:px-8">
        <div className="relative isolate overflow-hidden rounded-[28px] border border-white/8">
          <div className="absolute inset-0 -z-10">
            <Pharos paused={busy} />
          </div>
          <div className="flex flex-col items-start gap-4 bg-gradient-to-r from-ink-950/80 to-transparent px-8 py-14 sm:px-12">
            <h2 className="m-0 max-w-[20ch] text-[clamp(30px,4vw,48px)] font-normal leading-tight tracking-tight">Bring an answer you are not sure about.</h2>
            <p className="m-0 max-w-[48ch] text-fog-300">A lighthouse does not tell ships where to go; it shows them where the rocks are. Paste the sources and the answer and see which claims stand on them.</p>
            <Link to="/analyze" className="btn btn-primary no-underline">
              Open the analyzer
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
