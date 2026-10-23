import type { Blame, Grade, Lane, Status, Verdict } from "./types";

export const pct = (x: number | null | undefined, digits = 0) => (x == null ? "n/a" : `${(x * 100).toFixed(digits)}%`);
export const num = (x: number | null | undefined, digits = 2) => (x == null ? "n/a" : x.toFixed(digits));

export const STATUS: Record<Status, { label: string; color: string; line: string }> = {
  supported: { label: "Supported", color: "var(--color-ok)", line: "solid" },
  contradicted: { label: "Contradicted", color: "var(--color-bad)", line: "solid" },
  unsupported: { label: "Unsupported", color: "var(--color-warn)", line: "dashed" },
  insufficient_evidence: { label: "Weak evidence", color: "var(--color-weak)", line: "dotted" },
  contested: { label: "Sources disagree", color: "var(--color-split)", line: "double" },
};

export const VERDICT: Record<Verdict, { label: string; color: string }> = {
  grounded: { label: "Grounded", color: "var(--color-ok)" },
  hallucinated: { label: "Hallucinated", color: "var(--color-bad)" },
  uncertain: { label: "Uncertain", color: "var(--color-warn)" },
};

export const GRADE_COLOR: Record<Grade, string> = {
  A: "var(--color-ok)",
  B: "#86efac",
  C: "var(--color-warn)",
  D: "#fb923c",
  F: "var(--color-bad)",
};

export const LANE: Record<Lane, { label: string; color: string; hint: string }> = {
  pass: { label: "Pass", color: "var(--color-ok)", hint: "can go out unchecked" },
  review: { label: "Review", color: "var(--color-warn)", hint: "a person should check it" },
  block: { label: "Block", color: "var(--color-bad)", hint: "should not go out" },
};

export const BLAME: Record<Blame, string> = {
  retrieval: "Retrieval",
  generation: "The language model",
  weak_sources: "Weak sources",
  conflicting_sources: "Conflicting sources",
  none: "Nobody",
  unknown: "Cannot tell",
};

export const STAGES: Record<string, string> = {
  lexical: "Word overlap with the sources",
  symbolic: "Numbers, names and dates",
  dense: "Meaning similarity",
  hhem: "Consistency model (HHEM)",
  polarity: "Negations and opposites",
  shifts: "Swapped roles and overclaims",
  score: "Fusion model score",
  claims: "Claims, fixes and exact words",
  checks: "Omissions, conflicts, citations",
  verdict: "Verdict, guarantee and card",
};

export const KIND_LABEL: Record<string, string> = {
  number: "Change a number",
  entity: "Swap a name",
  negation: "Add a negation",
  antonym: "Use the opposite word",
  addition: "Add an unsupported claim",
  role_swap: "Swap who did what",
  quantifier: "Exaggerate a quantity",
  certainty: "Drop a hedge",
};

export const TASK_LABEL: Record<string, string> = { qa: "Question answering", summary: "Summary", data2text: "Data to text", other: "Other", agent: "Agent", live: "Other" };
