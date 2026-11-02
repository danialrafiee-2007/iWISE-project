import TextEngine from "spring-text-engine";
import type { ReactNode } from "react";
import { useI18n } from "../i18n";

// "Rise & Settle" from the Text Animations tool (docs/CREDITS.md): letters lift and spring into place one after another. Persian and Arabic
// letters join one another, so animating them one by one would break the words apart: there the heading fades in whole.
// A "\n" in the text starts a new line (the landing slogan puts each sentence on its own line).
export function Heading({ as = "h1", className, children }: { as?: "h1" | "h2" | "h3"; className?: string; children: ReactNode }) {
  const { lang, dir } = useI18n();
  const Tag = as;
  const lines = typeof children === "string" ? children.split("\n") : null;
  if (dir === "rtl") {
    return (
      <Tag key={lang} className={`heading-fade ${className ?? ""}`}>
        {lines && lines.length > 1 ? lines.map((line, i) => <span key={i} className="block">{line}</span>) : children}
      </Tag>
    );
  }
  const engine = (text: ReactNode, tag: "h1" | "h2" | "h3" | "span", extra: { className?: string; delayIn?: number } = {}) => (
    <TextEngine
      key={`${lang}:${String(text)}`}
      tag={tag}
      mode="once"
      overflow
      letterOut={{ opacity: 0, y: 24 }}
      letterIn={{ opacity: 1, y: 0 }}
      letterConfig={{ tension: 220, friction: 22 }}
      letterStagger={30}
      {...extra}
    >
      {text}
    </TextEngine>
  );
  if (lines && lines.length > 1) {
    return <Tag className={className}>{lines.map((line, i) => engine(line, "span", { delayIn: i * 260 }))}</Tag>;
  }
  return engine(children, as, { className });
}
