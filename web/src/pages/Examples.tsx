import { Suspense } from "react";
import { useI18n } from "../i18n";
import { Heading } from "../layers/Heading";
import { lazyPage } from "../lib/lazyPage";

// The ready-made text examples as a card deck, on a page of their own under the AI engine's text tools; choosing a
// card opens it on the Analyze page.

const ExamplesDeck = lazyPage(() => import("../components/ExamplesDeck"));

export default function Examples() {
  const { t } = useI18n();
  return (
    <div className="mx-auto flex max-w-[1320px] flex-col gap-8 px-4 py-14 sm:px-8">
      <header className="flex max-w-3xl flex-col gap-4">
        <span className="eyebrow">{t("nav.text")}</span>
        <Heading className="m-0 text-[clamp(34px,4vw,52px)] font-normal leading-tight tracking-tight">{t("examples.title")}</Heading>
        <p className="m-0 text-lg leading-relaxed text-fog-300">{t("examples.lead")}</p>
      </header>
      <Suspense fallback={<div className="h-[440px]" />}>
        <ExamplesDeck onPick={() => {}} />
      </Suspense>
    </div>
  );
}
