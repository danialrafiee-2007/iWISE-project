import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useI18n, type MessageKey } from "../i18n";
import { api, ApiError, checkBody, postJson } from "../lib/api";
import { num, pct, STAGES, STATUS, VERDICT } from "../lib/format";
import { useRouter } from "../lib/router";
import type { CheckInput, Report } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useWorkspace } from "../lib/workspace";

// The landing page's challenge inputs, opened in place: a chat-like box to write or attach the input and send it, and
// the guardian's answer above it. Text goes to the claim check (/api/analyze); an image, a recording or a video goes
// to the local media readers (/api/media/read), whose reading is shown as read: where each piece was found, its
// language and how sure the reader is, and what needs review.

export type InputKind = "text" | "audio" | "image" | "video";

interface Place {
  box: [number, number, number, number] | null;
  start: number | null;
  end: number | null;
}
interface Segment {
  text: string;
  role: "transcript" | "ocr" | "description";
  language: string | null;
  language_confidence: number | null;
  script: string | null;
  confidence: number | null;
  place: Place;
}
interface Reading {
  kind: "audio" | "image" | "video";
  segments: Segment[];
  language: string | null;
  language_confidence: number | null;
  quality: number | null;
  seconds: number;
  needs_review: boolean;
  reasons: string[];
  notes: string[];
}

// Languages offered as a hint, in their own names; without one the readers detect the language themselves.
const LANGUAGES: [string, string][] = [
  ["en", "English"], ["fa", "فارسی"], ["ar", "العربية"], ["zh", "中文"], ["ja", "日本語"], ["ko", "한국어"], ["ru", "Русский"], ["fr", "Français"],
  ["es", "Español"], ["de", "Deutsch"], ["tr", "Türkçe"], ["hi", "हिन्दी"], ["ur", "اردو"], ["am", "አማርኛ"], ["sw", "Kiswahili"],
];
const NAME = Object.fromEntries(LANGUAGES);
const RECORD_LIMIT = 120;

const clock = (s: number | null) => (s == null ? "" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);

async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

function failure(e: unknown, t: (key: MessageKey, vars?: Record<string, string>) => string): string {
  const status = e instanceof ApiError ? e.status : 0;
  if (status === 429) return t("inputs.errBusy");
  if (status === 413) return t("inputs.errBig");
  if (status === 503) return t("inputs.errMissing");
  return t("inputs.errUnread", { error: e instanceof Error ? e.message : String(e) });
}

function useObjectUrl(file: Blob | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) return setUrl(null);
    const made = URL.createObjectURL(file);
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [file]);
  return url;
}

/** The writing box: grows with its text; Enter sends, Shift+Enter starts a new line, like a chat. */
function Composer({ value, onChange, onSend, placeholder, disabled, canSend, actions }: {
  value: string; onChange: (v: string) => void; onSend: () => void; placeholder: string; disabled?: boolean; canSend: boolean; actions?: ReactNode;
}) {
  const { t } = useI18n();
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);
  return (
    <div className="rounded-2xl border border-white/12 bg-white/[0.04] p-2 transition-colors focus-within:border-[var(--tone)]">
      <textarea
        ref={area}
        rows={2}
        dir="auto"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canSend && !disabled) onSend();
          }
        }}
        className="block w-full resize-none border-0 bg-transparent px-2 py-1.5 text-[15px] leading-relaxed text-fog-100 outline-none placeholder:text-fog-400"
      />
      <div className="flex items-center justify-between gap-2 px-1 pt-1">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">{actions}</div>
        <button
          type="button"
          onClick={onSend}
          disabled={!canSend || disabled}
          aria-label={t("inputs.send")}
          title={t("inputs.send")}
          className="grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-full bg-[var(--tone)] text-[#04201b] transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}

const SMALL = "inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-white/12 px-3 py-1 text-xs text-fog-300 hover:border-white/25 hover:text-fog-100";

function Working({ text }: { text: string }) {
  return (
    <p className="m-0 flex items-center gap-2.5 text-sm text-fog-300" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/15 border-t-[var(--tone)]" aria-hidden="true" />
      {text}
    </p>
  );
}

function Problem({ text }: { text: string }) {
  return (
    <p role="alert" className="m-0 rounded-xl border border-[#fb7185]/30 bg-[#fb7185]/10 px-3.5 py-2.5 text-sm text-[#fecdd3]">
      {text}
    </p>
  );
}

/** The panel frame: what to show (scrolls) above, the writing box below. */
function Frame({ children, composer }: { children: ReactNode; composer: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-white/8 bg-black/35 p-4 backdrop-blur-sm [scrollbar-width:thin]">{children}</div>
      {composer}
    </div>
  );
}

