import { useId } from "react";
import type { CheckInput, Task } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

const MAX_SOURCES = 10;

export function InputForm({ value, onChange, onSubmit, disabled, submitLabel = "Check the answer" }: { value: CheckInput; onChange: (v: CheckInput) => void; onSubmit: () => void; disabled?: boolean; submitLabel?: string }) {
  const id = useId();
  const { health } = useWorkspace();
  const edit = (patch: Partial<CheckInput>) => onChange({ ...value, ...patch, exampleId: null });
  const setSource = (i: number, text: string) => edit({ sources: value.sources.map((s, j) => (j === i ? text : s)) });
  const ready = value.answer.trim() && (value.sources.some((s) => s.trim()) || value.question.trim());

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready && !disabled) onSubmit();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && ready && !disabled) {
          e.preventDefault();
          onSubmit();
        }
      }}
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${id}-q`} className="label">
          Question <span className="text-fog-400/70">(optional, needed to judge retrieval and omissions)</span>
        </label>
        <input id={`${id}-q`} className="field" value={value.question} maxLength={1000} onChange={(e) => edit({ question: e.target.value })} placeholder="What was the AI asked?" />
      </div>

      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="label mb-1.5">Sources the answer should rest on</legend>
        {value.sources.map((source, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="mt-3 w-6 shrink-0 text-right font-mono text-xs text-beam-400" aria-hidden="true">
              [{i + 1}]
            </span>
            <label htmlFor={`${id}-s${i}`} className="sr-only">
              Source {i + 1}
            </label>
            <textarea id={`${id}-s${i}`} className="field min-h-[76px] resize-y text-sm" rows={3} maxLength={20000} value={source} onChange={(e) => setSource(i, e.target.value)} placeholder="Paste a retrieved passage" />
            {value.sources.length > 1 && (
              <button type="button" className="mt-2 grid h-9 w-9 shrink-0 place-items-center rounded-full text-fog-400 hover:bg-ink-700 hover:text-fog-100" aria-label={`Remove source ${i + 1}`} onClick={() => edit({ sources: value.sources.filter((_, j) => j !== i) })}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            )}
          </div>
        ))}
        {value.sources.length < MAX_SOURCES && (
          <button type="button" className="chip ml-8 self-start" onClick={() => edit({ sources: [...value.sources, ""] })}>
            + Add a source
          </button>
        )}
      </fieldset>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${id}-a`} className="label">
          AI answer to check
        </label>
        <textarea id={`${id}-a`} className="field min-h-[120px] resize-y" rows={5} maxLength={5000} value={value.answer} onChange={(e) => edit({ answer: e.target.value })} placeholder="Paste the generated answer" />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-t`} className="label">
            Kind of task
          </label>
          <select id={`${id}-t`} className="field h-11 py-0" value={value.task} onChange={(e) => edit({ task: e.target.value as Task })}>
            <option value="qa">Question answering</option>
            <option value="summary">Summary</option>
            <option value="data2text">Data to text</option>
            <option value="other">Other</option>
          </select>
        </div>
        {health && health.profiles.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-p`} className="label">
              Domain profile
            </label>
            <select id={`${id}-p`} className="field h-11 py-0" value={value.profile ?? ""} onChange={(e) => edit({ profile: e.target.value || null })}>
              <option value="">RAGTruth (default)</option>
              {health.profiles.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
        )}
        <button type="submit" className="btn btn-primary ml-auto" disabled={!ready || disabled}>
          {submitLabel}
        </button>
      </div>
      <span className="text-xs text-fog-400">Ctrl + Enter also runs the check. Nothing is sent outside this computer.</span>
    </form>
  );
}
