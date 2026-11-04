export type Status = "supported" | "contradicted" | "unsupported" | "insufficient_evidence" | "contested";
export type Verdict = "grounded" | "hallucinated" | "uncertain";
export type Lane = "pass" | "review" | "block";
export type Grade = "A" | "B" | "C" | "D" | "F";
export type Blame = "retrieval" | "generation" | "weak_sources" | "conflicting_sources" | "none" | "unknown";
export type Task = "qa" | "summary" | "data2text" | "other";

export interface Fix {
  start: number;
  end: number;
  original: string;
  replacement: string | null;
  confidence: number;
}

export interface Claim {
  start: number;
  end: number;
  text: string;
  status: Status;
  risk: number;
  type: string | null;
  spans: [number, number][];
  focus: [number, number][];
  evidence: { text: string; document_id: string | null } | null;
  explanation: string;
  action: "keep" | "replace" | "remove" | "verify";
  fixes: Fix[];
  cautions: string[];
  citation: { cited: number[]; supported: boolean; better_document: number | null } | null;
  contribution: number | null;
}

export interface AgentStepReport {
  step: number;
  kind: string;
  role: string | null;
  suspicion: number;
  reason: string;
  unsupported: string[];
  tool_error: boolean;
}

export interface AgentAlert {
  step: number;
  level: "warning" | "stop";
  reason: string;
}

export interface Report {
  id: string;
  verdict: Verdict;
  risk: number;
  response_threshold: number;
  sentence_threshold: number;
  claims: Claim[];
  agent: { risk: number; suspected_step: number | null; steps: AgentStepReport[]; alerts: AgentAlert[]; guardian_stop: number | null } | null;
  diagnosis: { blame: Blame; message: string; relevance: number | null; question_similarity: number | null; question_coverage: number | null } | null;
  completeness: { score: number | null; key_evidence: string[]; missing: string[]; omitted_caveats: string[] } | null;
  conflicts: { first: string; first_document: string; second: string; second_document: string; first_value: string; second_value: string }[];
  guarantee: { alpha: number; catch_threshold: number; alarm_threshold: number; flagged_with_catch_guarantee: boolean; flagged_with_alarm_guarantee: boolean; calibrated_on: string } | null;
  domain: { name: string; examples: number; calibrated_risk: number; model_risk?: number | null; decision?: number | null } | null;
  triage: { lane: Lane; reason: string } | null;
  card: { grade: Grade; risk: number; dimensions: { name: string; score: number | null; note: string }[] } | null;
  cited_answer: string | null;
  warnings: string[];
  model_version: string | null;
  /** Which check read the answer, and the languages told (language.py); absent in reports cached before D-138. */
  language?: { check: "english" | "multilingual"; answer: string | null; sources: (string | null)[]; guessed: boolean; measured: boolean } | null;
  /** The experimental online check (D-141): Claude's second opinion on the doubtful claims, beside the local verdict. */
  online?: Online | null;
}

export interface Online {
  status: "checked" | "budget" | "error" | "refused";
  model: string | null;
  claims: { start: number; end: number; text: string; in_sources: "supported" | "contradicted" | "not_found"; on_web: "true" | "false" | "unclear" | "not_searched"; explanation: string; correction: string | null; sources: { url: string; title: string | null }[] }[];
  cost_usd: number;
  cached: boolean;
  message: string | null;
}

export interface Step {
  step: number;
  kind: "thought" | "action" | "observation" | "answer";
  content: string;
  observation?: string;
  tool?: string;
  role?: string;
}

export interface Example {
  id: string;
  title: string;
  about: string;
  origin: string;
  task: string;
  question: string | null;
  sources: string[];
  answer: string;
  agent_steps: Step[];
  gold: "grounded" | "hallucinated" | null;
  gold_spans: { start: number; end: number; type: string | null }[];
  profile?: string | null;
}

export type ExampleBrief = Pick<Example, "id" | "title" | "about" | "origin" | "task">;

export interface Health {
  state: "loading" | "warming" | "ready" | "failed";
  error: string | null;
  warm_seconds: number | null;
  model_version: string | null;
  tracer_version: string | null;
  profiles: string[];
  online?: { configured: boolean; model: string; spent_today: number; budget: number };
  examples: number;
  agent_examples: number;
  fool_answers: number;
}

export interface Change {
  start: number;
  end: number;
  original: string;
  new: string;
  reason: string;
}

export interface Healing {
  original: string;
  answer: string;
  rounds: { answer: string; changes: Change[]; report: Report }[];
  seconds: number;
}

export interface FoolAnswer {
  id: string;
  question: string | null;
  answer: string;
  sources: string[];
  task: string;
}

export interface FoolResult {
  report: Report;
  edit: [number, number] | null;
  caught: boolean;
  located: boolean;
  cautioned: boolean;
  seconds: number;
}

export type AnswerStatus = "checked" | "healed" | "light" | "opinion" | "unchecked" | "not_in_documents" | "stopped";

/** One step of the agent that works from the library, with the Guardian's word on it (rag/agent.py). */
export interface RunStep {
  step: number;
  kind: "thought" | "action" | "answer" | "guardian";
  content: string;
  tool: string | null;
  observation: string | null;
  failed: boolean;
  alert: "warning" | "stop" | null;
  reason: string | null;
}

export interface Citation {
  n: number;
  document: string;
  collection: string;
  page: number | null;
  text: string;
  place: string | null;
  role: string | null;
  document_id: number | null;
  reviewed: boolean;
  inferred: boolean;
}

/** An answer written from the library (rag/answer.py). */
export interface RagAnswer {
  status: AnswerStatus;
  question: string;
  searched_for: string;
  text: string;
  generator: string | null;
  citations: Citation[];
  report: Report | null;
  light: { start: number; end: number; text: string; status: "close" | "doubtful"; reasons: string[] }[];
  looked_at: string[];
  original: string | null;
  similarity: number;
  cost_usd: number;
  seconds: number;
  notes: string[];
  steps?: RunStep[];
  corrections?: number;
}

export type AskTurn = { question: string; answer: RagAnswer };

export interface ShelfEntry {
  id: number;
  collection: "mine" | "project";
  name: string;
  kind: string;
  pages: number | null;
  language: string | null;
  added_at: string;
  passages: number;
  reader: string | null;
  concerns: string | null;
  reviewed_at: string | null;
}

export interface Shelf {
  documents: ShelfEntry[];
  types: string[];
  max_bytes: number;
  media_types: string[];
  max_media_bytes: number;
}

export interface ReadPart {
  index: number;
  text: string;
  role: "transcript" | "ocr" | "description" | "confirmed";
  place: string | null;
  start: number | null;
  box: [number, number, number, number] | null;
  confidence: number | null;
  doubtful: boolean;
  opinion: boolean;
}

/** What was read in a recording or an image, waiting for a person's review (D-167). */
export interface Draft {
  draft: string;
  name: string;
  kind: "audio" | "image";
  reader: string;
  language: string | null;
  concerns: string[];
  parts: ReadPart[];
  seconds: number;
}

export interface CheckInput {
  question: string;
  sources: string[];
  sourceNames?: (string | null)[];
  answer: string;
  task: Task;
  profile?: string | null;
  exampleId?: string | null;
  /** The language a media reader found in the sources, for texts too short to tell. */
  language?: string | null;
}
