import { useEffect, useState, type ReactNode } from "react";
import { CalibrationChart, type CalibrationSeries } from "../components/CalibrationChart";
import { Panel } from "../components/report/Panels";
import { formatNumber, t, useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { SceneFrame } from "../layers/SceneFrame";
import { api, type ChallengeCases, type ModelCard as Card } from "../lib/api";
import { KIND_LABEL, num, pct } from "../lib/format";

const CALIBRATION_SERIES: (Omit<CalibrationSeries, "ece" | "answers" | "bins" | "label"> & { label: MessageKey })[] = [
  { key: "ragtruth_dev", label: "card.seriesDev", color: "#3987e5", label_at: { bin: 7, dx: -10, dy: -10, anchor: "end" } },
  { key: "ragtruth_test", label: "card.seriesTest", color: "#14a38b", label_at: { bin: 4, dx: 10, dy: 18, anchor: "start" } },
  { key: "halueval", label: "card.seriesHalu", color: "#d95926", label_at: { bin: 3, dx: 0, dy: -12, anchor: "middle" } },
];
const taskLabel = (task: "qa" | "dialogue" | "summary") => t(`card.task.${task}`);
const taskShort = (task: "qa" | "dialogue" | "summary") => t(`card.short.${task}`);
/** "qa 0.912 · dialogue 0.670", with the task names in the interface language where they are known. */
const perTask = (rows: [string, number][], sep: string) =>
  rows.map(([task, v]) => `${["qa", "dialogue", "summary"].includes(task) ? taskShort(task as "qa") : task} ${num(v, 3)}`).join(sep);

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
      name: t("cc.mixed"), n: mixed.n, flagged: pct(mixed.caught), auroc: mixed.auroc_vs_faithful,
      check: t("cc.mixedCheck", { a: pct(mixed.wrong_part_found), b: pct(mixed.correct_parts_kept) }),
      controls: t("cc.flagged", { p: pct(faithful.flagged) }),
    },
    {
      name: t("cc.partial"), n: partial.n, flagged: pct(partial.caveat.caught), auroc: partial.caveat.auroc_vs_faithful,
      check: t("cc.partialCheck", { a: pct(partial.omission.left_out_reported), b: pct(partial.omission.flagged), n: formatNumber(partial.omission.n), c: pct(partial.caveat.noticed), d: pct(partial.caveat.caught), m: formatNumber(partial.caveat.n) }),
      controls: t("cc.partialControls", { p: pct(faithful.completeness_reported_missing) }),
    },
    {
      name: t("cc.unsupported"), n: unsupported.n, flagged: pct(unsupported.caught), auroc: unsupported.auroc_vs_faithful,
      check: t("cc.unsupportedCheck", { a: pct(unsupported.claim_found), b: pct(unsupported.called_unsupported) }),
      controls: t("cc.flagged", { p: pct(faithful.flagged) }),
    },
    {
      name: t("cc.weak"), n: weak.n, flagged: pct(weak.caught), auroc: weak.auroc_vs_honest,
      check: t("cc.weakCheck", { a: pct(weak.retrieval_blamed) }),
      controls: t("cc.weakControls", { p: pct(honest.flagged) }),
    },
    {
      name: t("cc.agent"), n: agent.n, flagged: pct(agent.caught), auroc: agent.auroc_answer_risk_vs_faithful,
      check: t("cc.agentCheck", { a: pct(agent.exact_step), b: pct(agent.guardian_stopped) }),
      controls: t("cc.agentControls", { a: pct(agents.flagged), b: pct(agents.guardian_stopped) }),
    },
  ];
  return (
    <Panel title={t("cc.title", { n: formatNumber(cases.samples - (faithful.n + honest.n + agents.n)) })}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-start text-sm">
          <thead className="text-xs text-fog-400">
            <tr>
              <th className="py-2 pe-3 font-normal">{t("cc.colCase")}</th>
              <th className="py-2 pe-3 font-normal">{t("cc.colItems")}</th>
              <th className="py-2 pe-3 font-normal">{t("cc.colFlagged")}</th>
              <th className="py-2 pe-3 font-normal">{t("cc.colNeeds")}</th>
              <th className="py-2 pe-3 font-normal">{t("cc.colAuroc")}</th>
              <th className="py-2 font-normal">{t("cc.colControls")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} className="border-t border-hair align-top">
                <td className="py-2 pe-3">{r.name}</td>
                <td className="py-2 pe-3 font-mono text-fog-300">{formatNumber(r.n)}</td>
                <td className="py-2 pe-3 font-mono">{r.flagged}</td>
                <td className="py-2 pe-3 text-fog-300">{r.check}</td>
                <td className="py-2 pe-3 font-mono">{num(r.auroc, 3)}</td>
                <td className="py-2 text-fog-300">{r.controls}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="text-xs leading-relaxed text-fog-400">
        {t("cc.note", { a: formatNumber(Math.round(stale.caught * stale.n)), b: formatNumber(stale.n) })}
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
          <span className="text-end font-mono text-fog-200">{num(r.value, digits)}</span>
        </li>
      ))}
    </ul>
  );
}

