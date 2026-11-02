import { useEffect, useRef, useState } from "react";
import { useWorkspace } from "../lib/workspace";

// A purchased three.js scene (public/layers/<name>.html, made offline by scripts/vendor-layers.mjs) in a same-origin
// frame. The frame isolates the scene's globals and render loop; messages pause it while the models run, update its
// CONFIG, or pick Signal Array's lamp. Decorative: hidden from assistive technology and from the tab order.

export type SceneName = "glass-halo" | "halftone-iris" | "lumen-grid" | "signal-array";

export function SceneFrame({
  name,
  paused,
  signal,
  config,
  interactive = true,
  eager = false,
  delay = 0,
  className = "",
}: {
  name: SceneName;
  paused?: boolean;
  signal?: "red" | "amber" | "green";
  config?: Record<string, string | number>;
  interactive?: boolean;
  eager?: boolean;
  /** Milliseconds to wait before loading: starting a scene holds the page for a moment, so let what is moving finish. */
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [waited, setWaited] = useState(delay === 0);
  const { busy, reducedMotion } = useWorkspace();
  const stopped = paused ?? (busy || reducedMotion);

  useEffect(() => {
    if (waited) return;
    const timer = window.setTimeout(() => setWaited(true), delay);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin === window.location.origin && e.source === ref.current?.contentWindow && e.data?.tg === 1 && e.data.ready) setReady(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const configKey = JSON.stringify(config ?? null);
  useEffect(() => {
    if (!ready) return;
    ref.current?.contentWindow?.postMessage({ tg: 1, paused: stopped, ...(signal ? { signal } : {}), ...(config ? { config } : {}) }, window.location.origin);
  }, [ready, stopped, signal, configKey]);

  return (
    <iframe
      ref={ref}
      src={waited ? `/layers/${name}.html` : undefined}
      title=""
      aria-hidden="true"
      tabIndex={-1}
      loading={eager ? "eager" : "lazy"}
      className={`block h-full w-full border-0 transition-opacity duration-700 ${ready ? "opacity-100" : "opacity-0"} ${interactive ? "" : "pointer-events-none"} ${className}`}
    />
  );
}
