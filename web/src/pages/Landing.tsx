import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from "react";
import InputPanel, { type InputKind } from "../components/InputPanels";
import { formatNumber, useI18n, type MessageKey } from "../i18n";
import { Ascent, type AscentRow } from "../layers/Ascent";
import { NeuralBrain } from "../layers/brain/NeuralBrain";
import { Heading } from "../layers/Heading";
import { useWorkspace } from "../lib/workspace";

// The challenge inputs in the order the rows show them; each row opens its own input panel.
const KINDS: InputKind[] = ["text", "audio", "image", "video"];
const INPUT_COUNT = KINDS.length;

// The brain is drawn only where the screen leaves room for it beside the words (.hero-words in styles.css keeps the
// words narrow enough); on narrow or upright screens it would sit under them.
const SIDE_BY_SIDE = "(min-width: 1024px) and (min-aspect-ratio: 5/4)";

// The opening camera (config.ts, cameraFov 38) frames the brain's centre 0.255 viewport heights right of the canvas's
// middle, half its width 0.30. The brain's near edge goes GAP pixels past the end of the words.
const BRAIN_CENTRE = 0.255;
const BRAIN_HALF = 0.3;
const GAP = 40;

/** Places the brain's canvas so the brain stands just past the words. The canvas is widened, never shifted, so it
 *  always covers the whole screen; on right-to-left pages it is mirrored to stand on the left. */
function useBrainStage(words: RefObject<HTMLElement | null>, rtl: boolean, active: boolean) {
  const [style, setStyle] = useState<CSSProperties>({ left: 0, width: "100%" });
  useLayoutEffect(() => {
    const el = words.current;
    if (!active || !el) return;
    const place = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const box = el.getBoundingClientRect();
      const reach = rtl ? width - box.left : box.right;
      const fromStart = reach + GAP + (BRAIN_HALF - BRAIN_CENTRE) * height;
      const middle = rtl ? width - fromStart : fromStart;
      const half = Math.max(middle, width - middle);
      setStyle({ left: middle - half, width: 2 * half, scale: rtl ? "-1 1" : undefined });
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(el);
    window.addEventListener("resize", place);
    document.fonts?.ready.then(place);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", place);
    };
  }, [words, rtl, active]);
  return style;
}

function useScrollFraction(ref: React.RefObject<HTMLElement | null>) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let raf = 0;
    const read = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const travel = el.offsetHeight - window.innerHeight;
      setValue(travel > 0 ? Math.min(1, Math.max(0, -rect.top / travel)) : 0);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, [ref]);
  return value;
}

/** The height of the site's sticky top bar, which grows to several lines on a narrow screen and in some languages. */
function useBarHeight() {
  const [height, setHeight] = useState(64);
  useEffect(() => {
    const bar = document.querySelector("header");
    if (!bar) return;
    const observer = new ResizeObserver(() => setHeight(bar.getBoundingClientRect().height));
    observer.observe(bar);
    return () => observer.disconnect();
  }, []);
  return height;
}

function useMedia(query: string) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatch(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return match;
}

export default function Landing() {
  const { busy } = useWorkspace();
  const how = useRef<HTMLElement>(null);
  const words = useRef<HTMLDivElement>(null);
  const howProgress = useScrollFraction(how);
  const roomForBrain = useMedia(SIDE_BY_SIDE);
  const { dir, t } = useI18n();
  const stage = useBrainStage(words, dir === "rtl", roomForBrain);
  const [open, setOpen] = useState<number | null>(null);
  // The inputs' frame sticks just under the top bar and ends above the page's footer (64px), which would otherwise push
  // it up at the last row; the card inside leaves room for the section's heading.
  const top = useBarHeight() + 8;
  const frame = window.innerHeight - top - 68;

  // Escape closes the open panel, unless the person is typing in it.
  useEffect(() => {
    if (open == null) return;
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, select");
      if (e.key === "Escape" && !typing) setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  /** Opens row `i` (or closes it when it is open) and scrolls to where that row stands, so closing leaves it in place. */
  const toggle = (i: number) => {
    setOpen((o) => (o === i ? null : i));
    const el = how.current;
    if (!el) return;
    const travel = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY + (travel * i) / (INPUT_COUNT - 1), behavior: "smooth" });
  };
  const INPUTS: AscentRow[] = Array.from({ length: INPUT_COUNT }, (_, k) => ({
    label: t(`landing.in${k + 1}.label` as MessageKey),
    chip: t("landing.chip", { i: formatNumber(k + 1), n: formatNumber(INPUT_COUNT) }),
    title: t(`landing.in${k + 1}.title` as MessageKey),
    sub: t(`landing.in${k + 1}.sub` as MessageKey),
  }));

  return (
    <div className="theme-night relative isolate">
      {/* The solid ground matches the brain's own background, so the light text stays readable while the scene loads. */}
      <div className="fixed inset-0 -z-10 overflow-hidden bg-ink-950" aria-hidden="true">
        {roomForBrain && (
          <div className="absolute inset-y-0" style={stage}>
            {/* The camera holds still while the opening words are on screen, and flies through its story as the inputs scroll. */}
            <NeuralBrain progress={howProgress} paused={busy} mirror={dir === "rtl"} />
          </div>
        )}
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(9,18,14,.86)_0%,rgba(9,18,14,.5)_45%,rgba(9,18,14,0)_75%)] rtl:bg-[linear-gradient(270deg,rgba(9,18,14,.86)_0%,rgba(9,18,14,.5)_45%,rgba(9,18,14,0)_75%)]" />
      </div>

      <section className="mx-auto flex min-h-[calc(100dvh-64px)] max-w-[1320px] flex-col justify-center px-4 py-16 sm:px-8">
        {/* As wide as the words themselves (up to the room beside the brain), so the brain can stand just past them. */}
        <div ref={words} className="hero-words flex w-fit flex-col items-start gap-7">
          <span className="eyebrow">{t("landing.badge")}</span>
          <Heading className="hero-title m-0 font-normal leading-[1.06] tracking-[-0.03em]">{t("landing.title")}</Heading>
          <p className="m-0 max-w-[600px] text-lg leading-relaxed text-fog-300 [text-wrap:pretty]">{t("landing.lead")}</p>
        </div>
      </section>

      <section ref={how} className="relative h-[300vh]" aria-label={t("landing.inputs")}>
        <div className="sticky mx-auto flex max-w-[1320px] flex-col gap-4 px-4 sm:px-8" style={{ top, height: `calc(100dvh - ${top + 68}px)` }}>
          <h2 className="eyebrow m-0">{t("landing.inputs")}</h2>
          <div className="min-h-0 flex-1">
            <Ascent
              night
              rows={INPUTS}
              value={howProgress * (INPUTS.length - 1)}
              // Open, the card takes all the room the sticky frame has, for the panel's answer and its writing box.
              height={open != null ? Math.max(440, frame - 40) : Math.max(360, Math.min(620, frame - 60))}
              open={open}
              onToggle={toggle}
              panel={open != null ? <InputPanel kind={KINDS[open]} /> : null}
              cta={t("inputs.cta")}
              closeLabel={t("inputs.close")}
            />
          </div>
        </div>
      </section>
    </div>
  );
}
