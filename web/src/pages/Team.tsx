import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ShieldMark } from "../components/ShieldMark";
import { useI18n, type MessageKey } from "../i18n";
import { Heading } from "../layers/Heading";

// The people behind Truth Guardian: the teacher and guide on top, the four team members in a row below, all on screen
// on arrival, without scrolling (.team-fit). Choosing a card opens that person's introduction over this same page. A photo is a file in web/public/people/; a person without
// one shows the same ground with an icon until it is added. Names stay in Latin in every language, as the team writes
// them. What is said about each person is only what the team gave: the role, and what that part of the project covers.

type Person = { name: string; photo?: string; rank: MessageKey; role: MessageKey; bio: MessageKey };

const TEACHER: Person = { name: "Hamed Khalilavi", photo: "/people/hamed-khalilavi.jpg", rank: "team.supervisor", role: "team.role.hamed", bio: "team.bio.hamed" };
const MEMBERS: Person[] = [
  { name: "Danial Rafiee", photo: "/people/danial-rafiee.jpg", rank: "team.member", role: "team.role.models", bio: "team.bio.models" },
  { name: "Mojdeh Ghazvinian", rank: "team.member", role: "team.role.models", bio: "team.bio.models" },
  { name: "Sepehr Kakoli", rank: "team.member", role: "team.role.sepehr", bio: "team.bio.sepehr" },
  { name: "Majid Rafiee", rank: "team.member", role: "team.role.majid", bio: "team.bio.majid" },
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

/** The project's shield in the corner of a photo; it turns only while its card is under the pointer. */
const Logo = () => (
  <span className="person-logo absolute start-2.5 top-2.5">
    <ShieldMark size={32} />
  </span>
);

function Card({ person, onOpen }: { person: Person; onOpen: () => void }) {
  const { t } = useI18n();
  return (
    <button type="button" onClick={onOpen} className="card person-card group flex h-full min-h-0 w-full cursor-pointer flex-col overflow-hidden rounded-[20px] p-0 text-start">
      {/* The photo takes what the text leaves, so the card fits whatever height its row has. On a short window or a
          phone the lesser lines give way first; the whole introduction is one click away. */}
      <span className="relative block min-h-0 w-full flex-1 overflow-hidden">
        <Photo person={person} className="absolute inset-0 h-full w-full" />
        <Logo />
      </span>
      <span className="flex shrink-0 flex-col gap-1 px-4 py-2.5 max-sm:px-3 max-sm:py-2">
        <span className="font-sans text-xs text-fog-400 max-sm:hidden [@media(max-height:700px)]:hidden">{t(person.rank)}</span>
        <span className="truncate font-display text-[20px] font-medium leading-snug text-fog-100 transition-colors duration-300 group-hover:text-beam-300 max-sm:text-[15px]" lang="en">
          {person.name}
        </span>
        <span className="line-clamp-2 min-h-[2.75em] text-sm leading-snug text-fog-300 max-sm:hidden [@media(max-height:700px)]:hidden">{t(person.role)}</span>
        <span className="mt-1 flex items-center gap-2 border-t border-line pt-2 max-sm:hidden [@media(max-height:900px)]:hidden">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-beam-400 font-sans text-[11px] font-medium text-white" aria-hidden="true" lang="en">
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
  const page = useRef<HTMLDivElement>(null);
  const [person, setPerson] = useState<Person | null>(null);

  // The whole team fills the screen under the top bar, whose height changes with the language and the window.
  useLayoutEffect(() => {
    const bar = document.querySelector("header");
    if (!bar) return;
    const fit = () => page.current?.style.setProperty("--bar", `${bar.offsetHeight}px`);
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(bar);
    return () => observer.disconnect();
  }, []);

  // The page behind stays where it is while an introduction is open; padding takes the scrollbar's place, so it does not
  // shift sideways either.
  const release = () => {
    const root = document.documentElement;
    root.classList.remove("person-open");
    root.style.paddingRight = "";
  };
  useEffect(() => {
    new Image().src = "/textures/parchment.jpg"; // ready before the first introduction opens on it
    return release;
  }, []);
  const open = (next: Person) => {
    const root = document.documentElement;
    setPerson(next);
    root.style.paddingRight = `${window.innerWidth - root.clientWidth}px`;
    root.classList.add("person-open");
    dialog.current?.showModal();
  };

  return (
    <div ref={page} className="team-fit page-in mx-auto flex max-w-[1320px] flex-col gap-3 px-4 py-3 sm:px-8">
      <header className="flex shrink-0 flex-wrap items-baseline gap-x-5">
        <Heading className="m-0 text-[clamp(24px,4.4vh,38px)] font-normal leading-tight tracking-tight">{t("team.title")}</Heading>
        <p className="m-0 text-[15px] leading-snug text-fog-300 max-sm:hidden [@media(max-height:640px)]:hidden">{t("team.lead")}</p>
      </header>
      <div className="grid min-h-0 flex-1 grid-rows-[1fr_2fr] gap-3 sm:grid-rows-2 sm:gap-4">
        <div className="flex min-h-0 justify-center">
          <div className="min-h-0 w-[calc(50%-0.375rem)] sm:w-[calc(25%-0.75rem)]">
            <Card person={TEACHER} onOpen={() => open(TEACHER)} />
          </div>
        </div>
        <ul className="m-0 grid min-h-0 list-none grid-cols-2 grid-rows-2 gap-3 p-0 sm:grid-cols-4 sm:grid-rows-1 sm:gap-4">
          {MEMBERS.map((member) => (
            <li key={member.name} className="min-h-0">
              <Card person={member} onOpen={() => open(member)} />
            </li>
          ))}
        </ul>
      </div>

      <dialog
        ref={dialog}
        className="person-dialog m-auto w-[min(1080px,calc(100vw-32px))] max-w-none overflow-hidden rounded-[26px] border border-line bg-ink-950 p-0 text-fog-100"
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
            <div className="relative">
              <Photo person={person} className="h-72 w-full sm:h-full sm:min-h-[600px]" />
              <Logo />
            </div>
            <div className="paper flex flex-col justify-center gap-4 p-7 sm:p-12">
              <span className="font-sans text-sm text-fog-100">{t(person.rank)}</span>
              <h2 id="person-name" className="m-0 font-display text-[32px] font-medium leading-tight sm:text-[42px]" lang="en">
                {person.name}
              </h2>
              <p className="m-0 font-sans text-base font-medium text-[#264a38]">{t(person.role)}</p>
              <p className="m-0 border-t border-[#a98a58] pt-5 text-[18px] leading-relaxed text-fog-100 sm:text-[20px]">{t(person.bio)}</p>
            </div>
          </div>
        )}
      </dialog>
    </div>
  );
}
