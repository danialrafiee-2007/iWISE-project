import { useMemo } from "react";
import { exampleText, formatNumber, useI18n } from "../i18n";
import { SpectraDeck, type SpectraCard } from "../layers/SpectraDeck";
import { TASK_LABEL } from "../lib/format";
import type { ExampleBrief } from "../lib/types";

// The ready-made answers as a card deck on the Check an answer page; choosing one checks it there.

const GLOW = ["#fb7185", "#c4b5fd", "#a78bfa", "#fbbf24", "#34d399", "#60a5fa", "#2dd4bf", "#f472b6", "#fb923c", "#93c5fd", "#5eead4", "#e879f9"];

export function ExamplesDeck({ examples, onPick, paused }: { examples: ExampleBrief[]; onPick: (id: string) => void; paused: boolean }) {
  const { lang, t } = useI18n();

  const cards: SpectraCard[] = useMemo(() => examples.map((e, i) => ({
    key: e.id,
    c1: `color-mix(in oklab, ${GLOW[i % GLOW.length]} 48%, #2c3a34)`,
    c2: "#1f2a25",
    glow: GLOW[i % GLOW.length],
    label: exampleText(e.id, "title", e.title),
    content: (
      <>
        <span className="self-start rounded-lg border border-hair bg-white/12 px-2 py-1 font-mono text-[11px] tracking-widest">{formatNumber(i + 1, 0, 2)}</span>
        <span className="flex flex-col gap-2">
          {e.task in TASK_LABEL && <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/70">{TASK_LABEL[e.task]}</span>}
          <span className="text-[22px] font-semibold leading-tight" dir="auto">{exampleText(e.id, "title", e.title)}</span>
          <span className="text-[13px] leading-snug text-white/75" dir="auto">{exampleText(e.id, "about", e.about)}</span>
        </span>
      </>
    ),
  })), [examples, lang]);

  if (!cards.length) return <div className="h-[520px]" />;
  return (
    <SpectraDeck
      cards={cards}
      paused={paused}
      onOpen={(i) => onPick(examples[i].id)}
      caption={(i) => <h3 className="m-0 flex min-h-[2.5em] items-center text-[22px] font-normal leading-tight tracking-tight" dir="auto">{examples[i] && exampleText(examples[i].id, "title", examples[i].title)}</h3>}
      cta={t("examples.cta")}
    />
  );
}
