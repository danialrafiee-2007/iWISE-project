import { useEffect, useState, type ReactNode } from "react";
import { Panel } from "../components/report/Panels";
import { Heading } from "../layers/Heading";
import { SceneFrame } from "../layers/SceneFrame";
import { api, type ModelCard as Card } from "../lib/api";
import { KIND_LABEL, num, pct } from "../lib/format";

function Stat({ value, label, note }: { value: ReactNode; label: string; note?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[34px] leading-none text-fog-100">{value}</span>
      <span className="text-sm text-fog-300">{label}</span>
      {note && <span className="text-xs text-fog-400">{note}</span>}
    </div>
  );
}

function Bars({ rows, max = 1, digits = 3 }: { rows: { label: string; value: number; highlight?: boolean }[]; max?: number; digits?: number }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
      {rows.map((r) => (
        <li key={r.label} className="grid grid-cols-[minmax(0,180px)_minmax(0,1fr)_56px] items-center gap-3 text-sm">
          <span className={r.highlight ? "text-fog-100" : "text-fog-300"}>{r.label}</span>
          <div className="h-2 rounded-full bg-ink-600">
            <div className="h-2 rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: r.highlight ? "var(--color-beam-400)" : "var(--color-ink-500)" }} />
          </div>
          <span className="text-right font-mono text-fog-200">{r.value.toFixed(digits)}</span>
        </li>
      ))}
    </ul>
  );
}

const LIMITS = [
  "Trained and calibrated on RAGTruth (English news, QA and business data). On another domain the ranking holds less well (HaluEval dialogue and summary about 0.69 to 0.70 AUROC) and the guarantees break until a domain profile is fitted on a few dozen labelled answers.",
  "Some edits slip through often: opposite words, stronger quantifiers and dropped hedges are the weakest columns of the Fool-the-Guardian suite.",
  "On natural agent runs (AgentHallu) no setting of the live guardian separates faithful from hallucinating agents well; strict mode stops many faithful runs, lenient mode stops few hallucinating ones.",
  "Healing edits are often right but not always: read the changes before using a healed answer.",
  "It checks answers against the given sources only. A claim that is true in the world but absent from the sources counts as unsupported.",
];

