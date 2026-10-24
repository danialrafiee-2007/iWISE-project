import { useId, useRef, useState, type DragEvent } from "react";
import { postJson } from "../lib/api";
import type { CheckInput, Task } from "../lib/types";
import { useWorkspace } from "../lib/workspace";

const MAX_SOURCES = 10;
const MAX_FILE_BYTES = 10_000_000;
const ACCEPT = ".pdf,.docx,.txt,.md,.markdown,.html,.htm,.csv,.json,.log";
const LONG_SOURCES = 60_000;

type Read = { name: string; kind: string; pages: number | null; chars: number; parts: string[] };

async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** Puts the parts in empty source slots first, then appends, up to MAX_SOURCES; returns how many were placed. */
function place(value: CheckInput, parts: string[], labels: string[]): { next: CheckInput; placed: number } {
  const sources = [...value.sources];
  const names = sources.map((_, i) => value.sourceNames?.[i] ?? null);
  let placed = 0;
  for (let k = 0; k < parts.length; k++) {
    const empty = sources.findIndex((s) => !s.trim());
    if (empty >= 0) {
      sources[empty] = parts[k];
      names[empty] = labels[k];
    } else if (sources.length < MAX_SOURCES) {
      sources.push(parts[k]);
      names.push(labels[k]);
    } else break;
    placed++;
  }
  return { next: { ...value, sources, sourceNames: names, exampleId: null }, placed };
}

export function InputForm({ value, onChange, onSubmit, disabled, submitLabel = "Check the answer" }: { value: CheckInput; onChange: (v: CheckInput) => void; onSubmit: () => void; disabled?: boolean; submitLabel?: string }) {
  const id = useId();
  const { health } = useWorkspace();
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const [note, setNote] = useState<{ text: string; bad: boolean } | null>(null);
  const names = value.sources.map((_, i) => value.sourceNames?.[i] ?? null);
  const edit = (patch: Partial<CheckInput>) => onChange({ ...value, ...patch, exampleId: null });
  const setSource = (i: number, text: string) => edit({ sources: value.sources.map((s, j) => (j === i ? text : s)) });
  const removeSource = (i: number) => edit({ sources: value.sources.filter((_, j) => j !== i), sourceNames: names.filter((_, j) => j !== i) });
  const ready = value.answer.trim() && (value.sources.some((s) => s.trim()) || value.question.trim());
  const totalChars = value.sources.reduce((n, s) => n + s.length, 0);

  const addFiles = async (files: File[]) => {
    if (!files.length) return;
    setReading(true);
    setNote(null);
    let current = value;
    const done: string[] = [];
    try {
      for (const file of files) {
        if (file.size > MAX_FILE_BYTES) {
          setNote({ text: `${file.name} is ${(file.size / 1e6).toFixed(1)} MB; the limit is 10 MB.`, bad: true });
          continue;
        }
        let read: Read;
        try {
          read = await postJson<Read>("/api/documents", { name: file.name, data: await toBase64(file) });
        } catch (e) {
          setNote({ text: `${file.name}: ${e instanceof Error ? e.message : String(e)}.`, bad: true });
          continue;
        }
        const n = read.parts.length;
        const labels = read.parts.map((_, k) => `${file.name}${n > 1 ? ` · part ${k + 1} of ${n}` : ""}`);
        const { next, placed } = place(current, read.parts, labels);
        current = next;
        const size = `${read.pages ? `${read.pages} page${read.pages === 1 ? "" : "s"}, ` : ""}${read.chars.toLocaleString("en")} characters`;
        done.push(placed === n ? `${file.name} (${size}) as ${n} source${n === 1 ? "" : "s"}` : `${placed} of ${n} parts of ${file.name}: at most ${MAX_SOURCES} sources fit`);
        if (placed < n) break;
      }
      onChange(current);
      if (done.length) setNote({ text: `Added ${done.join("; ")}.`, bad: done.some((d) => d.includes("at most")) });
    } finally {
      setReading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles([...e.dataTransfer.files]);
  };

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

      <fieldset
        data-tour="sources"
        className={`m-0 flex flex-col gap-2 rounded-2xl border border-dashed p-0 transition-colors ${dragging ? "border-beam-400 bg-beam-400/5 p-3" : "border-transparent"}`}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("Files")) {
            e.preventDefault();
            setDragging(true);
          }
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={onDrop}
      >
        <legend className="label mb-1.5">Sources the answer should rest on</legend>
        {value.sources.map((source, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="mt-3 w-6 shrink-0 text-right font-mono text-xs text-beam-400" aria-hidden="true">
              {`[${i + 1}]`}
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              {names[i] && <span className="truncate font-mono text-[11px] text-fog-400">{`from ${names[i]}`}</span>}
              <label htmlFor={`${id}-s${i}`} className="sr-only">
                {`Source ${i + 1}`}
              </label>
              <textarea id={`${id}-s${i}`} className="field min-h-[76px] resize-y text-sm" rows={3} maxLength={20000} value={source} onChange={(e) => setSource(i, e.target.value)} placeholder="Paste a retrieved passage, or drop a PDF, Word or text file here" />
            </div>
            {value.sources.length > 1 && (
              <button type="button" className="mt-2 grid h-9 w-9 shrink-0 place-items-center rounded-full text-fog-400 hover:bg-ink-700 hover:text-fog-100" aria-label={`Remove source ${i + 1}`} onClick={() => removeSource(i)}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            )}
          </div>
        ))}
        <div className="ml-8 flex flex-wrap items-center gap-2">
          {value.sources.length < MAX_SOURCES && (
            <button type="button" className="chip" onClick={() => edit({ sources: [...value.sources, ""], sourceNames: [...names, null] })}>
              + Add a source
            </button>
          )}
          <input ref={fileInput} id={`${id}-files`} type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => addFiles([...(e.target.files ?? [])])} />
          <label htmlFor={`${id}-files`} className={`chip cursor-pointer ${reading ? "pointer-events-none opacity-60" : ""}`} data-tour="upload">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
            </svg>
            {reading ? "Reading the file…" : "Add from files"}
          </label>
          <span className="text-xs text-fog-400">PDF, Word, HTML, Markdown or text, up to 10 MB; or drop files here</span>
        </div>
        {note && (
          <p role="status" className={`m-0 ml-8 text-sm ${note.bad ? "text-warn" : "text-fog-300"}`}>
            {note.text}
          </p>
        )}
        {totalChars > LONG_SOURCES && <p className="m-0 ml-8 text-xs text-fog-400">{`${totalChars.toLocaleString("en")} characters of sources: the check takes longer on long documents.`}</p>}
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
