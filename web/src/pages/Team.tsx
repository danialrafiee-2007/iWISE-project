import { useI18n } from "../i18n";
import { Heading } from "../layers/Heading";

// The people behind Truth Guardian: the supervisor and the four team members. Their names, photos (put them in
// web/public/team/ and give the path, such as "/team/name.jpg") and a line about each are added by the team; until
// then each card says so.

type Member = { role: "supervisor" | "member"; name?: string; photo?: string };

const MEMBERS: Member[] = [{ role: "supervisor" }, { role: "member" }, { role: "member" }, { role: "member" }, { role: "member" }];

export default function Team() {
  const { t } = useI18n();
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-10 px-4 py-14 sm:px-8">
      <header className="flex max-w-3xl flex-col gap-4">
        <span className="eyebrow">{t("landing.badge")}</span>
        <Heading className="m-0 text-[clamp(34px,4vw,52px)] font-normal leading-tight tracking-tight">{t("team.title")}</Heading>
        <p className="m-0 text-lg leading-relaxed text-fog-300">{t("team.lead")}</p>
      </header>
      <ul className="m-0 grid list-none gap-5 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {MEMBERS.map((member, i) => (
          <li key={i} className="card flex flex-col items-center gap-3 p-7 text-center">
            {member.photo ? (
              <img src={member.photo} alt={member.name ?? ""} className="h-28 w-28 rounded-full object-cover" />
            ) : (
              <div className="grid h-28 w-28 place-items-center rounded-full border border-dashed border-line bg-ink-700 text-fog-400" aria-hidden="true">
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
                  <circle cx="12" cy="8.5" r="4" />
                  <path d="M4.5 20c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
                </svg>
              </div>
            )}
            <span className="eyebrow">{t(member.role === "supervisor" ? "team.supervisor" : "team.member")}</span>
            <h2 className="m-0 text-xl font-medium">{member.name ?? t("team.namePending")}</h2>
            <p className="m-0 text-sm text-fog-400">{t("team.bioPending")}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