export default function ModelCard() {
  const [card, setCard] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.modelCard().then(setCard).catch((e) => setError(String(e)));
  }, []);

  const dev = card?.ragtruth_dev;
  return (
    <div className="relative isolate">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[620px] opacity-70 [mask:linear-gradient(180deg,#000_55%,transparent)]">
        <SceneFrame name="lumen-grid" interactive={false} />
      </div>
      <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-10 sm:px-8">
        <div className="flex max-w-3xl flex-col gap-2">
          <Heading className="m-0 text-[40px] font-normal leading-tight tracking-tight">Model card</Heading>
          <p className="m-0 text-[15px] leading-relaxed text-fog-300">
            Every number on this page is read from the project's committed evaluation files. Thresholds were chosen on training or development data; the locked test set is opened once, at the end.
          </p>
          {card && (
            <span className="font-mono text-xs text-fog-400">
              fusion model {card.engine.model_version ?? "not loaded"} · tracer {card.engine.tracer_version ?? "not loaded"}
            </span>
          )}
        </div>
        {error && <p role="alert" className="text-bad">The model card could not be loaded: {error}</p>}
        {!card && !error && <p className="text-fog-400">Loading the results…</p>}

        {dev && (
          <Panel>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Stat value={num(dev.auroc, 3)} label="AUROC on RAGTruth dev" note={dev.auroc_ci95 ? `95% interval ${num(dev.auroc_ci95[0], 3)} to ${num(dev.auroc_ci95[1], 3)}, ${dev.answers} answers` : undefined} />
              <Stat value={num(dev.f1, 3)} label="F1 for hallucinated answers" note={`flagging everything gives ${num(dev.f1_flag_everything, 3)}`} />
              <Stat value={num(dev.span_f1, 3)} label="Character-level span F1" note="where in the answer the error is" />
              <Stat value={num(dev.ece, 3)} label="Calibration error (ECE)" note="the risk reads as a probability" />
            </div>
          </Panel>
        )}

        <div className="grid gap-5 lg:grid-cols-2">
          {dev && (
            <Panel title="Against the baselines (RAGTruth dev, AUROC)">
              <Bars
                rows={[
                  { label: "Truth Guardian", value: dev.auroc, highlight: true },
                  ...Object.entries(card!.baselines).map(([label, b]) => ({ label, value: b.auroc })),
                ]}
              />
              <span className="text-xs text-fog-400">Per task: {Object.entries(dev.by_task).map(([t, v]) => `${t} ${num(v.auroc, 3)}`).join(" · ")}</span>
            </Panel>
          )}
          {card?.halueval && (
            <Panel title="On data it never saw (HaluEval, AUROC)">
              <Bars
                rows={[
                  { label: "Question answering", value: card.halueval.qa, highlight: true },
                  { label: "Dialogue", value: card.halueval.dialogue, highlight: true },
                  { label: "Summarisation", value: card.halueval.summary, highlight: true },
                ]}
              />
              <span className="text-xs text-fog-400">{card.halueval.answers_per_task} answers per task, no tuning on HaluEval. Training: {card.train?.answers} RAGTruth answers, out-of-fold AUROC {num(card.train?.out_of_fold_auroc, 3)}.</span>
            </Panel>
          )}
        </div>

        {card?.fool_the_guardian && (
          <Panel title="Fool the Guardian: one controlled edit per answer (372 edited dev answers, 60 unedited controls)">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-left text-sm">
                <thead className="text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pr-3 font-normal">Edit</th>
                    <th className="py-2 pr-3 font-normal">Answers</th>
                    <th className="py-2 pr-3 font-normal">Caught</th>
                    <th className="py-2 pr-3 font-normal">Exact place found</th>
                    <th className="py-2 font-normal">AUROC vs unedited</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(card.fool_the_guardian.edits).map(([kind, e]) => (
                    <tr key={kind} className="border-t border-white/6">
                      <td className="py-2 pr-3">{KIND_LABEL[kind] ?? kind}</td>
                      <td className="py-2 pr-3 font-mono text-fog-300">{e.n}</td>
                      <td className="py-2 pr-3 font-mono">{pct(e.detected)}</td>
                      <td className="py-2 pr-3 font-mono">{pct(e.located)}</td>
                      <td className="py-2 font-mono">{num(e.auroc, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <span className="text-xs text-fog-400">Unedited control answers are flagged {pct(card.fool_the_guardian.controls_flagged)} of the time.</span>
          </Panel>
        )}

        <div className="grid gap-5 lg:grid-cols-3">
          {card?.guarantee && (
            <Panel title="Statistical guarantees (conformal, α = 0.1)">
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                Over {card.guarantee.splits} random splits of RAGTruth dev: the catch line missed {pct(card.guarantee.miss_rate, 1)} of hallucinated answers and the alarm line raised {pct(card.guarantee.false_alarm_rate, 1)} false alarms, both at the promised 10%.
              </p>
            </Panel>
          )}
          {card?.triage && (
            <Panel title="Triage lanes (held-out splits)">
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {pct(card.triage.pass)} of answers pass ({pct(card.triage.hallucinated_among_passed, 1)} of them hallucinated, target at most 10%), {pct(card.triage.review)} go to review, {pct(card.triage.block)} are blocked ({pct(card.triage.hallucinated_among_blocked)} of them hallucinated). {pct(card.triage.hallucinations_caught)} of hallucinations never pass.
              </p>
            </Panel>
          )}
          {card?.speed && (
            <Panel title="Speed on this laptop (CPU only)">
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {num(card.speed.mean, 1)} s per answer on average, {num(card.speed.p95, 1)} s at the 95th percentile, over {card.speed.answers} dev answers once warm. Loading the models takes about {num(card.speed.cold_start_seconds, 0)} s at start-up.
              </p>
            </Panel>
          )}
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          {card?.tracer_tg_agent && (
            <Panel title="Agents: finding the step where it went wrong">
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                TG-Agent ({card.tracer_tg_agent.trajectories} runs): detection AUROC {num(card.tracer_tg_agent.detection_auroc, 2)}; the exact faulty step in {pct(card.tracer_tg_agent.tracer_exact)} of hallucinating runs, within one step in {pct(card.tracer_tg_agent.tracer_within_1)} (random {pct(card.tracer_tg_agent.baseline_random)}).
                {card.tracer_agenthallu && ` AgentHallu (${card.tracer_agenthallu.trajectories} natural runs): exact step ${pct(card.tracer_agenthallu.exact)} (random ${pct(card.tracer_agenthallu.random)}), detection AUROC ${num(card.tracer_agenthallu.detection_auroc, 2)}.`}
              </p>
            </Panel>
          )}
          {card?.healing && (
            <Panel title="Self-healing (84 dev answers)">
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                Of flagged hallucinated answers, {pct(card.healing.hallucinated.grounded_after_among_flagged as number)} end up judged grounded; mean risk falls from {num(card.healing.hallucinated.mean_risk_before as number)} to {num(card.healing.hallucinated.mean_risk_after as number)}. Edits remove {pct(card.healing.hallucinated.edit_recall as number)} of the annotated wrong text with {pct(card.healing.hallucinated.edit_precision as number)} precision; grounded answers lose {pct(card.healing.grounded.text_edited as number, 1)} of their text.
              </p>
            </Panel>
          )}
        </div>

        {card && <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="Known limits">
            <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-sm leading-relaxed text-fog-300">
              {LIMITS.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
          </Panel>
          <Panel title="Locked test set">
            {card?.locked_test ? (
              <p className="m-0 text-sm text-fog-300">
                AUROC {num(card.locked_test.auroc, 3)}, F1 {num(card.locked_test.f1, 3)}, span F1 {num(card.locked_test.span_f1, 3)}.
              </p>
            ) : (
              <p className="m-0 text-sm leading-relaxed text-fog-300">Not opened yet. It is evaluated once, with the final model, and reported here as it comes out.</p>
            )}
            <span className="label mt-2">Data, models and AI use</span>
            <p className="m-0 text-sm leading-relaxed text-fog-300">
              Datasets, models and libraries with their licences are listed in docs/CREDITS.md; every use of AI tools in building this project, and who verified it, is in docs/AI_USAGE.md; every design decision with its evidence is in docs/DECISIONS.md.
            </p>
          </Panel>
        </div>}

        {card && (
          <details className="text-xs text-fog-400">
            <summary className="cursor-pointer">Where these numbers come from</summary>
            <ul className="mt-2 flex list-none flex-col gap-1 p-0 font-mono">
              {Object.values(card.sources).map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}
