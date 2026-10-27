import { formatNumber, useI18n, type MessageKey } from "../i18n";
import { Link } from "../lib/router";
import { TOOLS } from "./EngineMenu";
import { ShieldMark } from "./ShieldMark";

// The foot of every page, after iridology.app's: a pale sage ground, the shield and the name with a line on what the
// project does, three columns of links in the site's own order (the AI engine by input, the text tools, the
// project's pages), and a rule in warm sand above the closing line. Colours measured from iridology's footer.

const COLUMNS: { title: MessageKey; links: { to: string; label: MessageKey }[] }[] = [
  {
    title: "nav.engine",
    links: [
      { to: "/analyze", label: "nav.text" },
      { to: "/audio", label: "nav.audio" },
      { to: "/image", label: "nav.image" },
      { to: "/video", label: "nav.video" },
    ],
  },
  { title: "footer.tools", links: TOOLS.filter((tool) => tool.to !== "/analyze") },
  {
    title: "footer.project",
    links: [
      { to: "/", label: "nav.home" },
      { to: "/about", label: "nav.about" },
      { to: "/team", label: "nav.team" },
      { to: "/contact", label: "nav.contact" },
    ],
  },
];

export function Footer() {
  const { t } = useI18n();
  return (
    // Positioned, so it is painted over the landing page's fixed night ground rather than under it.
    <footer className="relative border-t border-[#c6d9ca] bg-[#e7f0e8] font-serif text-[#34443b]">
      <div className="mx-auto max-w-[1320px] px-4 pb-10 pt-16 sm:px-8 lg:pt-20">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr] lg:gap-10">
          <div className="flex flex-col gap-5 sm:col-span-2 lg:col-span-1">
            {/* The name and shield as in the top bar: the breathing light all round, the sheen, the turning shield. */}
            <Link to="/" className="brand relative isolate flex w-fit items-center gap-3 no-underline">
              <span className="brand-glow" aria-hidden="true" />
              <ShieldMark size={44} />
              <span className="brand-name font-display text-[30px] font-medium leading-none tracking-tight" lang="en">
                Truth Guardian
              </span>
            </Link>
            <p className="m-0 max-w-[380px] text-[17px] leading-relaxed text-[#3d4c44]">{t("footer.about")}</p>
          </div>
          {COLUMNS.map((column) => (
            <nav key={column.title} aria-label={t(column.title)} className="flex flex-col gap-5">
              <h2 className="m-0 font-serif text-[13px] font-semibold uppercase tracking-[0.2em] text-[#286046]">{t(column.title)}</h2>
              <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                {column.links.map((link) => (
                  <li key={link.to}>
                    {/* Lit under the pointer like the top bar's links: Home's tint and the soft jade light. */}
                    <Link to={link.to} className="nav-glow -mx-3 inline-block rounded-full px-3 py-1 text-[17px] text-[#34443b] no-underline">
                      {t(link.label)}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="mt-14 flex flex-col gap-3 border-t border-[#d4c2a6] pt-7 text-[15px] text-[#3d4c44] sm:flex-row sm:items-center sm:justify-between">
          <span>{t("footer.rights", { year: formatNumber(new Date().getFullYear()) })}</span>
          <span>{t("footer.offline")}</span>
        </div>
      </div>
    </footer>
  );
}
