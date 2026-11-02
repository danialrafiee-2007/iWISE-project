import { useEffect, useRef, useState } from "react";
import { BRAIN_CONFIG } from "./config";
import type { BrainLayout, FromSceneWorker, SceneSize, ToSceneWorker } from "./lib/brain-scene.worker";

/** Where the brain stands on the screen, in CSS pixels from the window's top left: its centre, the centre of each of
 *  its three parts (indexed as in the worker: 0 upper left, 1 upper right, 2 below on the unmirrored brain), where a
 *  part's name goes, and the crack cells on its front, the nearest of which tells which part a point is on. */
export interface BrainSpot {
  x: number;
  y: number;
  pieces: { x: number; y: number }[];
  cells: { x: number; y: number; piece: number }[];
}

const toScreen = (layout: BrainLayout, canvas: HTMLCanvasElement, mirror: boolean): BrainSpot => {
  const box = canvas.getBoundingClientRect();
  const at = ([x, y]: [number, number]) => ({ x: box.left + (((mirror ? -x : x) + 1) / 2) * box.width, y: box.top + ((1 - y) / 2) * box.height });
  return { ...at(layout.centre), pieces: layout.pieces.map(at), cells: layout.cells.map(([x, y, piece]) => ({ ...at([x, y]), piece })) };
};

// GetLayers "Neural Monitor" particle brain, from the template's worker path (BrainStage): the page keeps only a
// <canvas>, whose control goes to brain-scene.worker.ts as an OffscreenCanvas; three.js, the model and the frame loop
// live in the worker. Where a worker cannot draw, the template's still image is shown instead. `progress` (0..1) flies
// the camera along the story keyframes; `paused` stops drawing; `mirror` says the page shows the canvas mirrored.
// `open` cracks the brain into three and `piece` lights one of them; `onSpot` hears where the brain and its parts stand.

const sizeOf = (canvas: HTMLCanvasElement): SceneSize => ({
  width: Math.max(1, canvas.clientWidth),
  height: Math.max(1, canvas.clientHeight),
  dpr: Math.min(Math.max(window.devicePixelRatio || 1, 1), 2),
});

const supported = () => typeof OffscreenCanvas !== "undefined" && typeof Worker !== "undefined" && "transferControlToOffscreen" in HTMLCanvasElement.prototype;

export function NeuralBrain({ progress, paused = false, mirror = false, open = false, piece = -1, onSpot, className = "" }: {
  progress: number; paused?: boolean; mirror?: boolean; open?: boolean; piece?: number; onSpot?: (spot: BrainSpot | null) => void; className?: string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const mirrorRef = useRef(mirror);
  const spotRef = useRef(onSpot);
  spotRef.current = onSpot;
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
        if (event.data.type === "layout") spotRef.current?.(event.data.layout && toScreen(event.data.layout, canvas, mirrorRef.current));
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
    workerRef.current?.postMessage({ type: "split", open } satisfies ToSceneWorker);
  }, [open]);

  useEffect(() => {
    workerRef.current?.postMessage({ type: "piece", index: piece } satisfies ToSceneWorker);
  }, [piece]);

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
