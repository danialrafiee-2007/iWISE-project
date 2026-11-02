import { useI18n, type MessageKey } from "../i18n";
import { Link } from "../lib/router";

// The menu lists only what Challenge 4 asks for (EngineMenu). What uses the same check another way lives inside "Check
// an answer": this row leads there from that page, and the link at the top of each of those pages leads back. Healing
// has no place in the row: it needs an answer to work on, so the report offers it.

const MORE: { to: string; label: MessageKey }[] = [
  { to: "/fool", label: "nav.fool" },
  { to: "/audit", label: "nav.audit" },
  { to: "/examples", label: "nav.examples" },
];

export function CheckMore() {
  const { t } = useI18n();
  return (
    <nav aria-label={t("analyze.more")} className="flex flex-wrap items-center gap-1.5">
      <span className="label me-1.5">{t("analyze.more")}</span>
      {MORE.map((item) => (
        <Link key={item.to} to={item.to} className="nav-glow rounded-full px-4 py-2 font-sans text-sm text-fog-300 no-underline">
          {t(item.label)}
        </Link>
      ))}
    </nav>
  );
}

export function BackToCheck() {
  const { t } = useI18n();
  return (
    <Link to="/analyze" className="nav-glow inline-flex w-fit items-center gap-1.5 rounded-full px-3 py-1.5 font-sans text-sm text-fog-300 no-underline">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="rtl:-scale-x-100">
        <path d="M15 6l-6 6 6 6" />
      </svg>
      {t("nav.analyze")}
    </Link>
  );
}
