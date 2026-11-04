import { Suspense, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { AdderStatus, FileButton, Library, Review, useAdder, type Adder } from "../components/Library";
import { AnswerView } from "../components/report/AnswerView";
import { Panel } from "../components/report/Panels";
import { useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { api } from "../lib/api";
import { num, VERDICT } from "../lib/format";
import { lazyPage } from "../lib/lazyPage";
import { Link, useRouter } from "../lib/router";
import type { AskTurn, Citation, RagAnswer, Task } from "../lib/types";
import { useStream } from "../lib/useStream";
import { useWorkspace } from "../lib/workspace";
import { ReportView } from "./Analyze";

// Text, sound and images in one place (D-169). Asking the documents (D-164): a question goes to the library, a model writes
// from the closest passages, looking at their images, and the Guardian checks what it wrote, so the check stays what this page
// is about: every answer carries how it was checked. A file of any kind can be added from the conversation; the library and
// the review of what was read (D-167), and checking an answer about a recording or an image (D-135), are its other tabs.

const FileCheck = lazyPage(() => import("../components/FileCheck"));
type Tab = "ask" | "library" | "audio" | "image";
const TABS: Record<Tab, MessageKey> = { ask: "ask.tab.ask", library: "ask.tab.library", audio: "nav.audioRead", image: "nav.imageRead" };
// The landing page's row for each medium: its line on what is checked.
const ROW = { audio: 2, image: 3 } as const;
const FROM_IMAGE = ["ocr", "description", "confirmed"];
type Collection = "mine" | "project";
const MAX_QUESTION = 1000;
const MAX_TURN = 5000;
const MAX_HISTORY = 20;
const TRIES = ["ask.try1", "ask.try2", "ask.try3"] as const;
// The server's own words for these; anything else it says is shown as it came.
const NOTE: Record<string, MessageKey> = { "the model cited a document it was not given; that citation was removed": "ask.citedInvented" };
const REASON: Record<string, MessageKey> = { "a number is not in the documents": "ask.reason.number", "no passage is close to this sentence": "ask.reason.far" };

function statusOf(answer: RagAnswer, t: (key: MessageKey) => string): { label: string; color: string } {
  if (answer.status === "checked" && answer.report) return VERDICT[answer.report.verdict];
  const color = { healed: "var(--color-ok)", light: "var(--color-warn)", opinion: "var(--color-weak)", unchecked: "var(--color-warn)", checked: "var(--color-weak)", not_in_documents: "var(--color-fog-400)" }[answer.status];
  return { label: t(`ask.status.${answer.status}` as MessageKey), color };
}

function Fold({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <details className="group rounded-2xl bg-ink-700/70 px-4 py-2.5 text-sm">
      <summary className="cursor-pointer text-fog-300" dir="auto">
        {summary}
      </summary>
      <div className="mt-2.5">{children}</div>
    </details>
  );
}

export function roleLabel(role: string | null, t: (key: MessageKey) => string): string | null {
  return role ? t(`ask.role.${role}` as MessageKey) : null;
}

function Source({ citation }: { citation: Citation }) {
  const { t } = useI18n();
  const place = [citation.page ? t("ask.page", { n: citation.page }) : null, citation.place && <bdi key="place">{citation.place}</bdi>, roleLabel(citation.role, t)].filter(Boolean);
  return (
    <Fold
      summary={
        <>
          {!citation.inferred && <span className="font-mono text-xs">[{citation.n}] </span>}
          <bdi className="text-fog-100">{citation.document}</bdi>
          {place.map((part, i) => (
            <span key={i} className="text-fog-400">
              {" · "}
              {part}
            </span>
          ))}
          {citation.reviewed && <span className="ms-2 rounded-full bg-ok/12 px-2 py-0.5 text-xs text-ok-ink">{t("ask.reviewed")}</span>}
        </>
      }
    >
      {citation.document_id != null && citation.role && FROM_IMAGE.includes(citation.role) && <img src={`/api/library/documents/${citation.document_id}/picture`} alt={citation.document} loading="lazy" className="mb-2 block max-h-48 max-w-full rounded-xl" />}
      <p className="m-0 whitespace-pre-wrap leading-relaxed text-fog-200" dir="auto">
        {citation.text}
      </p>
    </Fold>
  );
}

/** The light check's reading (D-164): its doubtful sentences marked, with why, and no verdict. */
function LightText({ answer }: { answer: RagAnswer }) {
  const { t } = useI18n();
  const parts: ReactNode[] = [];
  let at = 0;
  answer.light.forEach((claim, i) => {
    if (claim.start > at) parts.push(answer.text.slice(at, claim.start));
    const piece = answer.text.slice(claim.start, claim.end);
    parts.push(
      claim.status === "doubtful" ? (
        <mark key={i} className="rounded-[4px] bg-warn/20 px-0.5 text-fog-100" title={claim.reasons.map((r) => (r in REASON ? t(REASON[r]) : r)).join(t("common.comma"))}>
          {piece}
        </mark>
      ) : (
        piece
      ),
    );
    at = claim.end;
  });
  parts.push(answer.text.slice(at));
  const doubts = [...new Set(answer.light.flatMap((claim) => claim.reasons))];
  return (
    <>
      <p className="m-0 whitespace-pre-wrap text-[17px] leading-[1.9]" dir="auto">
        {parts}
      </p>
      {doubts.map((reason) => (
        <p key={reason} className="m-0 text-sm text-warn-ink">
          {reason in REASON ? t(REASON[reason]) : reason}
        </p>
      ))}
      <p className="m-0 text-[13px] leading-relaxed text-fog-400">{t("ask.lightNote")}</p>
    </>
  );
}

function AnswerCard({ turn }: { turn: AskTurn }) {
  const { t } = useI18n();
  const { answer, question } = turn;
  const [full, setFull] = useState(false);
  const status = statusOf(answer, t);
  const generator = answer.generator ? t(`ask.generator.${answer.generator}` as MessageKey) : null;
  const facts = [generator, t("common.seconds", { s: num(answer.seconds, 1) }), answer.cost_usd > 0 ? `$${num(answer.cost_usd, 3)}` : null].filter(Boolean).join(" · ");
  const words = answer.notes.filter((note) => !note.startsWith("this answer rests"));
  return (
    <Panel tone={status.color}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ background: `color-mix(in oklab, ${status.color} 16%, transparent)`, color: status.color }}>
          {status.label}
        </span>
        <span className="font-mono text-xs text-fog-400">{facts}</span>
      </div>
      {answer.status === "light" ? (
        <LightText answer={answer} />
      ) : answer.report ? (
        <AnswerView answer={answer.text} claims={answer.report.claims} />
      ) : (
        <p className="m-0 whitespace-pre-wrap text-[17px] leading-[1.9]" dir="auto">
          {answer.text}
        </p>
      )}
      {answer.status === "opinion" && <p className="m-0 text-sm text-warn-ink">{t("ask.opinionNote")}</p>}
      {answer.status === "unchecked" && <p className="m-0 text-sm text-warn-ink">{t("ask.uncheckedNote")}</p>}
      {answer.looked_at.length > 0 && answer.status !== "opinion" && <p className="m-0 text-[13px] leading-relaxed text-fog-400">{t("ask.lookedAt", { names: answer.looked_at.join(t("common.comma")) })}</p>}
      {answer.status !== "not_in_documents" && !answer.citations.length && <p className="m-0 text-sm text-warn-ink">{t("ask.noCitation")}</p>}
      {words.map((note) => (
        <p key={note} className="m-0 text-sm text-warn-ink" dir="auto">
          {note in NOTE ? t(NOTE[note]) : note}
        </p>
      ))}
      {answer.searched_for !== question && (
        <p className="m-0 text-[13px] text-fog-400" dir="auto">
          {t("ask.searchedFor", { q: answer.searched_for })}
        </p>
      )}
      {answer.citations.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="m-0 font-sans text-[13px] font-normal text-fog-400">{t(answer.citations[0].inferred ? "ask.sourcesFound" : "ask.sources")}</h3>
          {answer.citations.map((citation) => (
            <Source key={citation.n} citation={citation} />
          ))}
        </div>
      )}
      {answer.original && (
        <Fold summary={t("ask.original")}>
          <p className="m-0 whitespace-pre-wrap leading-relaxed text-fog-200" dir="auto">
            {answer.original}
          </p>
        </Fold>
      )}
      {answer.report && (
        <div className="flex flex-col gap-3">
          <button type="button" className="chip self-start" aria-pressed={full} onClick={() => setFull((v) => !v)}>
            {t("ask.fullCheck")}
          </button>
          {full && <ReportView report={answer.report} input={{ question, sources: [], answer: answer.text, task: "qa" as Task }} />}
        </div>
      )}
    </Panel>
  );
}

