import { useCallback, useEffect, useId, useRef, useState } from "react";
import { formatNumber, languageName, useI18n, type MessageKey } from "../i18n";
import { api } from "../lib/api";
import type { Draft, ReadPart, Shelf, ShelfEntry } from "../lib/types";
import { useStream } from "../lib/useStream";
import { toBase64 } from "./InputForm";
import { MediumIcon } from "./EngineMenu";
import { Panel } from "./report/Panels";

// The document library's parts: what is on the shelf, and adding to it. A document goes straight in. A recording or an image
// is read first and shown for review, with the file beside it to listen to or look at, since extracted text carries the
// reader's mistakes; nothing goes in until the person says so (D-167). A file can be added from the conversation or from the
// library's tab, so the state lives in useAdder, on the page that holds both.

type Kept = { text: string; keep: boolean; confirmed: boolean };
const suffix = (name: string) => (name.includes(".") ? `.${name.split(".").pop()!.toLowerCase()}` : "");
const megabytes = (bytes: number) => Math.round(bytes / 1_000_000);

export function useAdder() {
  const { t } = useI18n();
  const [shelf, setShelf] = useState<Shelf | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [describe, setDescribe] = useState(true);
  const [draft, setDraft] = useState<{ draft: Draft; file: File } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [added, setAdded] = useState(0);
  const reading = useStream<Draft>();
  const adding = useStream<{ document: ShelfEntry }>();

  const load = useCallback(() => {
    api.library().then((found) => {
      setShelf(found);
      setFailed(null);
    }, (e: Error) => setFailed(e.message));
  }, []);
  useEffect(load, [load]);

  const landed = (text: string) => {
    setMessage(text);
    setAdded((n) => n + 1);
    load();
  };

  const choose = async (file: File) => {
    setMessage(null);
    if (!shelf) return;
    const media = shelf.media_types.includes(suffix(file.name));
    if (!media && !shelf.types.includes(suffix(file.name))) return setMessage(t("library.unsupported"));
    const limit = media ? shelf.max_media_bytes : shelf.max_bytes;
    if (file.size > limit) return setMessage(t("library.tooLarge", { mb: formatNumber(megabytes(limit)) }));
    const data = await toBase64(file);
    if (media) {
      const found = await reading.run("/api/library/read", { name: file.name, data, describe });
      if (found) setDraft({ draft: found, file });
      return;
    }
    const done = await adding.run("/api/library/documents", { name: file.name, data });
    if (done) landed(t("library.added", { name: done.document.name }));
  };

  const finish = async (parts: { index: number; text: string; confirmed: boolean }[]) => {
    if (!draft) return;
    const done = await adding.run("/api/library/reviewed", { draft: draft.draft.draft, parts });
    if (done) {
      setDraft(null);
      landed(t("library.addedReviewed", { name: done.document.name }));
    }
  };

  const progress = adding.events.flatMap((e) => (e.type === "stage" ? [e as unknown as { done?: number; total?: number }] : [])).pop();
  return { shelf, failed, load, describe, setDescribe, draft, discard: () => setDraft(null), choose, finish, message, added, reading, adding, progress, busy: reading.running || adding.running };
}

export type Adder = ReturnType<typeof useAdder>;

/** A button that opens the file chooser; the label is the visible control and the input stays out of sight. */
export function FileButton({ adder, className, label }: { adder: Adder; className: string; label: string }) {
  const id = useId();
  const off = adder.busy || !adder.shelf;
  return (
    <>
      <label htmlFor={id} className={`${className} cursor-pointer ${off ? "pointer-events-none opacity-50" : ""}`}>
        {label}
      </label>
      <input
        id={id}
        type="file"
        className="sr-only"
        disabled={off}
        accept={adder.shelf ? [...adder.shelf.types, ...adder.shelf.media_types].join(",") : undefined}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) adder.choose(file);
        }}
      />
    </>
  );
}

/** What adding a file is doing now, and how it ended: one line, whichever tab it was started from. */
export function AdderStatus({ adder }: { adder: Adder }) {
  const { t } = useI18n();
  const { reading, adding, progress, message } = adder;
  const busy = reading.running ? t("library.reading") : adding.running ? (progress?.total ? t("library.embedding", { done: formatNumber(progress.done ?? 0), total: formatNumber(progress.total) }) : t("library.adding")) : null;
  const error = reading.error ?? (adder.draft ? null : adding.error);
  if (!busy && !error && !message) return null;
  return (
    <div className="flex flex-col gap-1 text-sm">
      {busy && (
        <p className="m-0 flex items-center gap-2.5 text-fog-300" aria-live="polite">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-beam-400" aria-hidden="true" />
          {busy}
        </p>
      )}
      {!busy && error && <p className="m-0 text-bad-ink" role="alert" dir="auto">{error}</p>}
      {!busy && !error && message && <p className="m-0 text-ok-ink" role="status">{message}</p>}
    </div>
  );
}