const LIMITS: MessageKey[] = ["card.limit1", "card.limit2", "card.limit3", "card.limit4", "card.limit5", "card.limit6"];

export default function ModelCard() {
  const [card, setCard] = useState<Card | null>(null);
  const [error, setError] = useState<string | null>(null);
  useI18n();
  useEffect(() => {
    api.modelCard().then(setCard).catch((e) => setError(String(e)));
  }, []);

  const dev = card?.ragtruth_dev;
  const locked = card?.locked_test;
  const lockedBaselines = Object.entries(card?.locked_baselines ?? {}).filter(([, b]) => b.ragtruth !== undefined);
  const reference = card?.locked_reference;
  const calibration: CalibrationSeries[] = card?.calibration
    ? CALIBRATION_SERIES.filter((s) => card.calibration?.[s.key]).map((s) => ({ ...s, label: t(s.label), ...card.calibration![s.key] }))
    : [];
  return (
    <div className="relative isolate">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[620px] opacity-70 [mask:linear-gradient(180deg,#000_55%,transparent)]">
        <SceneFrame name="lumen-grid" interactive={false} className="ink-invert" delay={450} />
      </div>
      <div className="page-in mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-10 sm:px-8">
        <div className="flex max-w-3xl flex-col gap-2">
          <Heading className="m-0 text-[40px] font-normal leading-tight tracking-tight">{t("card.title")}</Heading>
          <p className="m-0 text-[15px] leading-relaxed text-fog-300">
            {t("card.lead")}
          </p>
          {card && (
            <span className="font-mono text-xs text-fog-400">
              {t("card.versions", { m: card.engine.model_version ?? t("card.notLoaded"), t: card.engine.tracer_version ?? t("card.notLoaded") })}
            </span>
          )}
        </div>
        {error && <p role="alert" className="text-bad-ink">{t("card.error", { e: error })}</p>}
        {!card && !error && <p className="text-fog-400">{t("card.loading")}</p>}

        {locked && (
          <Panel tour="headline" title={t("card.lockedTitle")} tone="var(--color-beam-400)">
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Stat value={num(locked.auroc, 3)} label={t("card.auroc")} note={(locked.auroc_ci95 ? t("card.interval", { a: num(locked.auroc_ci95[0], 3), b: num(locked.auroc_ci95[1], 3) }) : "") + t("card.answers", { n: formatNumber(locked.answers) })} />
              <Stat value={num(locked.f1, 3)} label={t("card.f1")} note={t("card.f1Note", { v: num(locked.f1_flag_everything, 3) })} />
              <Stat value={num(locked.span_f1, 3)} label={t("card.span")} note={t("card.spanNote")} />
              <Stat value={num(locked.ece, 3)} label={t("card.ece")} note={t("card.eceNote")} />
            </div>
            <span className="text-xs text-fog-400">{t("card.perTask", { list: perTask(Object.entries(locked.by_task).map(([task, v]) => [task, v.auroc]), " · ") })}</span>
          </Panel>
        )}

        {dev && (
          <Panel tour={locked ? undefined : "headline"} title={locked ? t("card.devTitle") : undefined}>
            <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <Stat value={num(dev.auroc, 3)} label={t("card.devAuroc")} note={(dev.auroc_ci95 ? t("card.interval", { a: num(dev.auroc_ci95[0], 3), b: num(dev.auroc_ci95[1], 3) }) : "") + t("card.answers", { n: formatNumber(dev.answers) }) + (dev.fusion_only_auroc ? t("card.fusionAlone", { v: num(dev.fusion_only_auroc, 3) }) : "")} />
              <Stat value={num(dev.f1, 3)} label={t("card.f1")} note={t("card.f1Note", { v: num(dev.f1_flag_everything, 3) })} />
              <Stat value={num(dev.span_f1, 3)} label={t("card.span")} note={t("card.spanNote")} />
              <Stat value={num(dev.ece, 3)} label={t("card.ece")} note={t("card.eceNote")} />
            </div>
          </Panel>
        )}

        <div className="grid gap-5 lg:grid-cols-2">
          {locked && lockedBaselines.length > 0 ? (
            <Panel title={t("card.baselinesLocked")}>
              <Bars
                rows={[
                  { label: "Truth Guardian", value: locked.auroc, highlight: true },
                  ...lockedBaselines.map(([label, b]) => ({ label, value: b.ragtruth! })),
                  ...(reference?.ragtruth !== undefined ? [{ label: t("card.lettuce"), value: reference.ragtruth }] : []),
                ]}
              />
              <span className="text-xs text-fog-400">
                {t("card.sameAnswers", { a: num(dev?.auroc, 3), b: num(Math.max(...Object.values(card!.baselines).map((b) => b.auroc)), 3) })}
                {reference?.ragtruth !== undefined && t("card.lettuceNote", { s: num(reference.ragtruth_span_f1, 3), halu: reference.qa !== undefined ? t("card.lettuceHalu", { v: (["qa", "dialogue", "summary"] as const).map((task) => num(reference[task], 3)).join(" / ") }) : "" })}
              </span>
            </Panel>
          ) : dev && (
            <Panel title={t("card.baselinesDev")}>
              <Bars
                rows={[
                  { label: "Truth Guardian", value: dev.auroc, highlight: true },
                  ...Object.entries(card!.baselines).map(([label, b]) => ({ label, value: b.auroc })),
                ]}
              />
              <span className="text-xs text-fog-400">{t("card.perTask", { list: perTask(Object.entries(dev.by_task).map(([task, v]) => [task, v.auroc]), " · ") })}</span>
            </Panel>
          )}
          {card?.locked_halueval ? (
            <Panel title={t("card.unseenLocked")}>
              <Bars
                rows={(["qa", "dialogue", "summary"] as const).flatMap((task) => {
                  const ours = card.locked_halueval?.[task];
                  if (!ours) return [];
                  const best = Math.max(...lockedBaselines.map(([, b]) => b[task] ?? 0));
                  return [
                    { label: taskLabel(task), value: ours.auroc, highlight: true },
                    ...(best > 0 ? [{ label: t("card.bestBaseline", { task: taskShort(task) }), value: best }] : []),
                  ];
                })}
              />
              <span className="text-xs text-fog-400">{t("card.unseenLockedNote", { n: formatNumber(Object.values(card.locked_halueval)[0]?.answers ?? 0), t: formatNumber(card.train?.answers ?? 0) })}</span>
            </Panel>
          ) : card?.halueval && (
            <Panel title={t("card.unseen")}>
              <Bars
                rows={[
                  { label: taskLabel("qa"), value: card.halueval.qa, highlight: true },
                  { label: taskLabel("dialogue"), value: card.halueval.dialogue, highlight: true },
                  { label: taskLabel("summary"), value: card.halueval.summary, highlight: true },
                ]}
              />
              <span className="text-xs text-fog-400">{t("card.unseenNote", { n: formatNumber(card.halueval.answers_per_task), t: formatNumber(card.train?.answers ?? 0), a: num(card.train?.out_of_fold_auroc, 3) })}</span>
            </Panel>
          )}
        </div>

        {calibration.length > 0 && (
          <Panel title={t("card.calibTitle")}>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <CalibrationChart series={calibration} />
              <div className="flex flex-col gap-3 text-sm leading-relaxed text-fog-300">
                <p className="m-0">{t("card.calib1")}</p>
                <p className="m-0">{t("card.calib2")}</p>
                <p className="m-0">{t("card.calib3")}</p>
                <span className="text-xs text-fog-400">{t("card.calibNote")}</span>
              </div>
            </div>
          </Panel>
        )}

        {card?.profiles && (
          <Panel title={t("card.profilesTitle", { n: formatNumber(card.profiles.labelled) })}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] border-collapse text-start text-sm">
                <thead className="text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pe-3 font-normal">{t("card.colProfile")}</th>
                    <th className="py-2 pe-3 font-normal">{t("card.colChecked")}</th>
                    <th className="py-2 pe-3 font-normal">{t("card.colAurocArrow")}</th>
                    <th className="py-2 pe-3 font-normal">{t("card.colCalib")}</th>
                    <th className="py-2 font-normal">{t("card.colVerdictAcc")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(card.profiles.domains).map(([name, p]) => (
                    <tr key={name} className="border-t border-hair">
                      <td className="py-2 pe-3">{name}</td>
                      <td className="py-2 pe-3 font-mono text-fog-300">{formatNumber(p.held_out_answers)}</td>
                      <td className="py-2 pe-3 font-mono">{`${num(p.auroc.model, 3)} → ${num(p.auroc.profile, 3)}`}</td>
                      <td className="py-2 pe-3 font-mono">{`${num(p.ece.model, 3)} → ${num(p.ece.profile, 3)}`}</td>
                      <td className="py-2 font-mono">{`${pct(p.verdict_accuracy.model)} → ${pct(p.verdict_accuracy.profile)}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <span className="text-xs leading-relaxed text-fog-400">{t("card.profilesNote", { alone: card.profiles.length_alone_auroc ? t("card.lengthAlone", { list: Object.entries(card.profiles.length_alone_auroc).map(([d, v]) => `${d} ${num(v, 2)}`).join(t("common.comma")) }) : "" })}</span>
          </Panel>
        )}

        {card?.challenge_cases && <ChallengeCasesPanel cases={card.challenge_cases} />}

        {card?.fool_the_guardian && (
          <Panel title={t("card.foolTitle")}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] border-collapse text-start text-sm">
                <thead className="text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pe-3 font-normal">{t("card.colEdit")}</th>
                    <th className="py-2 pe-3 font-normal">{t("card.colAnswers")}</th>
                    <th className="py-2 pe-3 font-normal">{t("card.colCaught")}</th>
                    <th className="py-2 pe-3 font-normal">{t("card.colExact")}</th>
                    <th className="py-2 font-normal">{t("card.colAurocUnedited")}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(card.fool_the_guardian.edits).map(([kind, e]) => (
                    <tr key={kind} className="border-t border-hair">
                      <td className="py-2 pe-3">{KIND_LABEL[kind] ?? kind}</td>
                      <td className="py-2 pe-3 font-mono text-fog-300">{formatNumber(e.n)}</td>
                      <td className="py-2 pe-3 font-mono">{pct(e.detected)}</td>
                      <td className="py-2 pe-3 font-mono">{pct(e.located)}</td>
                      <td className="py-2 font-mono">{num(e.auroc, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <span className="text-xs text-fog-400">{t("card.foolNote", { p: pct(card.fool_the_guardian.controls_flagged) })}</span>
          </Panel>
        )}

        <div className="grid gap-5 lg:grid-cols-3">
          {card?.guarantee && (
            <Panel title={t("card.guaranteeTitle")}>
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {t("card.guarantee", { n: formatNumber(card.guarantee.splits), a: pct(card.guarantee.miss_rate, 1), b: pct(card.guarantee.false_alarm_rate, 1) })}
              </p>
            </Panel>
          )}
          {card?.triage && (
            <Panel title={t("card.triageTitle")}>
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {t("card.triage", { a: pct(card.triage.pass), b: pct(card.triage.hallucinated_among_passed, 1), c: pct(card.triage.review), d: pct(card.triage.block), e: pct(card.triage.hallucinated_among_blocked), f: pct(card.triage.hallucinations_caught) })}
              </p>
            </Panel>
          )}
          {card?.speed && (
            <Panel title={t("card.speedTitle")}>
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {t("card.speed", { m: num(card.speed.mean, 1), p: num(card.speed.p95, 1), n: formatNumber(card.speed.answers), c: num(card.speed.cold_start_seconds, 0) })}
              </p>
            </Panel>
          )}
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          {card?.tracer_tg_agent && (
            <Panel title={t("card.agentsTitle")}>
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {t("card.agents", { n: formatNumber(card.tracer_tg_agent.trajectories), a: num(card.tracer_tg_agent.detection_auroc, 2), b: pct(card.tracer_tg_agent.tracer_exact), c: pct(card.tracer_tg_agent.tracer_within_1), d: pct(card.tracer_tg_agent.baseline_random) })}
                {card.tracer_agenthallu && t("card.agentsHallu", { n: formatNumber(card.tracer_agenthallu.trajectories), a: pct(card.tracer_agenthallu.exact), b: pct(card.tracer_agenthallu.random), c: num(card.tracer_agenthallu.detection_auroc, 2) })}
              </p>
            </Panel>
          )}
          {card?.healing && (
            <Panel title={t("card.healTitle")}>
              <p className="m-0 text-sm leading-relaxed text-fog-300">
                {t("card.heal", { a: pct(card.healing.hallucinated.grounded_after_among_flagged as number), b: num(card.healing.hallucinated.mean_risk_before as number), c: num(card.healing.hallucinated.mean_risk_after as number), d: pct(card.healing.hallucinated.edit_recall as number), e: pct(card.healing.hallucinated.edit_precision as number), f: pct(card.healing.grounded.text_edited as number, 1) })}
              </p>
            </Panel>
          )}
        </div>

        {card && <div className="grid gap-5 lg:grid-cols-2">
          <Panel title={t("card.limits")}>
            <ul className="m-0 flex list-disc flex-col gap-2 ps-5 text-sm leading-relaxed text-fog-300">
              {LIMITS.map((l) => (
                <li key={l}>{t(l)}</li>
              ))}
            </ul>
          </Panel>
          <Panel title={t("card.lockedSets")}>
            {locked ? (
              <ul className="m-0 flex list-disc flex-col gap-1.5 ps-5 text-sm leading-relaxed text-fog-300">
                <li>{t("card.locked1", { a: num(locked.auroc, 3), b: num(locked.f1, 3), c: num(locked.span_f1, 3), n: formatNumber(locked.answers) })}</li>
                {card?.locked_halueval && <li>{t("card.locked2", { list: perTask(Object.entries(card.locked_halueval).map(([task, v]) => [task, v.auroc]), t("common.comma")), n: formatNumber(Object.values(card.locked_halueval)[0]?.answers ?? 0) })}</li>}
                {card?.locked_agenthallu && <li>{t("card.locked3", { n: formatNumber(card.locked_agenthallu.trajectories), a: pct(card.locked_agenthallu.exact), b: pct(card.locked_agenthallu.random), c: num(card.locked_agenthallu.detection_auroc, 2) })}</li>}
                <li>{t("card.locked4")}</li>
                <li>{t("card.locked5")}</li>
              </ul>
            ) : (
              <p className="m-0 text-sm leading-relaxed text-fog-300">{t("card.notOpened")}</p>
            )}
            <span className="label mt-2">{t("card.dataTitle")}</span>
            <p className="m-0 text-sm leading-relaxed text-fog-300">
              {t("card.data")}
            </p>
          </Panel>
        </div>}

        {card && (
          <details className="text-xs text-fog-400">
            <summary className="cursor-pointer">{t("card.sources")}</summary>
            <ul className="mt-2 flex list-none flex-col gap-1 p-0 font-mono" dir="ltr">
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