function Question({ text }: { text: string }) {
  return (
    <p className="m-0 max-w-[85%] self-end whitespace-pre-wrap rounded-2xl bg-beam-400/12 px-4 py-2.5 text-[15px] leading-relaxed text-fog-100" dir="auto">
      {text}
    </p>
  );
}

function Conversation({ adder }: { adder: Adder }) {
  const { t, lang } = useI18n();
  const { health, turns, setTurns } = useWorkspace();
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const [collections, setCollections] = useState<Collection[]>(["mine", "project"]);
  const [generator, setGenerator] = useState<"local" | "online">("local");
  const [available, setAvailable] = useState<{ local: boolean; online: boolean } | null>(null);
  const ask = useStream<{ answer: RagAnswer }>();
  const end = useRef<HTMLDivElement>(null);
  const ready = health?.state === "ready";

  useEffect(() => {
    api.generators().then(setAvailable, () => {});
  }, []);
  // A file just added is what the person means to ask about next.
  useEffect(() => {
    if (adder.added) setCollections((list) => (list.includes("mine") ? list : [...list, "mine"]));
  }, [adder.added]);

  const written = ask.events.flatMap((e) => (e.type === "text" ? [e.text] : [])).join("");
  const stages = ask.events.flatMap((e) => (e.type === "stage" ? [e.stage] : []));
  const stage = stages[stages.length - 1];

  useEffect(() => {
    if (asked || turns.length) end.current?.scrollIntoView({ block: "nearest" });
  }, [turns.length, asked, written.length]);

  const send = async (text: string) => {
    const value = text.trim();
    if (!value || ask.running || !ready || adder.busy) return;
    const history = turns.flatMap((turn) => [{ role: "user", content: turn.question.slice(0, MAX_TURN) }, { role: "assistant", content: turn.answer.text.slice(0, MAX_TURN) }]).slice(-MAX_HISTORY);
    setAsked(value);
    setQuestion("");
    const result = await ask.run("/api/ask", { question: value, history, collections, generator, language: lang });
    setAsked(null);
    if (result) setTurns((list) => [...list, { question: value, answer: result.answer }]);
    else setQuestion(value);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(question);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(question);
    }
  };
  const toggle = (name: Collection) => setCollections((list) => (list.includes(name) ? (list.length > 1 ? list.filter((c) => c !== name) : list) : [...list, name]));

  return (
    <div className="flex flex-col gap-4">
      {!turns.length && !asked && (
        <div className="flex flex-col gap-2.5">
          <p className="m-0 text-[15px] text-fog-300">{t("ask.empty")}</p>
          <div className="flex flex-wrap gap-2">
            {TRIES.map((key) => (
              <button key={key} type="button" className="chip" disabled={!ready} onClick={() => send(t(key))} dir="auto">
                {t(key)}
              </button>
            ))}
          </div>
        </div>
      )}
      {turns.map((turn, i) => (
        <div key={i} className="page-in flex flex-col gap-3">
          <Question text={turn.question} />
          <AnswerCard turn={turn} />
        </div>
      ))}
      {asked && (
        <div className="flex flex-col gap-3" aria-busy="true">
          <Question text={asked} />
          <Panel>
            <p className="m-0 flex items-center gap-2.5 text-sm text-fog-300" aria-live="polite">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-beam-400" aria-hidden="true" />
              {stage ? t(`ask.stage.${stage}` as MessageKey) : t("app.loading")}
            </p>
            {written && (
              <p className="m-0 whitespace-pre-wrap text-[17px] leading-[1.9] text-fog-300" dir="auto">
                {written}
              </p>
            )}
          </Panel>
        </div>
      )}
      {ask.error && (
        <div role="alert" className="rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
          {t("ask.failed", { error: ask.error })}
        </div>
      )}
      <div ref={end} />
      <form onSubmit={submit} className="card flex flex-col gap-3 p-4">
        <label className="sr-only" htmlFor="ask-question">
          {t("ask.placeholder")}
        </label>
        <textarea id="ask-question" className="field min-h-[76px] resize-y" dir="auto" maxLength={MAX_QUESTION} placeholder={t("ask.placeholder")} value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={onKey} />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("ask.searchIn")}>
              <span className="label">{t("ask.searchIn")}</span>
              {(["mine", "project"] as const).map((name) => (
                <button key={name} type="button" className="chip" aria-pressed={collections.includes(name)} onClick={() => toggle(name)}>
                  {t(`ask.in.${name}`)}
                </button>
              ))}
            </div>
            {available && (
              <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={t("ask.generator")}>
                <span className="label">{t("ask.generator")}</span>
                {(["local", "online"] as const).map((name) => (
                  <button key={name} type="button" className="chip disabled:opacity-50" aria-pressed={generator === name} disabled={!available[name]} title={!available[name] ? t(`ask.unavailable.${name}`) : undefined} onClick={() => setGenerator(name)}>
                    {t(`ask.generator.${name}`)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {turns.length > 0 && (
              <button type="button" className="btn btn-ghost" disabled={ask.running} onClick={() => setTurns(() => [])}>
                {t("ask.clear")}
              </button>
            )}
            <FileButton adder={adder} className="btn btn-ghost" label={t("ask.attach")} />
            <button type="submit" className="btn btn-primary" disabled={ask.running || !ready || adder.busy || !question.trim()}>
              {ready ? t("ask.send") : t("common.loadingModels")}
            </button>
          </div>
        </div>
        {generator === "online" && <p className="m-0 text-[13px] text-warn-ink">{t("ask.onlineNote")}</p>}
      </form>
    </div>
  );
}

function MediaTab({ kind, shown }: { kind: "audio" | "image"; shown: boolean }) {
  const { t } = useI18n();
  return (
    <div hidden={!shown} className="flex flex-col gap-4">
      <p className="m-0 max-w-3xl text-[15px] leading-relaxed text-fog-300">
        {t(`landing.in${ROW[kind]}.sub` as MessageKey)}{" "}
        <Link to={`/${kind}/models`} className="whitespace-nowrap">
          {t("nav.models")}
        </Link>
      </p>
      <Suspense fallback={<p className="m-0 text-fog-400">{t("app.loading")}</p>}>
        <FileCheck kind={kind} />
      </Suspense>
    </div>
  );
}

export default function Ask() {
  const { t } = useI18n();
  const { path } = useRouter();
  const start = path.split("/")[1] as Tab;
  const [tab, setTab] = useState<Tab>(start in TABS ? start : "ask");
  // A panel for checking a file loads when first opened, and stays so what was read in it is not lost.
  const [opened, setOpened] = useState<Set<Tab>>(() => new Set([start]));
  const adder = useAdder();
  const open = (name: Tab) => {
    setTab(name);
    setOpened((seen) => new Set(seen).add(name));
  };
  return (
    <div className="page-in mx-auto flex max-w-[1100px] flex-col gap-6 px-4 py-10 sm:px-8">
      <header className="flex max-w-3xl flex-col gap-3">
        <Heading className="m-0 text-[clamp(28px,3.4vw,42px)] font-normal leading-tight tracking-tight">{t("ask.title")}</Heading>
        <p className="m-0 text-[17px] leading-relaxed text-fog-300">{t("ask.lead")}</p>
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(TABS) as Tab[]).map((name) => (
            <button key={name} type="button" className={`nav-glow rounded-full px-4 py-2 font-sans text-sm ${tab === name ? "bg-beam-400/12 text-beam-300" : "text-fog-300"}`} aria-pressed={tab === name} onClick={() => open(name)}>
              {t(TABS[name])}
            </button>
          ))}
        </div>
      </header>
      {(tab === "ask" || tab === "library") && (
        <>
          <AdderStatus adder={adder} />
          {adder.draft && <Review key={adder.draft.draft.draft} adder={adder} />}
        </>
      )}
      {/* All stay mounted, so going to another tab does not lose the conversation or a review under way. */}
      <div hidden={tab !== "ask"}>
        <Conversation adder={adder} />
      </div>
      <div hidden={tab !== "library"}>
        <Library adder={adder} />
      </div>
      {opened.has("audio") && <MediaTab kind="audio" shown={tab === "audio"} />}
      {opened.has("image") && <MediaTab kind="image" shown={tab === "image"} />}
    </div>
  );
}
