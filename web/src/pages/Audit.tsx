import { useRef, useState } from "react";
import { Panel } from "../components/report/Panels";
import { Heading } from "../layers/Heading";
import { api } from "../lib/api";
import { BLAME, GRADE_COLOR, LANE, pct, VERDICT } from "../lib/format";
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
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ background: colors?.[k] ?? "var(--color-beam-500)" }} aria-hidden="true" />
              {labels?.[k] ?? k.replaceAll("_", " ")}
            </span>
            <span className="font-mono text-fog-300">
              {v} <span className="text-fog-400">· {pct(v / total)}</span>
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
  const progress = [...audit.events].reverse().find((e) => e.type === "progress") as { done: number; total: number } | undefined;

  const load = async (f: File) => {
    if (f.size > MAX_BYTES) {
      setProblem(`The file is ${(f.size / 1e6).toFixed(1)} MB; the limit is 2 MB (about 100 answers).`);
      return;
    }
    setProblem(null);
    setName(f.name);
    setText(await f.text());
  };

  const sample = async () => {
    const s = await api.auditSample();
    setName(`sample log (${s.answers} answers)`);
    setText(s.jsonl);
  };

  const result = audit.result;
  const s = result?.summary;

  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-6 px-4 py-8 sm:px-8">
      <div className="flex max-w-3xl flex-col gap-2">
        <Heading className="m-0 text-[34px] font-normal leading-tight tracking-tight">Audit a RAG system</Heading>
        <p className="m-0 text-[15px] leading-relaxed text-fog-300">
          Run a whole log of a system's answers through the guardian and get its health: the estimated hallucination rate with an interval, which lane each answer goes to, who is to blame, which kinds of error appear and which documents sit behind the flagged claims.
        </p>
      </div>

      <Panel title="The log">
        <p className="m-0 text-sm leading-relaxed text-fog-300">
          One JSON object per line: <code className="rounded bg-ink-700 px-1.5 py-0.5 font-mono text-[12.5px]">{'{"id": 1, "question": "...", "sources": ["..."], "answer": "..."}'}</code>, or the project's Sample format (then the true rate is shown too). At most 100 answers; about 3 seconds each on this laptop.
        </p>
        <div className="flex flex-wrap gap-2">
          <input ref={file} type="file" accept=".jsonl,.json,.txt" className="sr-only" id="audit-file" onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} />
          <label htmlFor="audit-file" className="btn btn-ghost">
            Choose a file
          </label>
          <button type="button" className="btn btn-ghost" onClick={sample}>
            Use the sample log
          </button>
          {name && <span className="self-center text-sm text-fog-300">{name}</span>}
        </div>
        <label htmlFor="audit-text" className="label">
          Or paste the lines
        </label>
        <textarea id="audit-text" className="field min-h-[140px] resize-y font-mono text-[12.5px]" value={text} spellCheck={false} onChange={(e) => { setText(e.target.value); setName(null); }} />
        {problem && (
          <p role="alert" className="m-0 text-sm text-warn">
            {problem}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn btn-primary" disabled={!ready || !lines || audit.running} onClick={() => audit.run("/api/audit", { jsonl: text }, () => "idle")}>
            {audit.running ? "Auditing…" : `Audit ${lines || ""} answer${lines === 1 ? "" : "s"}`}
          </button>
          {audit.running && progress && (
            <div className="flex min-w-[240px] flex-1 items-center gap-3" aria-live="polite">
              <div className="h-1.5 flex-1 rounded-full bg-ink-600">
                <div className="h-1.5 rounded-full bg-beam-400 transition-[width]" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
              </div>
              <span className="font-mono text-xs text-fog-300">
                {`${progress.done} / ${progress.total}`}
              </span>
            </div>
          )}
        </div>
      </Panel>

      {audit.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-rose-200">
          The audit did not finish: {audit.error}
        </div>
      )}

      {result && s && (
        <div key={`${s.answers}:${result.seconds}`} className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-mono text-xs text-fog-400">
              {s.answers} answers audited in {result.seconds.toFixed(0)} s
            </span>
            <button type="button" className="btn btn-ghost" onClick={() => downloadJson("truth-guardian-audit.json", result)}>
              Download the audit
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Panel title="Estimated hallucination rate" className="md:col-span-1">
              <span className="font-mono text-[44px] leading-none">{pct(s.estimated_hallucination_rate, 1)}</span>
              <span className="text-sm text-fog-300">
                95% interval {pct(s.estimate_interval[0], 1)} to {pct(s.estimate_interval[1], 1)} (mean calibrated risk, bootstrap)
              </span>
              {s.true_hallucination_rate != null && <span className="text-sm text-fog-200">Labelled rate in this log: {pct(s.true_hallucination_rate, 1)}</span>}
              <span className="text-xs text-fog-400">On a domain unlike RAGTruth the estimate can be far off; fit a domain profile first.</span>
            </Panel>
            <Breakdown title="Triage lanes" counts={s.lanes} colors={Object.fromEntries(Object.entries(LANE).map(([k, v]) => [k, v.color]))} labels={Object.fromEntries(Object.entries(LANE).map(([k, v]) => [k, `${v.label}: ${v.hint}`]))} />
            <Breakdown title="Verdicts" counts={s.verdicts} colors={Object.fromEntries(Object.entries(VERDICT).map(([k, v]) => [k, v.color]))} />
            <Breakdown title="Grades" counts={s.grades} colors={GRADE_COLOR as Record<string, string>} labels={{ A: "A", B: "B", C: "C", D: "D", F: "F" }} />
            <Breakdown title="Who is to blame" counts={s.blame} labels={BLAME} />
            <Breakdown title="Kinds of error in flagged claims" counts={s.error_types} />
            <Breakdown title="Cautions" counts={s.cautions} />
            <Breakdown title="Documents behind flagged claims" counts={s.flagged_documents} />
          </div>
          <Panel title="Riskiest answers">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <thead className="text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pr-3 font-normal">Answer</th>
                    <th className="py-2 pr-3 font-normal">Grade</th>
                    <th className="py-2 pr-3 font-normal">Risk</th>
                    <th className="py-2 pr-3 font-normal">Flagged claim</th>
                    <th className="py-2 font-normal">Why</th>
                  </tr>
                </thead>
                <tbody>
                  {s.worst.map((w) => (
                    <tr key={w.id} className="border-t border-white/6 align-top">
                      <td className="py-2.5 pr-3 font-mono text-xs text-fog-300">{w.id}</td>
                      <td className="py-2.5 pr-3" style={{ color: GRADE_COLOR[w.grade as Grade] }}>
                        {w.grade}
                      </td>
                      <td className="py-2.5 pr-3 font-mono">{w.risk.toFixed(2)}</td>
                      <td className="max-w-[380px] py-2.5 pr-3 text-fog-200">{w.claim}</td>
                      <td className="py-2.5 text-fog-300">{w.explanation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Every answer">
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <thead className="sticky top-0 bg-ink-800 text-xs text-fog-400">
                  <tr>
                    <th className="py-2 pr-3 font-normal">Answer</th>
                    <th className="py-2 pr-3 font-normal">Verdict</th>
                    <th className="py-2 pr-3 font-normal">Grade</th>
                    <th className="py-2 pr-3 font-normal">Lane</th>
                    <th className="py-2 pr-3 font-normal">Flagged claims</th>
                    <th className="py-2 font-normal">Start of the answer</th>
                  </tr>
                </thead>
                <tbody>
                  {result.answers.map((a) => (
                    <tr key={a.id} className="border-t border-white/6 align-top">
                      <td className="py-2 pr-3 font-mono text-xs text-fog-300">{a.id}</td>
                      <td className="py-2 pr-3" style={{ color: VERDICT[a.verdict].color }}>
                        {VERDICT[a.verdict].label}
                      </td>
                      <td className="py-2 pr-3">{a.grade}</td>
                      <td className="py-2 pr-3">{a.lane ? LANE[a.lane].label : "n/a"}</td>
                      <td className="py-2 pr-3 font-mono">{a.flagged}</td>
                      <td className="py-2 text-fog-300">{a.answer}</td>
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
