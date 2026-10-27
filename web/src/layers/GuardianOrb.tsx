import { createOrb, createOrbTheme, type OrbController, type OrbState } from "orbloom";
import { useEffect, useRef } from "react";
import { useI18n, type MessageKey } from "../i18n";
import type { Mood } from "../lib/workspace";

// GetLayers Orb Studio, "core-teal-01" structure with the shipped teal palette; red and amber share its structure.
const shared = {
  preset: "core-teal-01",
  seed: 1,
  appearance: { intensity: 0.95, detail: 0.8, glow: 0.9, glass: 0.35 },
  motion: { speed: 0.8, drift: 0.6 },
  audioResponse: { brightness: 1.2, motion: 0.55, pulse: 0.85 },
} as const;

const THEMES = {
  teal: createOrbTheme({ ...shared, id: "tg-orb-teal", colors: { base: "#07262b", interior: "#050809", accents: ["#00c2a8", "#38e1ff", "#ffc65c"] } }),
  red: createOrbTheme({ ...shared, id: "tg-orb-red", colors: { base: "#2b0710", interior: "#090506", accents: ["#fb7185", "#ff9f7a", "#ffc65c"] } }),
  amber: createOrbTheme({ ...shared, id: "tg-orb-amber", colors: { base: "#2b1d07", interior: "#090806", accents: ["#fbbf24", "#fde68a", "#38e1ff"] } }),
};

const LOOK: Record<Mood, { theme: keyof typeof THEMES; state: OrbState; label: MessageKey }> = {
  idle: { theme: "teal", state: "idle", label: "orb.idle" },
  thinking: { theme: "teal", state: "thinking", label: "orb.thinking" },
  grounded: { theme: "teal", state: "success", label: "orb.grounded" },
  uncertain: { theme: "amber", state: "idle", label: "orb.uncertain" },
  hallucinated: { theme: "red", state: "error", label: "orb.hallucinated" },
};

export function GuardianOrb({ mood, diameter = 40, quality = "low" }: { mood: Mood; diameter?: number; quality?: "low" | "balanced" | "high" }) {
  const motionRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const orbRef = useRef<OrbController | null>(null);
  const look = LOOK[mood];
  const { t } = useI18n();

  useEffect(() => {
    const canvas = canvasRef.current;
    const motion = motionRef.current;
    if (!canvas || !motion) return;
    try {
      orbRef.current = createOrb(canvas, { theme: THEMES[LOOK.idle.theme], quality, state: "idle", reducedMotion: "user", onError: () => motion.classList.add("orb-no-webgl") });
    } catch {
      motion.classList.add("orb-no-webgl");
    }
    return () => {
      orbRef.current?.destroy();
      orbRef.current = null;
    };
  }, [quality]);

  useEffect(() => {
    const orb = orbRef.current;
    const motion = motionRef.current;
    const theme = THEMES[look.theme];
    if (motion) {
      const m = theme.ambientMotion;
      motion.dataset.ambientMotion = String(m.enabled);
      motion.style.setProperty("--orb-motion-distance", `${-m.verticalTravel}px`);
      motion.style.setProperty("--orb-motion-scale", String(m.scale));
      motion.style.setProperty("--orb-motion-duration", `${m.durationSeconds}s`);
      motion.style.setProperty("--orb-motion-delay", `${m.delaySeconds}s`);
    }
    if (!orb) return;
    orb.setTheme(theme);
    orb.setState(look.state);
  }, [look.theme, look.state]);

  return (
    <div ref={motionRef} className="orb-motion" style={{ ["--orb-diameter" as string]: `${diameter}px` }} title={t(look.label)}>
      <div className="orb-shell">
        <div className="orb-clip">
          <canvas ref={canvasRef} className="orb-canvas" aria-label={t(look.label)} role="img" />
          <div className="orb-fallback" aria-hidden="true" />
        </div>
        <div className="orb-chrome" aria-hidden="true" />
      </div>
    </div>
  );
}
