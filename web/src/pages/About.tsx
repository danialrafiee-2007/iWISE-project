import { formatNumber, useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";
import { Link } from "../lib/router";

// What the challenge asks, how the text engine reaches a verdict, and where it runs.

const STAGES = 5;

export default function About() {
  const { t } = useI18n();
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-12 px-4 py-14 sm:px-8">
      <header className="flex max-w-3xl flex-col gap-4">
        <span className="eyebrow">{t("landing.badge")}</span>
        <Heading className="m-0 text-[clamp(34px,4vw,52px)] font-normal leading-tight tracking-tight">{t("about.title")}</Heading>
        <p className="m-0 text-lg leading-relaxed text-fog-300">{t("about.lead")}</p>
      </header>

      <section className="flex max-w-3xl flex-col gap-3" aria-labelledby="about-challenge">
        <h2 id="about-challenge" className="eyebrow m-0">
          {t("about.challengeTitle")}
        </h2>
        <p className="m-0 text-[17px] leading-relaxed text-fog-200">{t("about.challengeBody")}</p>
      </section>

      <section className="flex flex-col gap-5" aria-labelledby="about-engine">
        <div className="flex max-w-3xl flex-col gap-3">
          <h2 id="about-engine" className="eyebrow m-0">
            {t("about.engineTitle")}
          </h2>
          <p className="m-0 text-[17px] leading-relaxed text-fog-200">{t("about.engineBody")}</p>
        </div>
        <ol className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: STAGES }, (_, k) => (
            <li key={k} className="card flex flex-col gap-2 p-6">
              <span className="font-sans text-xs font-medium uppercase tracking-[0.16em] text-beam-400">
                {formatNumber(k + 1, 0, 2)} · {t(`about.s${k + 1}.label` as MessageKey)}
              </span>
              <h3 className="m-0 text-xl font-medium leading-snug">{t(`about.s${k + 1}.title` as MessageKey)}</h3>
              <p className="m-0 text-[15px] leading-relaxed text-fog-300">{t(`about.s${k + 1}.sub` as MessageKey)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="flex max-w-3xl flex-col gap-3" aria-labelledby="about-runs">
        <h2 id="about-runs" className="eyebrow m-0">
          {t("about.runsTitle")}
        </h2>
        <p className="m-0 text-[17px] leading-relaxed text-fog-200">{t("about.runsBody")}</p>
        <p className="m-0 text-[15px] text-fog-300">
          {t("about.cardPre")}
          <Link to="/model" className="text-beam-300">
            {t("about.cardLink")}
          </Link>
          {t("about.cardPost")}
        </p>
      </section>
    </div>
  );
}
