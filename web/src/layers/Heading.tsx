import TextEngine from "spring-text-engine";
import type { ReactNode } from "react";

// GetLayers Text Animations, "Rise & Settle": letters lift and spring into place one after another.
export function Heading({ as = "h1", className, children }: { as?: "h1" | "h2" | "h3"; className?: string; children: ReactNode }) {
  return (
    <TextEngine
      tag={as}
      mode="once"
      overflow
      letterOut={{ opacity: 0, y: 24 }}
      letterIn={{ opacity: 1, y: 0 }}
      letterConfig={{ tension: 220, friction: 22 }}
      letterStagger={30}
      className={className}
    >
      {children}
    </TextEngine>
  );
}
