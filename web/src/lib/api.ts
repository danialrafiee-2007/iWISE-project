import { languageName, t } from "../i18n";
import type { CheckInput, Example, ExampleBrief, FoolAnswer, Health, Report, RunStep, Shelf } from "./types";

export class ApiError extends Error {
  /** The HTTP status, when the server answered (0 otherwise). */
  constructor(message: string, readonly status = 0) {
    super(message);
  }
}

export type StreamEvent =
  | { type: "stage"; stage: string; t: number }
  | { type: "check"; round: number; t: number }
  | { type: "queued" }
  | { type: "text"; text: string }
  | { type: "step"; step: RunStep }
  | { type: "error"; message: string }
  | ({ type: "result" } & Record<string, unknown>);

/** The server's refusal of an answer no check reads (engine.NotChecked), said in the interface's language. */
function notChecked(detail: { code: string; language: string | null; sources: (string | null)[] }): string {
  if (detail.code === "not_installed") return t("check.notInstalled");
  if (detail.code === "unknown_language") return t("check.unknownLanguage");
  const checked = ["en", "ar", "es", "fr", "ru", "zh"];
  const outside = [detail.language, ...detail.sources].find((code) => code && !checked.includes(code)) ?? detail.language;
  return t("check.notChecked", { language: outside ? languageName(outside) : "?" });
}

async function detail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (body.detail && typeof body.detail.code === "string") return notChecked(body.detail);
    if (Array.isArray(body.detail)) return body.detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
  } catch {
    /* not JSON */
  }
  return `the server answered ${response.status}`;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new ApiError(await detail(response), response.status);
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new ApiError(await detail(response), response.status);
  return response.json() as Promise<T>;
}

/** POST and read the newline-delimited JSON events; resolves with the final result event. */
export async function stream<T>(path: string, body: unknown, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!response.ok || !response.body) throw new ApiError(await detail(response), response.status);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    let newline: number;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      const event = JSON.parse(line) as StreamEvent;
      if (event.type === "error") throw new ApiError(event.message);
      if (event.type === "result") return event as unknown as T;
      onEvent(event);
    }
    if (done) throw new ApiError("the connection closed before the result arrived");
  }
}

export function checkBody(input: CheckInput) {
  if (input.exampleId) return { example_id: input.exampleId };
  const kept = input.sources.map((s, i) => ({ text: s.trim(), name: input.sourceNames?.[i]?.split(" · part ")[0] ?? null })).filter((s) => s.text);
  return {
    question: input.question.trim() || null,
    sources: kept.map((s) => s.text),
    source_names: kept.map((s) => s.name),
    answer: input.answer,
    task: input.task,
    profile: input.profile || null,
    ...(input.language ? { language: input.language } : {}),
  };
}

export const api = {
  health: () => getJson<Health>("/api/health"),
  examples: () => getJson<{ answers: ExampleBrief[]; agents: ExampleBrief[] }>("/api/examples"),
  example: (id: string) => getJson<{ example: Example; report: Report | null }>(`/api/examples/${encodeURIComponent(id)}`),
  foolAnswers: () => getJson<FoolAnswer[]>("/api/fool/answers"),
  foolEdit: (answerId: string, kind: string, seed: number) =>
    postJson<{ answer: string; edit: { start: number; end: number; new: string; original: string } }>("/api/fool/edit", { answer_id: answerId, kind, seed }),
  modelCard: () => getJson<ModelCard>("/api/model-card"),
  generators: () => getJson<{ local: boolean; online: boolean }>("/api/ask/generators"),
  library: () => getJson<Shelf>("/api/library"),
  passages: (id: number) => getJson<{ passages: { text: string; page: number | null; place: string | null; role: string | null }[] }>(`/api/library/documents/${id}/passages`),
  removeDocument: async (id: number) => {
    const response = await fetch(`/api/library/documents/${id}`, { method: "DELETE" });
    if (!response.ok) throw new ApiError(await detail(response), response.status);
  },
};

export interface Summary {
  answers: number;
  hallucinated_share: number;
  auroc: number;
  auroc_ci95: [number, number] | null;
  f1: number;
  f1_flag_everything: number;
  precision: number;
  recall: number;
  ece: number | null;
  span_f1: number | null;
  by_task: Record<string, { n: number; auroc: number }>;
}

export type LockedAuroc = Partial<Record<"ragtruth" | "qa" | "dialogue" | "summary" | "ragtruth_span_f1", number>>;

export type Before = { model: number; profile: number };

export interface CalibrationBin {
  low: number;
  high: number;
  n: number;
  mean_risk: number;
  observed: number;
}

export interface ChallengeCases {
  samples: number;
  auroc_answers_vs_faithful: number;
  cases: {
    mixed: { n: number; caught: number; wrong_part_found: number; correct_parts_kept: number; auroc_vs_faithful: number };
    partial: {
      n: number;
      omission: { n: number; left_out_reported: number; flagged: number };
      caveat: { n: number; caught: number; noticed: number; auroc_vs_faithful: number };
    };
    unsupported: { n: number; caught: number; claim_found: number; called_unsupported: number; auroc_vs_faithful: number };
    weak: { n: number; caught: number; retrieval_blamed: number; auroc_vs_honest: number };
    agent: { n: number; caught: number; guardian_stopped: number; exact_step: number; auroc_answer_risk_vs_faithful: number; by_kind: Record<string, { n: number; caught: number; exact_step: number }> };
  };
  controls: {
    faithful: { n: number; flagged: number; completeness_reported_missing: number };
    honest_over_weak_sources: { n: number; flagged: number };
    faithful_agents: { n: number; flagged: number; guardian_stopped: number };
  };
}

export interface ModelCard {
  ragtruth_dev?: Summary & { fusion_only_auroc?: number | null };
  baselines: Record<string, { auroc: number; span_f1: number }>;
  halueval?: { qa: number; dialogue: number; summary: number; answers_per_task: number };
  train?: { answers: number; out_of_fold_auroc: number };
  fool_the_guardian?: { controls_flagged: number; edits: Record<string, { n: number; detected: number; auroc: number; located: number; cautioned: number | null }> };
  guarantee?: { alpha: number; splits: number; miss_rate: number; false_alarm_rate: number };
  challenge_cases?: ChallengeCases;
  calibration?: Record<string, { answers: number; ece: number; bins: CalibrationBin[] }>;
  profiles?: {
    labelled: number;
    domains: Record<string, { held_out_answers: number; auroc: Before; ece: Before; verdict_accuracy: Before }>;
    length_alone_auroc?: Record<string, number>;
  };
  triage?: Record<string, number>;
  healing?: { hallucinated: Record<string, number | null>; grounded: Record<string, number | null> };
  tracer_tg_agent?: { trajectories: number; detection_auroc: number; tracer_exact: number; tracer_within_1: number; baseline_random: number };
  tracer_agenthallu?: { trajectories: number; detection_auroc: number; exact: number; random: number };
  guardian?: Record<string, { stop_tpr: number; stop_fpr: number; stop_on_responsible_step: number }>;
  speed?: { answers: number; cold_start_seconds: number; mean: number; p95: number };
  locked_test: Summary | null;
  locked_halueval?: Record<string, Summary> | null;
  locked_baselines?: Record<string, LockedAuroc>;
  locked_reference?: LockedAuroc | null;
  locked_agenthallu?: { trajectories: number; detection_auroc: number; exact: number; random: number };
  engine: Health;
}
