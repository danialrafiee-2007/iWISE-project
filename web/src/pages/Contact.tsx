import { useEffect, useId, useState } from "react";
import { useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { ApiError, getJson, postJson } from "../lib/api";

// Contact: a message to the team's mailbox, sent by this app's own server (contact.py). The only part of the app that
// uses the internet, and only when a message is sent; the page says when sending is not set up on this computer.

const LIMITS = { name: 100, email: 254, subject: 150, message: 5000 };

type Status = { kind: "idle" | "sending" | "sent" } | { kind: "error"; message: MessageKey; detail?: string };

const failure = (e: unknown): Status => {
  const status = e instanceof ApiError ? e.status : 0;
  if (status === 503) return { kind: "error", message: "contact.notSetUp" };
  if (status === 429) return { kind: "error", message: "contact.tooMany" };
  if (status === 502 || status === 504) return { kind: "error", message: "contact.unreachable" };
  if (status === 422) return { kind: "error", message: "contact.invalid" };
  return { kind: "error", message: "contact.failed", detail: e instanceof Error ? e.message : String(e) };
};

export default function Contact() {
  const { lang, t } = useI18n();
  const id = useId();
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [configured, setConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    getJson<{ configured: boolean }>("/api/contact")
      .then((r) => setConfigured(r.configured))
      .catch(() => setConfigured(null));
  }, []);

  const edit = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm({ ...form, [key]: e.target.value });
    if (status.kind !== "sending") setStatus({ kind: "idle" });
  };
  const ready = form.name.trim() && form.email.trim() && form.subject.trim() && form.message.trim();

  const send = async () => {
    setStatus({ kind: "sending" });
    try {
      await postJson("/api/contact", { ...form, lang });
      setStatus({ kind: "sent" });
      setForm({ name: "", email: "", subject: "", message: "" });
    } catch (e) {
      setStatus(failure(e));
    }
  };

  return (
    <div className="mx-auto flex max-w-[760px] flex-col gap-8 px-4 py-14 sm:px-8">
      <header className="flex flex-col gap-4">
        <span className="eyebrow">{t("landing.badge")}</span>
        <Heading className="m-0 text-[clamp(34px,4vw,52px)] font-normal leading-tight tracking-tight">{t("contact.title")}</Heading>
        <p className="m-0 text-lg leading-relaxed text-fog-300">{t("contact.lead")}</p>
      </header>

      {configured === false && (
        <p role="note" className="m-0 rounded-2xl border border-warn/30 bg-warn/10 px-5 py-4 text-sm text-warn-ink">
          {t("contact.notSetUp")}
        </p>
      )}

      <form
        className="card flex flex-col gap-4 p-6 sm:p-8"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready && status.kind !== "sending") send();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-name`} className="label">
              {t("contact.name")}
            </label>
            <input id={`${id}-name`} className="field" dir="auto" autoComplete="name" required maxLength={LIMITS.name} value={form.name} onChange={edit("name")} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-email`} className="label">
              {t("contact.email")}
            </label>
            <input id={`${id}-email`} className="field" dir="ltr" type="email" autoComplete="email" required maxLength={LIMITS.email} value={form.email} onChange={edit("email")} />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-subject`} className="label">
            {t("contact.subject")}
          </label>
          <input id={`${id}-subject`} className="field" dir="auto" required maxLength={LIMITS.subject} value={form.subject} onChange={edit("subject")} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-message`} className="label">
            {t("contact.message")}
          </label>
          <textarea id={`${id}-message`} className="field min-h-[180px] resize-y" dir="auto" rows={7} required maxLength={LIMITS.message} value={form.message} onChange={edit("message")} />
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <button type="submit" className="btn btn-primary" disabled={!ready || status.kind === "sending" || configured === false}>
            {status.kind === "sending" ? t("contact.sending") : t("contact.send")}
          </button>
          <span className="text-xs text-fog-400">{t("contact.privacy")}</span>
        </div>
        <div aria-live="polite">
          {status.kind === "sent" && <p className="m-0 rounded-2xl border border-ok/30 bg-ok/10 px-5 py-4 text-sm text-ok-ink">{t("contact.sent")}</p>}
          {status.kind === "error" && (
            <p role="alert" className="m-0 rounded-2xl border border-bad/30 bg-bad/10 px-5 py-4 text-sm text-bad-ink">
              {t(status.message, { error: status.detail ?? "" })}
            </p>
          )}
        </div>
      </form>
    </div>
  );
}
