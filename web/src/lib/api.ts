import type { CheckInput, Example, ExampleBrief, FoolAnswer, Health, Report } from "./types";

export class ApiError extends Error {}

export type StreamEvent =
  | { type: "stage"; stage: string; t: number }
  | { type: "check"; round: number; t: number }
  | { type: "progress"; done: number; total: number; t: number }
  | { type: "queued" }
  | { type: "error"; message: string }
  | ({ type: "result" } & Record<string, unknown>);

async function detail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
  } catch {
    /* not JSON */
  }
  return `the server answered ${response.status}`;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new ApiError(await detail(response));
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new ApiError(await detail(response));
  return response.json() as Promise<T>;
}

/** POST and read the newline-delimited JSON events; resolves with the final result event. */
export async function stream<T>(path: string, body: unknown, onEvent: (event: StreamEvent) => void, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!response.ok || !response.body) throw new ApiError(await detail(response));
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
  return {
    question: input.question.trim() || null,
    sources: input.sources.map((s) => s.trim()).filter(Boolean),
    answer: input.answer,
    task: input.task,
    profile: input.profile || null,
  };
}

export const api = {
  health: () => getJson<Health>("/api/health"),
  examples: () => getJson<{ answers: ExampleBrief[]; agents: ExampleBrief[] }>("/api/examples"),
  example: (id: string) => getJson<{ example: Example; report: Report | null }>(`/api/examples/${encodeURIComponent(id)}`),
  foolAnswers: () => getJson<FoolAnswer[]>("/api/fool/answers"),
  foolEdit: (answerId: string, kind: string, seed: number) =>
    postJson<{ answer: string; edit: { start: number; end: number; new: string; original: string } }>("/api/fool/edit", { answer_id: answerId, kind, seed }),
  auditSample: () => getJson<{ jsonl: string; answers: number }>("/api/audit/sample"),
  modelCard: () => getJson<ModelCard>("/api/model-card"),
};

export interface ModelCard {
  sources: Record<string, string>;
  ragtruth_dev?: {
    answers: number;
    hallucinated_share: number;
    auroc: number;
    auroc_ci95: [number, number] | null;
    f1: number;
    f1_flag_everything: number;
    precision: number;
    recall: number;
    ece: number;
    span_f1: number;
    by_task: Record<string, { n: number; auroc: number }>;
  };
  baselines: Record<string, { auroc: number; span_f1: number }>;
  halueval?: { qa: number; dialogue: number; summary: number; answers_per_task: number };
  train?: { answers: number; out_of_fold_auroc: number };
  fool_the_guardian?: { controls_flagged: number; edits: Record<string, { n: number; detected: number; auroc: number; located: number; cautioned: number | null }> };
  guarantee?: { alpha: number; splits: number; miss_rate: number; false_alarm_rate: number };
  triage?: Record<string, number>;
  healing?: { hallucinated: Record<string, number | null>; grounded: Record<string, number | null> };
  tracer_tg_agent?: { trajectories: number; detection_auroc: number; tracer_exact: number; tracer_within_1: number; baseline_random: number };
  tracer_agenthallu?: { trajectories: number; detection_auroc: number; exact: number; random: number };
  guardian?: Record<string, { stop_tpr: number; stop_fpr: number; stop_on_responsible_step: number }>;
  speed?: { answers: number; cold_start_seconds: number; mean: number; p95: number };
  locked_test: { auroc: number; f1: number; span_f1: number } | null;
  engine: Health;
}
