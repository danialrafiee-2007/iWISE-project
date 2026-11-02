import { useEffect, useRef, useState } from "react";
import { useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";

// The people behind Truth Guardian: the teacher and guide on top, the four team members in a row below. Choosing a
// card opens that person's introduction over this same page. A photo is a file in web/public/people/; a person without
// one shows the same ground with an icon until it is added. Names stay in Latin in every language, as the team writes
// them. What is said about each person is only what the team gave: the role, and what that part of the project covers.

type Person = { name: string; photo?: string; rank: MessageKey; tag: MessageKey; role: MessageKey; bio: MessageKey };

const TEACHER: Person = { name: "Hamed Khalilavi", photo: "/people/hamed-khalilavi.jpg", rank: "team.supervisor", tag: "team.tag.ai", role: "team.role.hamed", bio: "team.bio.hamed" };
const MEMBERS: Person[] = [
  { name: "Danial Rafiee", photo: "/people/danial-rafiee.jpg", rank: "team.member", tag: "team.tag.models", role: "team.role.models", bio: "team.bio.models" },
  { name: "Mojdeh Ghazvinian", rank: "team.member", tag: "team.tag.models", role: "team.role.models", bio: "team.bio.models" },
  { name: "Sepehr Kakoli", rank: "team.member", tag: "team.tag.coordination", role: "team.role.sepehr", bio: "team.bio.sepehr" },
  { name: "Majid Rafiee", rank: "team.member", tag: "team.tag.sync", role: "team.role.majid", bio: "team.bio.majid" },
];

function Photo({ person, className }: { person: Person; className: string }) {
  if (person.photo) return <img src={person.photo} alt={person.name} width={900} height={1125} decoding="async" className={`object-cover object-[50%_12%] ${className}`} />;
  return (
    <div className={`grid place-items-center bg-[linear-gradient(160deg,#e9dfc8,#dccfb2)] text-fog-400 ${className}`} aria-hidden="true">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round">
        <circle cx="12" cy="8.5" r="4" />
        <path d="M4.5 20c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
      </svg>
    </div>
  );
}

const Tag = ({ label }: { label: string }) => <span className="rounded-full border border-white/30 bg-beam-400 px-3 py-1 font-sans text-[11px] font-semibold uppercase tracking-[0.12em] text-white">{label}</span>;

function Card({ person, onOpen }: { person: Person; onOpen: () => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex h-full w-full cursor-pointer flex-col overflow-hidden rounded-[22px] border border-line bg-ink-950 p-0 text-start shadow-[0_16px_34px_-22px_rgba(44,58,52,.45)] transition-[transform,border-color,box-shadow] duration-300 hover:-translate-y-1 hover:border-beam-400 hover:shadow-[0_22px_40px_-22px_rgba(44,58,52,.6)]"
    >
      <span className="relative block aspect-[5/4] w-full overflow-hidden">
        <Photo person={person} className="block h-full w-full transition-transform duration-500 group-hover:scale-[1.03]" />
        <span className="absolute start-3 top-3">
          <Tag label={t(person.tag)} />
        </span>
      </span>
      <span className="flex flex-1 flex-col gap-2 px-5 pb-4 pt-4">
        <span className="font-sans text-xs text-fog-400">{t(person.rank)}</span>
        <span className="font-display text-[21px] font-medium leading-snug text-fog-100 transition-colors duration-300 group-hover:text-beam-300" lang="en">
          {person.name}
        </span>
        <span className="line-clamp-2 min-h-[2.9em] text-[15px] leading-snug text-fog-300">{t(person.role)}</span>
        <span className="mt-auto flex items-center gap-2.5 border-t border-line pt-3">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-beam-400 font-sans text-xs font-medium text-white" aria-hidden="true" lang="en">
            {person.name[0]}
          </span>
          <span className="font-sans text-[13px] text-fog-300">{t("team.more")}</span>
        </span>
      </span>
    </button>
  );
}

export default function Team() {
  const { t } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [person, setPerson] = useState<Person | null>(null);

  // The page behind stays where it is while an introduction is open; padding takes the scrollbar's place, so it does not
  // shift sideways either.
  const release = () => {
    const page = document.documentElement;
    page.classList.remove("person-open");
    page.style.paddingRight = "";
  };
  useEffect(() => release, []);
  const open = (next: Person) => {
    const page = document.documentElement;
    setPerson(next);
    page.style.paddingRight = `${window.innerWidth - page.clientWidth}px`;
    page.classList.add("person-open");
    dialog.current?.showModal();
  };

  return (
    <div className="page-in mx-auto flex max-w-[1320px] flex-col gap-10 px-4 py-14 sm:px-8">
      <header className="flex max-w-3xl flex-col gap-4">
        <span className="eyebrow">{t("landing.badge")}</span>
        <Heading className="m-0 text-[clamp(34px,4vw,52px)] font-normal leading-tight tracking-tight">{t("team.title")}</Heading>
        <p className="m-0 text-lg leading-relaxed text-fog-300">{t("team.lead")}</p>
      </header>
      <div className="mx-auto w-full max-w-[340px]">
        <Card person={TEACHER} onOpen={() => open(TEACHER)} />
      </div>
      <ul className="m-0 grid list-none gap-5 p-0 sm:grid-cols-2 lg:grid-cols-4">
        {MEMBERS.map((member) => (
          <li key={member.name}>
            <Card person={member} onOpen={() => open(member)} />
          </li>
        ))}
      </ul>

      <dialog
        ref={dialog}
        className="person-dialog m-auto w-[min(780px,calc(100vw-32px))] max-w-none overflow-hidden rounded-[24px] border border-line bg-ink-950 p-0 text-fog-100"
        aria-labelledby="person-name"
        onClick={(e) => {
          if (e.target === dialog.current) dialog.current.close();
        }}
        onClose={release}
      >
        {person && (
          <div className="relative grid max-h-[calc(100dvh-32px)] overflow-y-auto sm:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <button type="button" aria-label={t("team.close")} onClick={() => dialog.current?.close()} className="absolute end-3 top-3 z-10 grid h-10 w-10 cursor-pointer place-items-center rounded-full border border-line bg-ink-950/90 text-fog-200 transition-colors hover:text-fog-100">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            <Photo person={person} className="h-64 w-full sm:h-full sm:min-h-[420px]" />
            <div className="flex flex-col justify-center gap-3 p-7 sm:p-9">
              <span className="self-start">
                <Tag label={t(person.tag)} />
              </span>
              <span className="font-sans text-xs text-fog-400">{t(person.rank)}</span>
              <h2 id="person-name" className="m-0 font-display text-[30px] font-medium leading-tight" lang="en">
                {person.name}
              </h2>
              <p className="m-0 font-sans text-sm font-medium text-beam-300">{t(person.role)}</p>
              <p className="m-0 border-t border-line pt-4 text-[17px] leading-relaxed text-fog-200">{t(person.bio)}</p>
            </div>
          </div>
        )}
      </dialog>
    </div>
  );
}
