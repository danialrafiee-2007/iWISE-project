import { useEffect, useState, type ReactNode } from "react";
import { CalibrationChart, type CalibrationSeries } from "../components/CalibrationChart";
import { Panel } from "../components/report/Panels";
import { Heading } from "../layers/Heading";
import { SceneFrame } from "../layers/SceneFrame";
import { api, type ChallengeCases, type ModelCard as Card } from "../lib/api";
import { KIND_LABEL, num, pct } from "../lib/format";

const CALIBRATION_SERIES: Omit<CalibrationSeries, "ece" | "answers" | "bins">[] = [
  { key: "ragtruth_dev", label: "RAGTruth dev", color: "#3987e5", label_at: { bin: 7, dx: -10, dy: -10, anchor: "end" } },
  { key: "ragtruth_test", label: "RAGTruth test (locked)", color: "#14a38b", label_at: { bin: 4, dx: 10, dy: 18, anchor: "start" } },
  { key: "halueval", label: "HaluEval (locked, unseen domain)", color: "#d95926", label_at: { bin: 3, dx: 0, dy: -12, anchor: "middle" } },
];
const TASK_LABELS ={ qa: "Question answering", dialogue: "Dialogue", summary: "Summarisation" } as const;
const TASK_SHORT = { qa: "QA", dialogue: "Dialogue", summary: "Summary" } as const;

function Stat({ value, label, note }: { value: ReactNode; label: string; note?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[34px] leading-none text-fog-100">{value}</span>
      <span className="text-sm text-fog-300">{label}</span>
      {note && <span className="text-xs text-fog-400">{note}</span>}
    </div>
  );
}

