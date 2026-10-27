import { useEffect, useState, type CSSProperties } from "react";
import InputPanel from "../components/InputPanels";
import { MediumIcon } from "../components/EngineMenu";
import { formatNumber, useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { getJson } from "../lib/api";
import { num } from "../lib/format";
import { Link, useRouter } from "../lib/router";

// The AI engine's pages for sound, images and video: /audio, /image and /video read a file (the landing page's input
// panel, full size), and /audio/models, /image/models and /video/models say which local models do it and what each
// has been shown to do on this computer, in the four states /api/media/status keeps apart.

type Kind = "audio" | "image" | "video";
interface Component {
  name: string;
  model: string;
  files_present: boolean;
  runtime_ready: boolean;
  run_tested: boolean;
  quality_evaluated: boolean;
  // The pilot's times are per step (loading, each sample); the image model's memory is its llama-server's.
  pilot: { seconds?: Record<string, number>; peak_mb?: number; server_peak_mb?: number; checks?: number; passed_checks?: number } | null;
}

// Which readers stand behind each input (a video goes through the others).
const READERS: Record<Kind, string[]> = { audio: ["speech"], image: ["ocr", "vision"], video: ["video", "speech", "ocr", "vision"] };
// The landing page's row for the input: its title and what the challenge asks of it.
const ROW: Record<Kind, number> = { audio: 2, image: 3, video: 4 };
const STATES = [
  ["files_present", "models.files"],
  ["runtime_ready", "models.runtime"],
  ["run_tested", "models.tested"],
  ["quality_evaluated", "models.evaluated"],
] as const;
const TONE = { "--tone": "#5eead4", "--tone-rgb": "94,234,212" } as CSSProperties;

function Tabs({ kind, models }: { kind: Kind; models: boolean }) {
  const { t } = useI18n();
  const tab = (to: string, label: MessageKey, current: boolean) => (
    <Link to={to} aria-current={current ? "page" : undefined} className={`nav-glow rounded-full px-4 py-2 font-sans text-sm no-underline ${current ? "bg-beam-400/12 text-beam-300" : "text-fog-300"}`}>
      {t(label)}
    </Link>
  );
  return (
    <nav aria-label={t(`nav.${kind}`)} className="flex flex-wrap gap-1.5">
      {tab(`/${kind}`, `nav.${kind}Read`, !models)}
      {tab(`/${kind}/models`, "nav.models", models)}
    </nav>
  );
}

function Reader({ kind }: { kind: Kind }) {
  return (
    // The panel is drawn for the landing page's night, so it keeps that ground here too.
    <div className="theme-night flex h-[min(760px,calc(100dvh-230px))] min-h-[520px] flex-col rounded-[24px] border border-hair bg-ink-950 p-4 shadow-[var(--shadow-card)] sm:p-6" style={TONE}>
      <InputPanel kind={kind} />
    </div>
  );
}

function Models({ kind }: { kind: Kind }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Component[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    getJson<{ components: Component[] }>("/api/media/status").then((r) => setRows(r.components), () => setFailed(true));
  }, []);
  if (failed) return <p className="m-0 text-fog-300" role="alert">{t("models.error")}</p>;
  if (!rows) return <p className="m-0 text-fog-400">{t("app.loading")}</p>;
  const shown = READERS[kind].map((name) => rows.find((r) => r.name === name)).filter((r): r is Component => !!r);
  return (
    <div className="flex flex-col gap-5">
      <ul className="m-0 grid list-none gap-4 p-0 md:grid-cols-2">
        {shown.map((row) => (
          <li key={row.name} className="card flex flex-col gap-4 p-6">
            <div className="flex flex-col gap-1">
              <span className="font-sans text-xs font-medium uppercase tracking-[0.16em] text-beam-400">{t(`models.role.${row.name}` as MessageKey)}</span>
              <h2 className="m-0 text-xl font-medium leading-snug">
                <bdi>{row.model}</bdi>
              </h2>
              <p className="m-0 text-[15px] leading-relaxed text-fog-300">{t(`models.about.${row.name}` as MessageKey)}</p>
            </div>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {STATES.map(([key, label]) => (
                <li key={key} className="flex items-center gap-2.5 text-[15px]">
                  <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full text-[11px] font-bold ${row[key] ? "bg-ok/15 text-ok-ink" : "bg-ink-600 text-fog-400"}`} aria-hidden="true">
                    {row[key] ? "✓" : "–"}
                  </span>
                  <span className={row[key] ? "text-fog-100" : "text-fog-400"}>{t(label)}</span>
                  <span className="sr-only">{t(row[key] ? "models.yes" : "models.no")}</span>
                </li>
              ))}
            </ul>
            {row.pilot?.checks != null && (
              <p className="m-0 font-sans text-sm text-fog-400">
                {t("models.pilot", {
                  passed: formatNumber(row.pilot.passed_checks ?? 0),
                  checks: formatNumber(row.pilot.checks),
                  s: num(Object.values(row.pilot.seconds ?? {}).reduce((a, b) => a + b, 0), 1),
                  mb: formatNumber(Math.round((row.pilot.peak_mb ?? 0) + (row.pilot.server_peak_mb ?? 0))),
                })}
              </p>
            )}
          </li>
        ))}
      </ul>
      <p className="m-0 max-w-3xl text-[15px] leading-relaxed text-fog-300">{t("models.note")}</p>
    </div>
  );
}

export default function Media() {
  const { path } = useRouter();
  const { t } = useI18n();
  const kind = path.split("/")[1] as Kind;
  const models = path.replace(/\/+$/, "").endsWith("/models");
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-7 px-4 py-12 sm:px-8">
      <header className="flex max-w-3xl flex-col gap-4">
        <span className="eyebrow inline-flex items-center gap-2">
          <MediumIcon medium={kind} size={14} />
          {t(`nav.${kind}`)}
        </span>
        <Heading key={path} className="m-0 text-[clamp(30px,3.6vw,46px)] font-normal leading-tight tracking-tight">
          {models ? t("models.title") : t(`landing.in${ROW[kind]}.title` as MessageKey)}
        </Heading>
        <p className="m-0 text-lg leading-relaxed text-fog-300">{models ? t(`models.lead.${kind}`) : t(`landing.in${ROW[kind]}.sub` as MessageKey)}</p>
        <Tabs kind={kind} models={models} />
      </header>
      {models ? <Models kind={kind} /> : <Reader key={kind} kind={kind} />}
    </div>
  );
}