function Passages({ id }: { id: number }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof api.passages>>["passages"] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    api.passages(id).then((r) => setRows(r.passages), (e: Error) => setFailed(e.message));
  }, [id]);
  if (failed) return <p className="m-0 text-sm text-bad-ink" role="alert">{failed}</p>;
  if (!rows) return <p className="m-0 text-sm text-fog-400">{t("app.loading")}</p>;
  return (
    <ol className="m-0 flex max-h-96 list-none flex-col gap-2 overflow-y-auto p-0">
      {rows.map((row, i) => (
        <li key={i} className="flex flex-col gap-1 rounded-xl bg-ink-700/70 px-3 py-2 text-sm leading-relaxed text-fog-200">
          {(row.place || row.page || row.role) && (
            <span className="text-xs text-fog-400">
              {[row.page ? t("ask.page", { n: row.page }) : null, row.place, row.role ? t(`ask.role.${row.role}` as MessageKey) : null].filter(Boolean).join(" · ")}
            </span>
          )}
          <span className="whitespace-pre-wrap" dir="auto">{row.text}</span>
        </li>
      ))}
    </ol>
  );
}

function Row({ entry, onRemoved }: { entry: ShelfEntry; onRemoved: () => void }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [sure, setSure] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const remove = () => {
    if (!sure) return setSure(true);
    api.removeDocument(entry.id).then(onRemoved, (e: Error) => setFailed(e.message));
  };
  return (
    <li className="flex flex-col gap-2 border-b border-hair py-3 last:border-b-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
          <span className="text-fog-400">
            <MediumIcon medium={entry.kind === "audio" ? "audio" : entry.kind === "image" ? "image" : "text"} />
          </span>
          <bdi className="min-w-0 break-all text-[15px] text-fog-100">{entry.name}</bdi>
          <span className="font-mono text-xs text-fog-400">
            {entry.language ? `${languageName(entry.language)} · ` : ""}
            {t("library.passages", { n: formatNumber(entry.passages) })}
          </span>
          {entry.reviewed_at ? (
            <span className="rounded-full bg-ok/12 px-2 py-0.5 text-xs text-ok-ink">{t("ask.reviewed")}</span>
          ) : entry.reader ? (
            <span className="rounded-full bg-warn/15 px-2 py-0.5 text-xs text-warn-ink">{t("library.notReviewed")}</span>
          ) : null}
        </div>
        <div className="flex gap-1.5">
          <button type="button" className="chip" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {t(open ? "library.hide" : "library.show")}
          </button>
          {entry.collection === "mine" && (
            <button type="button" className="chip" onClick={remove} onBlur={() => setSure(false)}>
              {t(sure ? "library.removeSure" : "library.remove")}
            </button>
          )}
        </div>
      </div>
      {entry.concerns && (
        <p className="m-0 text-[13px] text-warn-ink" dir="auto">
          {t("library.doubts", { list: entry.concerns.split("\n").join(t("common.comma")) })}
        </p>
      )}
      {failed && <p className="m-0 text-sm text-bad-ink" role="alert">{failed}</p>}
      {open && <Passages id={entry.id} />}
    </li>
  );
}

