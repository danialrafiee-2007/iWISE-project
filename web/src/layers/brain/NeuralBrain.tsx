import { useEffect, useRef, useState } from "react";
import { BRAIN_CONFIG } from "./config";
import type { FromSceneWorker, SceneSize, ToSceneWorker } from "./lib/brain-scene.worker";

// GetLayers "Neural Monitor" particle brain, from the template's worker path (BrainStage): the page keeps only a
// <canvas>, whose control goes to brain-scene.worker.ts as an OffscreenCanvas; three.js, the model and the frame loop
// live in the worker. Where a worker cannot draw, the template's still image is shown instead. `progress` (0..1) flies
// the camera along the story keyframes; `paused` stops drawing; `mirror` says the page shows the canvas mirrored.

const sizeOf = (canvas: HTMLCanvasElement): SceneSize => ({
  width: Math.max(1, canvas.clientWidth),
  height: Math.max(1, canvas.clientHeight),
  dpr: Math.min(Math.max(window.devicePixelRatio || 1, 1), 2),
});

const supported = () => typeof OffscreenCanvas !== "undefined" && typeof Worker !== "undefined" && "transferControlToOffscreen" in HTMLCanvasElement.prototype;

export function NeuralBrain({ progress, paused = false, mirror = false, className = "" }: { progress: number; paused?: boolean; mirror?: boolean; className?: string }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const mirrorRef = useRef(mirror);
  const workerRef = useRef<Worker | null>(null);
  const [failed, setFailed] = useState(!supported());
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const box = boxRef.current;
    if (failed || !box) return;
    const canvas = document.createElement("canvas");
    canvas.className = "block h-full w-full";
    box.appendChild(canvas);
    let worker: Worker;
    try {
      const offscreen = canvas.transferControlToOffscreen();
      worker = new Worker(new URL("./lib/brain-scene.worker.ts", import.meta.url), { type: "module" });
      const send = (message: ToSceneWorker, transfer: Transferable[] = []) => worker.postMessage(message, transfer);
      worker.onmessage = (event: MessageEvent<FromSceneWorker>) => {
        if (event.data.type === "error") setFailed(true);
        if (event.data.type === "progress" && !event.data.active) setLoaded(true);
      };
      worker.onerror = () => setFailed(true);
      const size = sizeOf(canvas);
      send({ type: "init", canvas: offscreen, config: BRAIN_CONFIG, reduced: window.matchMedia("(prefers-reduced-motion: reduce)").matches, progress: 0, entered: true, ...size }, [offscreen]);
      workerRef.current = worker;
    } catch {
      canvas.remove();
      setFailed(true);
      return;
    }
    const observer = new ResizeObserver(() => worker.postMessage({ type: "size", ...sizeOf(canvas) } satisfies ToSceneWorker));
    observer.observe(canvas);
    // Measured on the canvas, which the page may shift or mirror, so the cursor halo stays under the pointer.
    const onMove = (e: PointerEvent) => {
      const box = canvas.getBoundingClientRect();
      const x = ((e.clientX - box.left) / Math.max(1, box.width)) * 2 - 1;
      worker.postMessage({ type: "pointer", x: mirrorRef.current ? -x : x, y: -(((e.clientY - box.top) / Math.max(1, box.height)) * 2 - 1) } satisfies ToSceneWorker);
    };
    const onOut = () => worker.postMessage({ type: "pointerout" } satisfies ToSceneWorker);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.documentElement.addEventListener("pointerleave", onOut);
    return () => {
      observer.disconnect();
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onOut);
      worker.terminate();
      workerRef.current = null;
      canvas.remove();
    };
  }, [failed]);

  useEffect(() => {
    mirrorRef.current = mirror;
  }, [mirror]);

  useEffect(() => {
    workerRef.current?.postMessage({ type: "story", progress } satisfies ToSceneWorker);
  }, [progress]);

  useEffect(() => {
    const send = () => workerRef.current?.postMessage({ type: "visible", visible: !paused && !document.hidden } satisfies ToSceneWorker);
    send();
    document.addEventListener("visibilitychange", send);
    return () => document.removeEventListener("visibilitychange", send);
  }, [paused]);

  if (failed) {
    return <img src="/assets/robot/brain-desktop.webp" alt="" aria-hidden="true" className={`h-full w-full object-cover object-right opacity-80 ${className}`} />;
  }
  return <div ref={boxRef} aria-hidden="true" className={`h-full w-full transition-opacity duration-1000 ${loaded ? "opacity-100" : "opacity-0"} ${className}`} />;
}
