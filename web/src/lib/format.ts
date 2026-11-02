import { formatNumber, formatPercent, t, type MessageKey } from "../i18n";
import type { Blame, Grade, Lane, Status, Verdict } from "./types";

// Numbers and labels in the interface language. The labels are getters, read at render time, so a component that
// re-renders after a language change shows them in the new language.

export const pct = (x: number | null | undefined, digits = 0) => (x == null ? t("common.na") : formatPercent(x, digits));
export const num = (x: number | null | undefined, digits = 2) => (x == null ? t("common.na") : formatNumber(x, digits));

function labels<K extends string>(prefix: string, keys: readonly K[]): Record<K, string> {
  const out = {} as Record<K, string>;
  for (const key of keys) Object.defineProperty(out, key, { get: () => t(`${prefix}.${key}` as MessageKey), enumerable: true });
  return out;
}

function withLabels<K extends string, V extends object>(prefix: string, rows: Record<K, V>): Record<K, V & { label: string }> {
  const out = {} as Record<K, V & { label: string }>;
  for (const key of Object.keys(rows) as K[]) {
    out[key] = Object.defineProperty({ ...rows[key] }, "label", { get: () => t(`${prefix}.${key}` as MessageKey), enumerable: true }) as V & { label: string };
  }
  return out;
}

export const STATUS = withLabels<Status, { color: string; line: string }>("status", {
  supported: { color: "var(--color-ok)", line: "solid" },
  contradicted: { color: "var(--color-bad)", line: "solid" },
  unsupported: { color: "var(--color-warn)", line: "dashed" },
  insufficient_evidence: { color: "var(--color-weak)", line: "dotted" },
  contested: { color: "var(--color-split)", line: "double" },
});

export const VERDICT = withLabels<Verdict, { color: string }>("verdict", {
  grounded: { color: "var(--color-ok)" },
  hallucinated: { color: "var(--color-bad)" },
  uncertain: { color: "var(--color-warn)" },
});

export const GRADE_COLOR: Record<Grade, string> = {
  A: "var(--color-ok)",
  B: "#86efac",
  C: "var(--color-warn)",
  D: "#fb923c",
  F: "var(--color-bad)",
};

export const LANE = withLabels<Lane, { color: string }>("lane", {
  pass: { color: "var(--color-ok)" },
  review: { color: "var(--color-warn)" },
  block: { color: "var(--color-bad)" },
});

export const BLAME: Record<Blame, string> = labels("blame", ["retrieval", "generation", "weak_sources", "conflicting_sources", "none", "unknown"] as const);

export const STAGES: Record<string, string> = labels("stage", ["lexical", "symbolic", "dense", "hhem", "polarity", "shifts", "score", "claims", "checks", "verdict", "multilingual", "online"] as const);

export const KIND_LABEL: Record<string, string> = labels("kind", ["number", "entity", "negation", "antonym", "addition", "role_swap", "quantifier", "certainty"] as const);

export const TASK_LABEL: Record<string, string> = labels("task", ["qa", "summary", "data2text", "other", "agent", "live"] as const);
