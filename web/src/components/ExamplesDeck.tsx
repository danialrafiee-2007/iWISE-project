import { useEffect, useMemo, useState } from "react";
import { formatNumber, useI18n } from "../i18n";
import { SpectraDeck, type SpectraCard } from "../layers/SpectraDeck";
import { api } from "../lib/api";
import { TASK_LABEL } from "../lib/format";
import { useRouter } from "../lib/router";
import type { ExampleBrief } from "../lib/types";

// The written showcase answers as a card deck; choosing one opens it on the Analyze page.

const GLOW = ["#fb7185", "#c4b5fd", "#a78bfa", "#fbbf24", "#34d399", "#60a5fa", "#2dd4bf", "#f472b6", "#fb923c", "#93c5fd", "#5eead4", "#e879f9"];

export default function ExamplesDeck({ onPick }: { onPick: () => void }) {
  const { lang, t } = useI18n();
  const { navigate } = useRouter();
  const [examples, setExamples] = useState<ExampleBrief[]>([]);

  useEffect(() => {
    api.examples().then((e) => setExamples(e.answers.filter((x) => x.origin.startsWith("written")))).catch(() => {});
  }, []);

  const cards: SpectraCard[] = useMemo(() => examples.map((e, i) => ({
    key: e.id,
    c1: `color-mix(in oklab, ${GLOW[i % GLOW.length]} 48%, #2c3a34)`,
    c2: "#1f2a25",
    glow: GLOW[i % GLOW.length],
    label: e.title,
    content: (
      <>
        <span className="self-start rounded-lg border border-hair bg-white/12 px-2 py-1 font-mono text-[11px] tracking-widest">{formatNumber(i + 1, 0, 2)}</span>
        <span className="flex flex-col gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/70">{TASK_LABEL[e.task] ?? e.task}</span>
          <span className="text-[22px] font-semibold leading-tight" dir="auto">{e.title}</span>
          <span className="text-[13px] leading-snug text-white/75" dir="auto">{e.about}</span>
        </span>
      </>
    ),
  })), [examples, lang]);

  if (!cards.length) return <div className="h-[440px]" />;
  return (
    <SpectraDeck
      cards={cards}
      onOpen={(i) => {
        navigate(`/analyze?example=${encodeURIComponent(examples[i].id)}`);
        onPick();
      }}
      caption={(i) => <h3 className="m-0 text-[28px] font-normal tracking-tight" dir="auto">{examples[i]?.title}</h3>}
      cta={t("examples.cta")}
    />
  );
}