// --- text ------------------------------------------------------------------------------------------------------------

function TextPanel() {
  const { t } = useI18n();
  const { health, setInput } = useWorkspace();
  const { navigate } = useRouter();
  const id = useId();
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState("");
  const [question, setQuestion] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [hint, setHint] = useState(false);
  const check = useStream<{ report: Report; seconds: number }>();
  const value: CheckInput = {
    question, answer, task: "qa", profile: null, exampleId: null,
    // Passages are separated by a blank line; the server takes up to ten.
    sources: sources.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean).slice(0, 10),
  };
  const grounded = value.sources.some((s) => s) || question.trim();
  const ready = health?.state === "ready";

  const send = () => {
    if (!grounded) {
      setDrawer(true);
      setHint(true);
      return;
    }
    setHint(false);
    setDrawer(false); // the answer needs the room
    check.run("/api/analyze", checkBody(value));
  };
  const example = async () => {
    const { answers } = await api.examples();
    const chosen = answers.find((a) => a.origin.startsWith("written")) ?? answers[0];
    if (!chosen) return;
    const { example: e } = await api.example(chosen.id);
    setAnswer(e.answer);
    setSources(e.sources.join("\n\n"));
    setQuestion(e.question ?? "");
    setDrawer(true);
  };

  const report = check.result?.report;
  const flagged = report?.claims.filter((c) => c.status !== "supported") ?? [];
  const stage = [...check.events].reverse().find((e) => e.type === "stage");

  return (
    <Frame
      composer={
        <>
          {drawer && (
            <div className="grid gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-2.5">
              <label htmlFor={`${id}-q`} className="sr-only">{t("inputs.question")}</label>
              <input id={`${id}-q`} dir="auto" value={question} maxLength={1000} placeholder={t("inputs.question")} onChange={(e) => setQuestion(e.target.value)} className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2 text-sm text-fog-100 outline-none placeholder:text-fog-400 focus:border-[var(--tone)]" />
              <label htmlFor={`${id}-s`} className="sr-only">{t("inputs.sources")}</label>
              <textarea id={`${id}-s`} dir="auto" rows={3} value={sources} placeholder={t("inputs.sourcesPlaceholder")} onChange={(e) => setSources(e.target.value)} className="w-full resize-y rounded-xl border border-white/10 bg-transparent px-3 py-2 text-sm leading-relaxed text-fog-100 outline-none placeholder:text-fog-400 focus:border-[var(--tone)]" />
            </div>
          )}
          <Composer
            value={answer}
            onChange={setAnswer}
            onSend={send}
            placeholder={t("inputs.answerPlaceholder")}
            canSend={!!answer.trim() && ready}
            disabled={check.running}
            actions={
              <>
                <button type="button" className={SMALL} aria-expanded={drawer} onClick={() => setDrawer((d) => !d)}>
                  {drawer ? "−" : "+"} {t("inputs.sources")}
                </button>
                <button type="button" className={SMALL} onClick={example}>
                  {t("inputs.example")}
                </button>
              </>
            }
          />
        </>
      }
    >
      <div className="flex flex-col gap-3" aria-live="polite">
        {!ready && <Working text={t("common.loadingModels")} />}
        {hint && <p className="m-0 text-sm text-[#fcd34d]">{t("inputs.needSources")}</p>}
        {check.running && <Working text={stage?.type === "stage" ? `${t("inputs.checking")} · ${STAGES[stage.stage] ?? stage.stage}` : t("inputs.checking")} />}
        {check.error && <Problem text={check.error} />}
        {!report && !check.running && !check.error && <p className="m-0 text-sm leading-relaxed text-fog-400">{t("inputs.textEmpty")}</p>}
        {report && !check.running && (
          <>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="rounded-full px-3 py-1 text-sm font-semibold text-[#04201b]" style={{ background: VERDICT[report.verdict].color }}>
                {VERDICT[report.verdict].label}
              </span>
              <span className="font-mono text-sm text-fog-300">{t("inputs.risk", { v: pct(report.risk) })}</span>
              <span className="font-mono text-xs text-fog-400">{t("common.seconds", { s: num(check.result?.seconds ?? 0, 1) })}</span>
            </div>
            {report.diagnosis && report.diagnosis.blame !== "none" && <p className="m-0 text-sm text-fog-300">{report.diagnosis.message}</p>}
            {flagged.length === 0 ? (
              <p className="m-0 text-sm text-fog-300">{t("inputs.allSupported")}</p>
            ) : (
              <>
                <h4 className="m-0 text-xs font-medium uppercase tracking-[0.16em] text-fog-400">{t("inputs.flagged")}</h4>
                <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
                  {flagged.map((c) => (
                    <li key={`${c.start}-${c.end}`} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                      <span className="text-xs font-semibold" style={{ color: STATUS[c.status].color }}>
                        {STATUS[c.status].label}
                      </span>
                      <p className="m-0 mt-1 text-[15px] leading-relaxed text-fog-100" dir="auto">{c.text}</p>
                      <p className="m-0 mt-1 text-sm leading-relaxed text-fog-300" dir="auto">{c.explanation}</p>
                      {c.fixes.filter((f) => f.replacement).map((f) => (
                        <p key={f.start} className="m-0 mt-1 text-sm text-fog-300" dir="auto">
                          {t("inputs.fix")}: <s className="text-[#fda4af]">{f.original}</s> → <span className="text-[#86efac]">{f.replacement}</span>
                        </p>
                      ))}
                    </li>
                  ))}
                </ul>
              </>
            )}
            <button
              type="button"
              className={`${SMALL} self-start`}
              onClick={() => {
                setInput({ ...value, sources: value.sources.length ? value.sources : [""] });
                navigate("/analyze");
              }}
            >
              {t("inputs.openFull")}
            </button>
          </>
        )}
      </div>
    </Frame>
  );
}