export function Review({ adder }: { adder: Adder }) {
  const { t } = useI18n();
  const { draft, file } = adder.draft!;
  const [kept, setKept] = useState<Kept[]>(() => draft.parts.map((part) => ({ text: part.text, keep: true, confirmed: false })));
  const [url, setUrl] = useState<string | null>(null);
  const [shown, setShown] = useState<number | null>(null);
  const [size, setSize] = useState<[number, number] | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    const made = URL.createObjectURL(file);
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [file]);
  const change = (i: number, values: Partial<Kept>) => setKept((list) => list.map((row, k) => (k === i ? { ...row, ...values } : row)));
  const play = (part: ReadPart) => {
    if (!audio.current || part.start == null) return;
    audio.current.currentTime = part.start;
    audio.current.play().catch(() => {});
  };
  const box = shown != null && size ? draft.parts[shown]?.box : null;
  const add = () => adder.finish(draft.parts.flatMap((part, i) => (kept[i].keep && kept[i].text.trim() ? [{ index: part.index, text: kept[i].text, confirmed: kept[i].confirmed }] : [])));
  const nothing = !draft.parts.some((_, i) => kept[i].keep && kept[i].text.trim());
  return (
    <Panel title={t("review.title")} tone="var(--color-beam-400)">
      <p className="m-0 text-[15px] leading-relaxed text-fog-300">{t("review.lead")}</p>
      <p className="m-0 font-mono text-xs text-fog-400">
        <bdi>{draft.name}</bdi>
        {" · "}
        <bdi>{draft.reader}</bdi>
        {draft.language ? ` · ${languageName(draft.language)}` : ""}
      </p>
      {draft.concerns.map((concern) => (
        <p key={concern} className="m-0 text-sm text-warn-ink" dir="auto">
          {concern}
        </p>
      ))}
      {url && draft.kind === "audio" && <audio ref={audio} controls src={url} className="w-full" />}
      {url && draft.kind === "image" && (
        <div className="relative self-start" dir="ltr">
          <img src={url} alt={draft.name} className="block max-h-80 max-w-full rounded-xl" onLoad={(e) => setSize([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])} />
          {box && size && (
            <span
              className="pointer-events-none absolute rounded-sm border-2 border-beam-400"
              aria-hidden="true"
              style={{ left: `${(box[0] / size[0]) * 100}%`, top: `${(box[1] / size[1]) * 100}%`, width: `${(box[2] / size[0]) * 100}%`, height: `${(box[3] / size[1]) * 100}%` }}
            />
          )}
        </div>
      )}
      {!draft.parts.length && <p className="m-0 text-sm text-warn-ink">{t("review.nothing")}</p>}
      <ol className="m-0 flex list-none flex-col gap-3 p-0">
        {draft.parts.map((part, i) => (
          <li key={part.index} className={`flex flex-col gap-2 rounded-2xl bg-ink-700/70 px-4 py-3 ${kept[i].keep ? "" : "opacity-55"}`} onMouseEnter={() => setShown(i)} onFocus={() => setShown(i)}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="flex flex-wrap items-center gap-2 text-xs text-fog-400">
                {t(`ask.role.${part.role}` as MessageKey)}
                {part.place && <bdi className="font-mono">{part.place}</bdi>}
                {part.doubtful && <span className="rounded-full bg-warn/15 px-2 py-0.5 text-warn-ink">{t("review.doubtful")}</span>}
              </span>
              <span className="flex flex-wrap items-center gap-1.5">
                {part.start != null && draft.kind === "audio" && (
                  <button type="button" className="chip" onClick={() => play(part)}>
                    {t("review.play")}
                  </button>
                )}
                <label className="chip cursor-pointer gap-1.5">
                  <input type="checkbox" checked={kept[i].keep} onChange={(e) => change(i, { keep: e.target.checked })} />
                  {t("review.keep")}
                </label>
              </span>
            </div>
            <textarea className="field min-h-[64px] resize-y text-[15px]" dir="auto" aria-label={t(`ask.role.${part.role}` as MessageKey)} disabled={!kept[i].keep} value={kept[i].text} onChange={(e) => change(i, { text: e.target.value })} />
            {part.opinion && kept[i].keep && (
              <div className="flex flex-col gap-1.5">
                <p className="m-0 text-[13px] leading-relaxed text-warn-ink">{t("review.opinion")}</p>
                <label className="flex items-center gap-2 text-sm text-fog-200">
                  <input type="checkbox" checked={kept[i].confirmed} onChange={(e) => change(i, { confirmed: e.target.checked })} />
                  {t("review.confirm")}
                </label>
              </div>
            )}
          </li>
        ))}
      </ol>
      {adder.adding.error && <p className="m-0 text-sm text-bad-ink" role="alert" dir="auto">{adder.adding.error}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-ghost" disabled={adder.adding.running} onClick={adder.discard}>
          {t("review.discard")}
        </button>
        <button type="button" className="btn btn-primary" disabled={adder.adding.running || nothing} onClick={add}>
          {adder.adding.running ? t("library.adding") : t("review.add")}
        </button>
      </div>
    </Panel>
  );
}

export function Library({ adder }: { adder: Adder }) {
  const { t } = useI18n();
  const { shelf, failed } = adder;
  const mine = shelf?.documents.filter((d) => d.collection === "mine") ?? [];
  const project = shelf?.documents.filter((d) => d.collection === "project") ?? [];

  if (failed && !shelf) {
    return (
      <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
        {t("library.unavailable", { error: failed })}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-5">
      <Panel title={t("library.add")}>
        <p className="m-0 text-[15px] leading-relaxed text-fog-300">{t("library.lead")}</p>
        <div className="flex flex-wrap items-center gap-3">
          <FileButton adder={adder} className="btn btn-primary" label={t("library.choose")} />
          <label className="flex items-center gap-2 text-sm text-fog-300">
            <input type="checkbox" checked={adder.describe} onChange={(e) => adder.setDescribe(e.target.checked)} />
            {t("library.describe")}
          </label>
        </div>
        {shelf && <p className="m-0 text-[13px] text-fog-400">{t("library.types", { doc: formatNumber(megabytes(shelf.max_bytes)), media: formatNumber(megabytes(shelf.max_media_bytes)) })}</p>}
      </Panel>
      <Panel title={t("ask.in.mine")}>
        {mine.length ? (
          <ul className="m-0 list-none p-0">
            {mine.map((entry) => (
              <Row key={entry.id} entry={entry} onRemoved={adder.load} />
            ))}
          </ul>
        ) : (
          <p className="m-0 text-[15px] text-fog-400">{shelf ? t("library.empty") : t("app.loading")}</p>
        )}
      </Panel>
      {project.length > 0 && (
        <Panel title={t("ask.in.project")}>
          <ul className="m-0 list-none p-0">
            {project.map((entry) => (
              <Row key={entry.id} entry={entry} onRemoved={adder.load} />
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
