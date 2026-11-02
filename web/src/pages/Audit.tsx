import { useRef, useState } from "react";
import { BackToCheck } from "../components/CheckLinks";
import { Panel } from "../components/report/Panels";
import { formatNumber, t, useI18n } from "../i18n";
import { Heading } from "../layers/Heading";
import { api } from "../lib/api";
import { BLAME, GRADE_COLOR, LANE, num, pct, VERDICT } from "../lib/format";
import type { AuditRow, AuditSummary, Grade } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useWorkspace } from "../lib/workspace";
import { downloadJson } from "./Analyze";

const MAX_BYTES = 2_000_000;

function Breakdown({ title, counts, colors, labels }: { title: string; counts: Record<string, number>; colors?: Record<string, string>; labels?: Record<string, string> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!total) return null;
  return (
    <Panel title={title}>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-ink-600" aria-hidden="true">
        {entries.map(([k, v]) => (
          <div key={k} style={{ width: `${(v / total) * 100}%`, background: colors?.[k] ?? "var(--color-beam-500)" }} />
        ))}
      </div>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-sm">
        {entries.map(([k, v]) => (
          <li key={k} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2" dir="auto">
              <span className="h-2 w-2 rounded-full" style={{ background: colors?.[k] ?? "var(--color-beam-500)" }} aria-hidden="true" />
              {labels?.[k] ?? k.replaceAll("_", " ")}
            </span>
            <span className="font-mono text-fog-300">
              {formatNumber(v)} <span className="text-fog-400">· {pct(v / total)}</span>
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function Audit() {
  const { health } = useWorkspace();
  const [text, setText] = useState("");
  const [name, setName] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const audit = useStream<{ summary: AuditSummary; answers: AuditRow[]; seconds: number }>();
  const ready = health?.state === "ready";
  const lines = text.split("\n").filter((l) => l.trim()).length;
  const { tp } = useI18n();
  const progress = [...audit.events].reverse().find((e) => e.type === "progress") as { done: number; total: number } | undefined;

  const load = async (f: File) => {
    if (f.size > MAX_BYTES) {
      setProblem(t("audit.tooBig", { mb: num(f.size / 1e6, 1) }));
      return;
    }
    setProblem(null);
    setName(f.name);
    setText(await f.text());
  };

  const sample = async () => {
    const s = await api.auditSample();
    setName(t("audit.sampleName", { n: formatNumber(s.answers) }));
    setText(s.jsonl);
  };

  const result = audit.result;
  const s = result?.summary;

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <BackToCheck />
      <div className="flex max-w-3xl flex-col gap-2">
        <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">{t("audit.title")}</Heading>
        <p className="m-0 text-[15px] leading-relaxed text-fog-300">
          {t("audit.lead")}
        </p>
      </div>

      <Panel title={t("audit.log")}>
        <p className="m-0 text-sm leading-relaxed text-fog-300">
          {t("audit.formatPre")}
          <code className="rounded bg-ink-700 px-1.5 py-0.5 font-mono text-[12.5px]" dir="ltr">{'{"id": 1, "question": "...", "sources": ["..."], "answer": "..."}'}</code>
          {t("audit.formatPost")}
        </p>
        <div className="flex flex-wrap gap-2">
          <input ref={file} type="file" accept=".jsonl,.json,.txt" className="sr-only" id="audit-file" onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} />
          <label htmlFor="audit-file" className="btn btn-ghost">
            {t("audit.choose")}
          </label>
          <button type="button" className="btn btn-ghost" onClick={sample}>
            {t("audit.sample")}
          </button>
          {name && <span className="self-center text-sm text-fog-300" dir="auto">{name}</span>}
        </div>
        <label htmlFor="audit-text" className="label">
          {t("audit.paste")}
        </label>
        <textarea id="audit-text" className="field min-h-[140px] resize-y font-mono text-[12.5px]" dir="ltr" value={text} spellCheck={false} onChange={(e) => { setText(e.target.value); setName(null); }} />
        {problem && (
          <p role="alert" className="m-0 text-sm text-warn-ink">
            {problem}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-primary" disabled={!ready || !lines || audit.running} onClick={() => audit.run("/api/audit", { jsonl: text }, () => "idle")}>
            {audit.running ? t("audit.auditing") : lines ? tp("audit.run", lines) : t("audit.runNone")}
          </button>
          {audit.running && progress && (
            <div className="flex min-w-[240px] flex-1 items-center gap-3" aria-live="polite">
              <div className="h-1.5 flex-1 rounded-full bg-ink-600">
                <div className="h-1.5 rounded-full bg-beam-400 transition-[width]" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
              </div>
              <span className="font-mono text-xs text-fog-300">
                {`${formatNumber(progress.done)} / ${formatNumber(progress.total)}`}
              </span>
            </div>
          )}
        </div>
      </Panel>

      {audit.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
          {t("audit.failed", { error: audit.error })}
        </div>
      )}

      {result && s && (
        <div key={`${s.answers}:${result.seconds}`} className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-mono text-xs text-fog-400">
              {t("audit.done", { n: formatNumber(s.answers), s: num(result.seconds, 0) })}
            </span>
            <button type="button" className="btn btn-ghost" onClick={() => downloadJson("truth-guardian-audit.json", result)}>
              {t("audit.download")}
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Panel title={t("audit.rate")} className="md:col-span-1">
              <span className="font-mono text-[44px] leading-none">{pct(s.estimated_hallucination_rate, 1)}</span>
              <span className="text-sm text-fog-300">
                {t("audit.interval", { a: pct(s.estimate_interval[0], 1), b: pct(s.estimate_interval[1], 1) })}
              </span>
              {s.true_hallucination_rate != null && <span className="text-sm text-fog-200">{t("audit.labelled", { r: pct(s.true_hallucination_rate, 1) })}</span>}
              <span className="text-xs text-fog-400">{t("audit.rateNote")}</span>
            </Panel>
            <Breakdown title={t("audit.lanes")} counts={s.lanes} colors={Object.fromEntries(Object.entries(LANE).map(([k, v]) => [k, v.color]))} labels={Object.fromEntries(Object.entries(LANE).map(([k, v]) => [k, t("audit.laneLabel", { label: v.label, hint: v.hint })]))} />
            <Breakdown title={t("audit.verdicts")} counts={s.verdicts} colors={Object.fromEntries(Object.entries(VERDICT).map(([k, v]) => [k, v.color]))} labels={Object.fromEntries(Object.entries(VERDICT).map(([k, v]) => [k, v.label]))} />
            <Breakdown title={t("audit.grades")} counts={s.grades} colors={GRADE_COLOR as Record<string, string>} labels={{ A: "A", B: "B", C: "C", D: "D", F: "F" }} />
            <Breakdown title={t("audit.blame")} counts={s.blame} labels={BLAME} />
            <Breakdown title={t("audit.errors")} counts={s.error_types} />
            <Breakdown title={t("audit.cautions")} counts={s.cautions} />
            <Breakdown title={t("audit.docs")} counts={s.flagged_documents} />
          </div>
          <Panel title={t("audit.riskiest")}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-start text-sm">
                <thead className="text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pe-3 font-normal">{t("col.answer")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.grade")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.risk")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.flaggedClaim")}</th>
                    <th className="py-2 font-normal">{t("col.why")}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.worst.map((w) => (
                    <tr key={w.id} className="border-t border-hair align-top">
                      <td className="py-2.5 pe-3 font-mono text-xs text-fog-300">{w.id}</td>
                      <td className="py-2.5 pe-3" style={{ color: GRADE_COLOR[w.grade as Grade] }}>
                        {w.grade}
                      </td>
                      <td className="py-2.5 pe-3 font-mono">{num(w.risk)}</td>
                      <td className="max-w-[380px] py-2.5 pe-3 text-fog-200" dir="auto">{w.claim}</td>
                      <td className="py-2.5 text-fog-300" dir="auto">{w.explanation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title={t("audit.every")}>
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full min-w-[640px] border-collapse text-start text-sm">
                <thead className="sticky top-0 bg-ink-800 text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pe-3 font-normal">{t("col.answer")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.verdict")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.grade")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.lane")}</th>
                    <th className="py-2 pe-3 font-normal">{t("col.flagged")}</th>
                    <th className="py-2 font-normal">{t("col.start")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.answers.map((a) => (
                    <tr key={a.id} className="border-t border-hair align-top">
                      <td className="py-2 pe-3 font-mono text-xs text-fog-300">{a.id}</td>
                      <td className="py-2 pe-3" style={{ color: VERDICT[a.verdict].color }}>
                        {VERDICT[a.verdict].label}
                      </td>
                      <td className="py-2 pe-3">{a.grade}</td>
                      <td className="py-2 pe-3">{a.lane ? LANE[a.lane].label : t("common.na")}</td>
                      <td className="py-2 pe-3 font-mono">{formatNumber(a.flagged)}</td>
                      <td className="py-2 text-fog-300" dir="auto">{a.answer}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