// --- media -----------------------------------------------------------------------------------------------------------

function LanguageHint({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useI18n();
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={t("inputs.languageAuto")} className="cursor-pointer rounded-full border border-white/12 bg-[#0a0d12] px-2.5 py-1 text-xs text-fog-300 outline-none hover:text-fog-100">
      <option value="">{t("inputs.languageAuto")}</option>
      {LANGUAGES.map(([code, name]) => (
        <option key={code} value={code}>
          {name}
        </option>
      ))}
    </select>
  );
}

function ReadingView({ reading, onSeek, onHover }: { reading: Reading; onSeek?: (s: number) => void; onHover?: (i: number | null) => void }) {
  const { t } = useI18n();
  const read = reading.segments.map((s, i) => [s, i] as const).filter(([s]) => s.role !== "description");
  const answers = reading.segments.filter((s) => s.role === "description");
  const title = reading.kind === "audio" ? "inputs.heard" : reading.kind === "video" ? "inputs.heardSeen" : "inputs.read";
  const language = (code: string | null) => (code ? NAME[code] ?? code : t("inputs.unknownLanguage"));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs text-fog-400">
        <span className="rounded-full border border-white/12 px-2.5 py-0.5">
          <bdi>{language(reading.language)}</bdi>
          {reading.language_confidence != null ? ` · ${pct(reading.language_confidence)}` : ""}
        </span>
        {reading.quality != null && <span>{t("inputs.quality", { v: pct(reading.quality) })}</span>}
        <span>{t("common.seconds", { s: num(reading.seconds, 1) })}</span>
      </div>
      <h4 className="m-0 text-xs font-medium uppercase tracking-[0.16em] text-fog-400">{t(title)}</h4>
      {read.length === 0 ? (
        <p className="m-0 text-sm text-fog-400">{t("inputs.noText")}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
          {read.map(([s, i]) => (
            <li key={i} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 hover:bg-white/[0.05]" onMouseEnter={() => onHover?.(i)} onMouseLeave={() => onHover?.(null)}>
              {s.place.start != null && (
                <button type="button" disabled={!onSeek} onClick={() => onSeek?.(s.place.start ?? 0)} className="mt-0.5 shrink-0 cursor-pointer rounded border border-white/10 px-1.5 font-mono text-[11px] text-[var(--tone)] disabled:cursor-default" dir="ltr">
                  {clock(s.place.start)}
                  {s.place.end != null && s.place.end !== s.place.start ? `–${clock(s.place.end)}` : ""}
                </button>
              )}
              <span className="min-w-0 flex-1 text-[15px] leading-relaxed text-fog-100" dir="auto">{s.text}</span>
              <span className="mt-1 shrink-0 font-mono text-[10px] text-fog-400" dir="ltr">
                {s.language ?? s.script ?? "?"}
                {s.confidence != null ? ` ${Math.round(s.confidence * 100)}%` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {answers.map((s, i) => (
        <div key={`a${i}`} className="rounded-xl border border-[var(--tone)]/25 bg-[var(--tone)]/[0.06] p-3">
          <h4 className="m-0 text-xs font-medium uppercase tracking-[0.16em] text-[var(--tone)]">{t("inputs.modelAnswer")}</h4>
          <p className="m-0 mt-1.5 text-[15px] leading-relaxed text-fog-100" dir="auto">{s.text}</p>
          <p className="m-0 mt-1.5 text-xs text-fog-400">{t("inputs.opinion")}</p>
        </div>
      ))}
      {reading.needs_review && (
        <div className="rounded-xl border border-[#fbbf24]/30 bg-[#fbbf24]/[0.08] p-3 text-sm text-[#fde68a]">
          <strong className="font-semibold">{t("inputs.review")}</strong>
          <ul className="m-0 mt-1 list-disc ps-5">
            {reading.reasons.map((r) => (
              <li key={r} dir="ltr" className="text-start">{r}</li>
            ))}
          </ul>
        </div>
      )}
      {reading.notes.length > 0 && (
        <ul className="m-0 list-none p-0 text-xs text-fog-400">
          {reading.notes.map((n) => (
            <li key={n} dir="ltr" className="text-start">· {n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function useReader() {
  const { t } = useI18n();
  const { setBusy } = useWorkspace();
  const [running, setRunning] = useState(false);
  const [reading, setReading] = useState<Reading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const read = async (file: Blob, name: string, kind: Exclude<InputKind, "text">, language: string, question?: string) => {
    setRunning(true);
    setBusy(true);
    setError(null);
    setReading(null);
    try {
      const body = { name, kind, data: await toBase64(file), languages: language ? [language] : [], question: question?.trim() || null };
      setReading((await postJson<{ reading: Reading }>("/api/media/read", body)).reading);
    } catch (e) {
      setError(failure(e, t));
    } finally {
      setRunning(false);
      setBusy(false);
    }
  };
  return { running, reading, error, read, clear: () => (setReading(null), setError(null)) };
}

function Picker({ accept, label, onFile }: { accept: string; label: string; onFile: (f: File) => void }) {
  const id = useId();
  const [over, setOver] = useState(false);
  return (
    <label
      htmlFor={id}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const file = e.dataTransfer.files[0];
        if (file) onFile(file);
      }}
      className={`flex min-h-[150px] cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed p-6 text-center text-sm transition-colors ${over ? "border-[var(--tone)] bg-[var(--tone)]/[0.07] text-fog-100" : "border-white/15 text-fog-300 hover:border-white/30"}`}
    >
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
      </svg>
      {label}
      <input id={id} type="file" accept={accept} className="sr-only" onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
    </label>
  );
}

function VisualPanel({ kind }: { kind: "image" | "video" }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState("");
  const [lit, setLit] = useState<number | null>(null);
  const [size, setSize] = useState<[number, number] | null>(null);
  const url = useObjectUrl(file);
  const player = useRef<HTMLVideoElement>(null);
  const reader = useReader();

  useEffect(() => {
    if (kind !== "image") return;
    const onPaste = (e: ClipboardEvent) => {
      const pasted = [...(e.clipboardData?.files ?? [])].find((f) => f.type.startsWith("image/"));
      if (pasted) choose(pasted);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [kind]);

  const choose = (f: File) => {
    setFile(f);
    setSize(null);
    reader.clear();
  };
  const send = () => file && reader.read(file, file.name, kind, language, question);
  const boxes = reader.reading?.segments.map((s, i) => [s, i] as const).filter(([s]) => s.role === "ocr" && s.place.box) ?? [];

  return (
    <Frame
      composer={
        <Composer
          value={question}
          onChange={setQuestion}
          onSend={send}
          placeholder={t("inputs.ask")}
          canSend={!!file}
          disabled={reader.running}
          actions={
            <>
              <LanguageHint value={language} onChange={setLanguage} />
              {file && (
                <label className={SMALL}>
                  {t("inputs.change")}
                  <input type="file" accept={kind === "image" ? "image/*" : "video/*"} className="sr-only" onChange={(e) => e.target.files?.[0] && choose(e.target.files[0])} />
                </label>
              )}
            </>
          }
        />
      }
    >
      <div className="flex flex-col gap-4">
        {!file || !url ? (
          <Picker accept={kind === "image" ? "image/*" : "video/*"} label={t(kind === "image" ? "inputs.chooseImage" : "inputs.chooseVideo")} onFile={choose} />
        ) : kind === "image" ? (
          <div className="relative self-center">
            <img src={url} alt={file.name} className="block max-h-[28vh] max-w-full rounded-xl" onLoad={(e) => setSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])} />
            {size && boxes.map(([s, i]) => {
              const [x, y, w, h] = s.place.box!;
              return (
                <span key={i} aria-hidden="true" className={`pointer-events-none absolute rounded-sm border-2 transition-colors ${lit === i ? "border-[#fbbf24] bg-[#fbbf24]/20" : "border-[var(--tone)]/70"}`}
                  style={{ left: `${(x / size[0]) * 100}%`, top: `${(y / size[1]) * 100}%`, width: `${(w / size[0]) * 100}%`, height: `${(h / size[1]) * 100}%` }} />
              );
            })}
          </div>
        ) : (
          <video ref={player} src={url} controls className="block max-h-[28vh] w-full rounded-xl bg-black" />
        )}
        {reader.running && <Working text={t(question.trim() ? "inputs.readingAsk" : "inputs.reading")} />}
        {reader.error && <Problem text={reader.error} />}
        {reader.reading && <ReadingView reading={reader.reading} onHover={setLit} onSeek={kind === "video" ? (s) => player.current && ((player.current.currentTime = s), player.current.play()) : undefined} />}
      </div>
    </Frame>
  );
}

function AudioPanel() {
  const { t } = useI18n();
  const [file, setFile] = useState<Blob | null>(null);
  const [language, setLanguage] = useState("");
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [micError, setMicError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const player = useRef<HTMLAudioElement>(null);
  const timer = useRef(0);
  const url = useObjectUrl(file);
  const reader = useReader();

  useEffect(() => () => {
    window.clearInterval(timer.current);
    recorder.current?.stream.getTracks().forEach((track) => track.stop());
  }, []);

  const start = async () => {
    setMicError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return setMicError(t("inputs.micMissing"));
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/webm"].find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
      const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const parts: Blob[] = [];
      rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(parts, { type: rec.mimeType || "audio/webm" });
        setFile(blob);
        reader.read(blob, rec.mimeType.includes("ogg") ? "recording.ogg" : "recording.webm", "audio", language);
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
      setElapsed(0);
      setFile(null);
      reader.clear();
      const began = Date.now();
      timer.current = window.setInterval(() => {
        const s = Math.floor((Date.now() - began) / 1000);
        setElapsed(s);
        if (s >= RECORD_LIMIT) stop();
      }, 250);
    } catch {
      setMicError(t("inputs.micDenied"));
    }
  };
  const stop = () => {
    window.clearInterval(timer.current);
    setRecording(false);
    if (recorder.current?.state === "recording") recorder.current.stop();
  };

  return (
    <Frame
      composer={
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/12 bg-white/[0.04] p-2.5">
          <button
            type="button"
            onClick={recording ? stop : start}
            disabled={reader.running}
            aria-pressed={recording}
            className={`grid h-12 w-12 shrink-0 cursor-pointer place-items-center rounded-full transition-colors disabled:opacity-40 ${recording ? "animate-pulse bg-[#fb7185] text-white" : "bg-[var(--tone)] text-[#04201b]"}`}
            aria-label={recording ? t("inputs.stop") : t("inputs.record")}
            title={recording ? t("inputs.stop") : t("inputs.record")}
          >
            {recording ? (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path d="M5 11a7 7 0 0014 0M12 18v3" />
              </svg>
            )}
          </button>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="text-sm text-fog-100">{recording ? t("inputs.recording", { s: clock(elapsed) }) : t("inputs.record")}</span>
            <span className="text-xs text-fog-400">{t("inputs.audioHint")}</span>
          </div>
          {/* On a narrow screen these go to a row of their own, leaving the first to the button and its words. */}
          <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
            <LanguageHint value={language} onChange={setLanguage} />
            <label className={SMALL}>
              {t("inputs.chooseAudio")}
              <input type="file" accept="audio/*" className="sr-only" onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setFile(f);
                  reader.read(f, f.name, "audio", language);
                }
              }} />
            </label>
          </div>
        </div>
      }
    >
      <div className="flex flex-col gap-4" aria-live="polite">
        {micError && <Problem text={micError} />}
        {url && <audio ref={player} src={url} controls className="w-full" />}
        {!file && !recording && <p className="m-0 text-sm leading-relaxed text-fog-400">{t("inputs.audioEmpty")}</p>}
        {reader.running && <Working text={t("inputs.listening")} />}
        {reader.error && <Problem text={reader.error} />}
        {reader.reading && <ReadingView reading={reader.reading} onSeek={(s) => player.current && ((player.current.currentTime = s), player.current.play())} />}
      </div>
    </Frame>
  );
}

export default function InputPanel({ kind }: { kind: InputKind }) {
  if (kind === "text") return <TextPanel />;
  if (kind === "audio") return <AudioPanel />;
  return <VisualPanel key={kind} kind={kind} />;
}