function ChallengeCasesPanel({ cases }: { cases: ChallengeCases }) {
  const { mixed, partial, unsupported, weak, agent } = cases.cases;
  const { faithful, honest_over_weak_sources: honest, faithful_agents: agents } = cases.controls;
  const stale = agent.by_kind.stale;
  const rows = [
    {
      name: "Correct and incorrect information mixed", n: mixed.n, flagged: pct(mixed.caught), auroc: mixed.auroc_vs_faithful,
      check: `wrong part found ${pct(mixed.wrong_part_found)}, correct parts left alone ${pct(mixed.correct_parts_kept)}`,
      controls: `${pct(faithful.flagged)} flagged`,
    },
    {
      name: "Only part of the evidence used", n: partial.n, flagged: pct(partial.caveat.caught), auroc: partial.caveat.auroc_vs_faithful,
      check: `left-out fact reported ${pct(partial.omission.left_out_reported)}, flagged as false ${pct(partial.omission.flagged)} (${partial.omission.n} answers, nothing false in them); dropped caveat noticed ${pct(partial.caveat.noticed)}, flagged ${pct(partial.caveat.caught)} (${partial.caveat.n})`,
      controls: `a gap reported in ${pct(faithful.completeness_reported_missing)}`,
    },
    {
      name: "Claims no document supports", n: unsupported.n, flagged: pct(unsupported.caught), auroc: unsupported.auroc_vs_faithful,
      check: `claim found ${pct(unsupported.claim_found)}, called unsupported ${pct(unsupported.called_unsupported)} (else contradicted)`,
      controls: `${pct(faithful.flagged)} flagged`,
    },
    {
      name: "Sources with low relevance or too little evidence", n: weak.n, flagged: pct(weak.caught), auroc: weak.auroc_vs_honest,
      check: `the retriever blamed ${pct(weak.retrieval_blamed)}, else the generator`,
      controls: `honest "the sources do not say" answers: ${pct(honest.flagged)} flagged`,
    },
    {
      name: "Multi-step agents that generate or revise information", n: agent.n, flagged: pct(agent.caught), auroc: agent.auroc_answer_risk_vs_faithful,
      check: `step where it began found ${pct(agent.exact_step)}, guardian stopped the run ${pct(agent.guardian_stopped)}`,
      controls: `${pct(agents.flagged)} flagged, ${pct(agents.guardian_stopped)} stopped`,
    },
  ];
  return (
    <Panel title={`The challenge's five harder cases: ${cases.samples - (faithful.n + honest.n + agents.n)} written cases, each paired with a faithful answer`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-sm">
          <thead className="text-xs text-fog-400">
            <tr>
              <th className="py-2 pr-3 font-normal">Case named in the challenge</th>
              <th className="py-2 pr-3 font-normal">Items</th>
              <th className="py-2 pr-3 font-normal">Answer flagged</th>
              <th className="py-2 pr-3 font-normal">What this case needs</th>
              <th className="py-2 pr-3 font-normal">AUROC vs faithful</th>
              <th className="py-2 font-normal">Faithful counterparts</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t border-white/6 align-top">
                <td className="py-2 pr-3">{r.name}</td>
                <td className="py-2 pr-3 font-mono text-fog-300">{r.n}</td>
                <td className="py-2 pr-3 font-mono">{r.flagged}</td>
                <td className="py-2 pr-3 text-fog-300">{r.check}</td>
                <td className="py-2 pr-3 font-mono">{num(r.auroc, 3)}</td>
                <td className="py-2 text-fog-300">{r.controls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="text-xs leading-relaxed text-fog-400">
        {`Written for this project on fictional topics after the model was frozen, run once through the live app, nothing tuned on it (benchmark/challenge_cases.json). Weakest: an agent that keeps an outdated value after a newer tool result (${Math.round(stale.caught * stale.n)} of ${stale.n} caught), and a single wrong detail inside an otherwise correct answer, often marked on its claim but not enough to flag the whole answer.`}
      </span>
    </Panel>
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
  "Trained and calibrated on RAGTruth (English news, QA and business data). On another domain the ranking holds less well (locked HaluEval dialogue 0.67 and summary 0.69 AUROC, calibration error about 0.23) until a domain profile is fitted on a few dozen labelled answers; with 50, dialogue rises to about 0.72 and summary to 0.79 on answers the profile did not see, and the calibration error falls to about 0.07.",
  "Some edits still slip through: an opposite word is caught 45% of the time, a stronger quantifier 57% and a dropped hedge 37% (up from 37% and 20% after D-114).",
  "On natural agent runs (AgentHallu) no setting of the live guardian separates faithful from hallucinating agents well (detection AUROC about 0.53 on the locked test); three fixes tried out of fold made no difference (D-116). Finding the faulty step works better than chance, not reliably.",
  "Span F1 on the locked RAGTruth test (0.30) is lower than on dev (0.38): the verdict for the whole answer holds up better than the exact place of the error. Exact words from the trained detector lift dev span F1 to 0.41; the locked test has not been opened again to measure it.",
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
  const locked = card?.locked_test;
  const lockedBaselines = Object.entries(card?.locked_baselines ?? {}).filter(([, b]) => b.ragtruth !== undefined);
  const reference = card?.locked_reference;
  const calibration: CalibrationSeries[] = card?.calibration
    ? CALIBRATION_SERIES.filter((s) => card.calibration?.[s.key]).map((s) => ({ ...s, ...card.calibration![s.key] }))
    : [];
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

        {locked && (
          <Panel tour="headline" title="Locked test set: RAGTruth test, opened once with the final model and the thresholds chosen on dev" tone="var(--color-beam-400)">
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Stat value={num(locked.auroc, 3)} label="AUROC" note={locked.auroc_ci95 ? `95% interval ${num(locked.auroc_ci95[0], 3)} to ${num(locked.auroc_ci95[1], 3)}, ${locked.answers} answers` : `${locked.answers} answers`} />
              <Stat value={num(locked.f1, 3)} label="F1 for hallucinated answers" note={`flagging everything gives ${num(locked.f1_flag_everything, 3)}`} />
              <Stat value={num(locked.span_f1, 3)} label="Character-level span F1" note="where in the answer the error is" />
              <Stat value={num(locked.ece, 3)} label="Calibration error (ECE)" note="the risk reads as a probability" />
            </div>
            <span className="text-xs text-fog-400">{`Per task: ${Object.entries(locked.by_task).map(([t, v]) => `${t} ${num(v.auroc, 3)}`).join(" · ")}`}</span>
          </Panel>
        )}

        {dev && (
          <Panel tour={locked ? undefined : "headline"} title={locked ? "Development set (RAGTruth dev), where the model and its thresholds were chosen" : undefined}>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Stat value={num(dev.auroc, 3)} label="AUROC on RAGTruth dev" note={`${dev.auroc_ci95 ? `95% interval ${num(dev.auroc_ci95[0], 3)} to ${num(dev.auroc_ci95[1], 3)}, ` : ""}${dev.answers} answers${dev.fusion_only_auroc ? `; fusion model alone ${num(dev.fusion_only_auroc, 3)}` : ""}`} />
              <Stat value={num(dev.f1, 3)} label="F1 for hallucinated answers" note={`flagging everything gives ${num(dev.f1_flag_everything, 3)}`} />
              <Stat value={num(dev.span_f1, 3)} label="Character-level span F1" note="where in the answer the error is" />
              <Stat value={num(dev.ece, 3)} label="Calibration error (ECE)" note="the risk reads as a probability" />
            </div>
          </Panel>
        )}

        <div className="grid gap-5 lg:grid-cols-2">
          {locked && lockedBaselines.length > 0 ? (
            <Panel title="Against the baselines (locked RAGTruth test, AUROC)">
              <Bars
                rows={[
                  { label: "Truth Guardian", value: locked.auroc, highlight: true },
                  ...lockedBaselines.map(([label, b]) => ({ label, value: b.ragtruth! })),
                  ...(reference?.ragtruth !== undefined ? [{ label: "LettuceDetect (external)", value: reference.ragtruth }] : []),
                ]}
              />
              <span className="text-xs text-fog-400">
                {`Same answers, thresholds from dev. On dev: Truth Guardian ${num(dev?.auroc, 3)}, best baseline ${num(Math.max(...Object.values(card!.baselines).map((b) => b.auroc)), 3)}.`}
                {reference?.ragtruth !== undefined && ` LettuceDetect is a published detector fine-tuned on RAGTruth train itself, so this test is its home ground; it finds the wrong words better (span F1 ${num(reference.ragtruth_span_f1, 3)}) but ranks answers less well${reference.qa !== undefined ? `; on HaluEval QA / dialogue / summary it scores ${(["qa", "dialogue", "summary"] as const).map((t) => num(reference[t], 3)).join(" / ")}` : ""}.`}
              </span>
            </Panel>
          ) : dev && (
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
          {card?.locked_halueval ? (
            <Panel title="On data it never saw (locked HaluEval, AUROC)">
              <Bars
                rows={(["qa", "dialogue", "summary"] as const).flatMap((t) => {
                  const ours = card.locked_halueval?.[t];
                  if (!ours) return [];
                  const best = Math.max(...lockedBaselines.map(([, b]) => b[t] ?? 0));
                  return [
                    { label: TASK_LABELS[t], value: ours.auroc, highlight: true },
                    ...(best > 0 ? [{ label: `${TASK_SHORT[t]}, best baseline`, value: best }] : []),
                  ];
                })}
              />
              <span className="text-xs text-fog-400">{`${Object.values(card.locked_halueval)[0]?.answers ?? ""} answers per task, opened once, no tuning on HaluEval; the thresholds are RAGTruth's, so the risk is less well calibrated here. Training: ${card.train?.answers ?? ""} RAGTruth answers.`}</span>
            </Panel>
          ) : card?.halueval && (
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

        {calibration.length > 0 && (
          <Panel title="Does a risk of 0.8 mean 80%? Predicted risk against how often the answers were really hallucinated">
            <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <CalibrationChart series={calibration} />
              <div className="flex flex-col gap-3 text-sm leading-relaxed text-fog-300">
                <p className="m-0">A point on the dashed line means the risk can be read as a probability: of the answers given a risk near 0.8, about 80% were hallucinated. Points below the line mean the risk runs high (cautious); above it, low.</p>
                <p className="m-0">On RAGTruth, where the model was calibrated, the points stay close to the line, on dev and on the locked test. On the test the middle of the scale runs a little high, so the guardian errs on the side of caution there.</p>
                <p className="m-0">On HaluEval, a domain it never saw, low risks are too low and high risks too high. This is why a domain profile, fitted on a few dozen labelled answers of the new domain, recalibrates the risk before the guarantees are used there.</p>
                <span className="text-xs text-fog-400">Ten equal-width risk bins, the same as the reported calibration error (ECE). Hover a point for its numbers.</span>
              </div>
            </div>
          </Panel>
        )}

        {card?.profiles && (
          <Panel title={`A new domain from ${card.profiles.labelled} labelled answers: the shipped domain profiles, checked on answers they did not see`}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] border-collapse text-left text-sm">
                <thead className="text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pr-3 font-normal">Profile</th>
                    <th className="py-2 pr-3 font-normal">Answers checked</th>
                    <th className="py-2 pr-3 font-normal">AUROC, model → profile</th>
                    <th className="py-2 pr-3 font-normal">Calibration error</th>
                    <th className="py-2 font-normal">Verdict accuracy</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(card.profiles.domains).map(([name, p]) => (
                    <tr key={name} className="border-t border-white/6">
                      <td className="py-2 pr-3">{name}</td>
                      <td className="py-2 pr-3 font-mono text-fog-300">{p.held_out_answers}</td>
                      <td className="py-2 pr-3 font-mono">{`${num(p.auroc.model, 3)} → ${num(p.auroc.profile, 3)}`}</td>
                      <td className="py-2 pr-3 font-mono">{`${num(p.ece.model, 3)} → ${num(p.ece.profile, 3)}`}</td>
                      <td className="py-2 font-mono">{`${pct(p.verdict_accuracy.model)} → ${pct(p.verdict_accuracy.profile)}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <span className="text-xs leading-relaxed text-fog-400">{`Each profile re-weights the model's risk and three evidence signals averaged over the answer's sentences, recalibrates the risk and sets the domain's own guarantee lines and verdict. It never uses the answer's length: on HaluEval, length alone separates the labels${card.profiles.length_alone_auroc ? ` (AUROC ${Object.entries(card.profiles.length_alone_auroc).map(([d, v]) => `${d} ${num(v, 2)}`).join(", ")})` : ""}, a shortcut no real domain offers. HaluEval external dev; the locked HaluEval sets were not used.`}</span>
          </Panel>
        )}

        {card?.challenge_cases && <ChallengeCasesPanel cases={card.challenge_cases} />}

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
          <Panel title="Locked test sets">
            {locked ? (
              <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed text-fog-300">
                <li>{`RAGTruth test: AUROC ${num(locked.auroc, 3)}, F1 ${num(locked.f1, 3)}, span F1 ${num(locked.span_f1, 3)} (${locked.answers} answers).`}</li>
                {card?.locked_halueval && <li>{`HaluEval (never trained on): ${Object.entries(card.locked_halueval).map(([t, v]) => `${t} ${num(v.auroc, 3)}`).join(", ")} AUROC, ${Object.values(card.locked_halueval)[0]?.answers ?? ""} answers each.`}</li>}
                {card?.locked_agenthallu && <li>{`AgentHallu (${card.locked_agenthallu.trajectories} natural agent runs): faulty step found exactly in ${pct(card.locked_agenthallu.exact)} (random ${pct(card.locked_agenthallu.random)}), detection AUROC ${num(card.locked_agenthallu.detection_auroc, 2)}.`}</li>}
                <li>Each was evaluated once and logged in eval/locked_runs.log; nothing was tuned on them.</li>
                <li>These are the results of the system as it stood then (D-109). Later changes (domain profiles, exact words, overclaim rules: D-113 to D-115) are measured on development data only; the locked sets were not opened again.</li>
              </ul>
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
