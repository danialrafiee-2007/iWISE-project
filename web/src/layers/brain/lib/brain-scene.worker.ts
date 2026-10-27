// 📖 Docs: obsidian/frontend/components/brain.md

/**
 * The whole particle brain, rendered off the main thread (phones and tablets).
 *
 * The page hands this worker its `<canvas>` as an OffscreenCanvas
 * (`BrainStage`) and from then on only posts what changed: the canvas size,
 * the scroll story's progress, the loader's hand-off, the pointer, visibility.
 * Everything else happens here — three.js evaluating, the renderer and its
 * composers, loading the model, the shader prewarm, and every frame, on this
 * worker's own animation loop. On a throttled phone that work was the page's
 * long tasks (three/R3F evaluation, the renderer set-up, the first frame).
 *
 * It draws the same frame as the page's R3F scene: both run `brain-core.ts`
 * (uniforms, pipeline, prewarm, camera rig, scene step), and this file only
 * recreates what R3F's `<Canvas>` provided (renderer defaults, camera, clock,
 * the frame order: camera rig → scene → composers).
 */
import {
  ACESFilmicToneMapping,
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Clock,
  Color,
  DefaultLoadingManager,
  Fog,
  Group,
  PerspectiveCamera,
  Points,
  SRGBColorSpace,
  Scene,
  ShaderMaterial,
  Vector3,
  WebGLRenderer,
} from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { type BrainConfig } from "../config";
import { STORY_KEYFRAMES } from "../story/story-keyframes";
import {
  REVEAL_START_Z,
  createPipeline,
  makeAmbientUniforms,
  makeBrainUniforms,
  makeCameraRig,
  makeSceneStep,
  prewarmPipeline,
  renderPipeline,
  sizePipeline,
  stepCameraRig,
  stepScene,
  type PipelineSync,
} from "./brain-core";
import type { BrainGeometryRequest, BrainGeometryResult } from "./brain-geometry.worker";
import { AMBIENT_FRAGMENT, AMBIENT_VERTEX, BRAIN_FRAGMENT, BRAIN_VERTEX } from "./shaders";
import { centerAndScale, computeOcclusion, gatherTriangles, makeAmbientBuffers, makeSeeds, sampleSurface } from "./sampling";

// ─── Messages ────────────────────────────────────────────────────────────────

export interface SceneSize {
  /** CSS pixels. */
  width: number;
  height: number;
  dpr: number;
}

export type ToSceneWorker =
  | ({
      type: "init";
      canvas: OffscreenCanvas;
      config: BrainConfig;
      reduced: boolean;
      progress: number;
      entered: boolean;
    } & SceneSize)
  | ({ type: "size" } & SceneSize)
  | { type: "story"; progress?: number; entered?: boolean }
  | { type: "pointer"; x: number; y: number }
  | { type: "pointerout" }
  | { type: "visible"; visible: boolean }
  | { type: "split"; open: boolean }
  | { type: "piece"; index: number };

/** Where the brain stands on the canvas, in NDC (x right, y up): its centre and the centre of each of its four parts
 *  (0 upper left, 1 upper right, 2 lower left, 3 lower right, before any mirroring). */
export interface BrainLayout {
  centre: [number, number];
  pieces: [number, number][];
}

export type FromSceneWorker =
  | { type: "progress"; active: boolean; progress: number }
  | { type: "ready" }
  | { type: "error"; message: string }
  | { type: "layout"; layout: BrainLayout | null };

const post = (message: FromSceneWorker) => (self as unknown as Worker).postMessage(message);

// ─── State ───────────────────────────────────────────────────────────────────

interface Stage {
  gl: WebGLRenderer;
  scene: Scene;
  camera: PerspectiveCamera;
  group: Group;
  pipeline: ReturnType<typeof createPipeline>;
  brainUniforms: ReturnType<typeof makeBrainUniforms>;
  ambientUniforms: ReturnType<typeof makeAmbientUniforms>;
  brainMaterial: ShaderMaterial | null;
  ambientMaterial: ShaderMaterial;
  size: SceneSize;
  config: BrainConfig;
  reduced: boolean;
  progress: number;
  entered: boolean;
  warm: boolean;
  visible: boolean;
  clock: Clock;
  rig: ReturnType<typeof makeCameraRig>;
  step: ReturnType<typeof makeSceneStep>;
  sync: PipelineSync;
  open: Opening;
}

// ─── Opening into four (Truth Guardian) ─────────────────────────────────────

/**
 * A click on the brain opens it: it comes a little toward the viewer and parts into four, one per challenge input
 * (the page names them). The page says which part the pointer is on; this side eases the motion and reports where
 * the brain and its parts stand on the canvas, so the page can place their names and its pointer tests.
 */
const SPLIT = { forward: 0.45, rate: 4 };

interface Opening {
  target: number;
  amount: number;
  piece: number;
  lift: number;
  /** Each part's centre on the brain's front face, in model space (from the sampled surface). */
  centres: Vector3[];
  lastKey: string;
}

const makeOpening = (): Opening => ({ target: 0, amount: 0, piece: -1, lift: 0, centres: [], lastKey: "" });

const _point = new Vector3();
const _side = new Vector3();

/** The parts' centres and the cut height, from the surface points: the cut is at their mean height, each centre the
 *  mean of the part's points that face the viewer. */
const measureParts = (s: Stage, positions: Float32Array) => {
  let sumY = 0;
  const n = positions.length / 3;
  for (let i = 0; i < positions.length; i += 3) sumY += positions[i + 1];
  const cut = sumY / Math.max(1, n);
  const sums = [0, 1, 2, 3].map(() => [0, 0, 0, 0]);
  for (let i = 0; i < positions.length; i += 3) {
    if (positions[i + 2] < 0) continue;
    const piece = (positions[i + 1] >= cut ? 0 : 2) + (positions[i] >= 0 ? 1 : 0);
    const sum = sums[piece];
    sum[0] += positions[i];
    sum[1] += positions[i + 1];
    sum[2] += positions[i + 2];
    sum[3] += 1;
  }
  s.open.centres = sums.map(([x, y, z, count]) => new Vector3(x, y, z).divideScalar(Math.max(1, count)));
  s.brainUniforms.uSplitY.value = cut;
};

/** Eases the opening, moves the brain, and posts where it stands (only when that changed). */
const stepOpening = (s: Stage, delta: number) => {
  const o = s.open;
  const k = s.reduced ? 1 : 1 - Math.exp(-SPLIT.rate * Math.min(delta, 0.1));
  o.amount += (o.target - o.amount) * k;
  o.lift += ((o.piece >= 0 ? 1 : 0) - o.lift) * Math.min(1, k * 1.5);
  if (Math.abs(o.target - o.amount) < 1e-4) o.amount = o.target;
  const u = s.brainUniforms;
  u.uSplit.value = o.amount;
  u.uPieceLift.value = o.lift;
  if (o.piece >= 0) u.uPiece.value = o.piece;
  s.group.position.z += o.amount * SPLIT.forward;

  // Reported only while the brain stands in its opening frame (or is open): elsewhere in the story it is not clickable.
  if (!o.centres.length || (s.progress > 0.05 && o.amount < 0.001)) {
    if (o.lastKey !== "none") {
      o.lastKey = "none";
      post({ type: "layout", layout: null });
    }
    return;
  }
  s.group.updateMatrixWorld(true);
  s.camera.updateMatrixWorld();
  const project = (point: Vector3): [number, number] => {
    point.project(s.camera);
    return [Math.round(point.x * 1000) / 1000, Math.round(point.y * 1000) / 1000];
  };
  const spread = u.uSplitDist.value as number;
  const centre = project(_point.set(0, 0, 0).applyMatrix4(s.group.matrixWorld));
  const pieces = o.centres.map((c, i) => {
    const right = i % 2 === 1 ? 1 : -1;
    const upper = i < 2 ? 1 : -1;
    const lift = i === u.uPiece.value ? o.lift : 0;
    _side.set(right, upper * 0.85, 0.3).normalize().multiplyScalar(o.amount * spread * (1 + lift * 0.6));
    return project(_point.copy(c).add(_side).applyMatrix4(s.group.matrixWorld));
  });
  const key = `${centre}|${pieces.join("|")}`;
  if (key !== o.lastKey) {
    o.lastKey = key;
    post({ type: "layout", layout: { centre, pieces } });
  }
};

let stage: Stage | null = null;
// Messages that arrive before `init` has built the stage (none in practice).
const early: ToSceneWorker[] = [];

const raf: (cb: () => void) => void =
  typeof self.requestAnimationFrame === "function"
    ? (cb) => self.requestAnimationFrame(cb)
    : (cb) => setTimeout(cb, 16);

// ─── Frame loop ──────────────────────────────────────────────────────────────

/**
 * The scene renders at ~35 fps here (owner, D-030). Drawn on every vsync, the
 * worker's frame stream competed with the page's own frames and the phone
 * scroll test fell from ideal to smooth (1.1–2 % dropped vs 0.3–0.6 %); every
 * other vsync measured at or under the baseline.
 *
 * A time accumulator, not a frame skip, so it holds on 60 and 120 Hz screens
 * alike: a vsync renders only once ≥ 1000/35 ms has built up since the last
 * render. Motion stays time-based — the clock's delta and elapsed time span
 * the whole gap — so everything moves at the same speed, in fewer steps.
 */
const FRAME_INTERVAL = 1000 / 35;
let accumulated = 0;
let lastTick: number | null = null;

const frame = () => {
  const s = stage;
  if (!s) return;
  raf(frame);
  const now = performance.now();
  accumulated += lastTick === null ? FRAME_INTERVAL : now - lastTick;
  lastTick = now;
  if (accumulated < FRAME_INTERVAL) return;
  // Carry the remainder (the average lands on 35 fps), but never a backlog: a
  // long stall renders once, not a burst.
  accumulated = Math.min(accumulated - FRAME_INTERVAL, FRAME_INTERVAL);
  if (!s.visible) {
    // Keep the clock honest across a hidden stretch, as a paused rAF would.
    s.clock.getDelta();
    return;
  }
  draw(s);
};

/** One frame: the camera rig, the scene, the composers. */
const draw = (s: Stage) => {
  const delta = s.clock.getDelta();
  const time = s.clock.elapsedTime;
  const { width, height, dpr } = s.size;

  // R3F's order: the camera rig and the scene (default priority, the rig
  // first — the scene suspends on its model), then the renderer (priority 1).
  stepCameraRig(s.rig, s.camera, s.reduced ? 0 : s.progress, width, height, delta);
  stepScene(
    s.step,
    {
      time,
      width,
      height,
      dpr,
      camera: s.camera,
      config: s.config,
      progress: s.progress,
      entered: s.entered,
      warm: s.warm,
      hasBrain: s.brainMaterial !== null,
      steps: delta * 60,
    },
    s.group,
    s.brainMaterial ? s.brainUniforms : undefined,
    s.ambientUniforms,
  );
  if (s.brainMaterial) stepOpening(s, delta);
  if (s.warm) renderPipeline(s.pipeline, s.config, time, s.sync);
};

// ─── Set-up ──────────────────────────────────────────────────────────────────

/**
 * Re-sizing clears the drawing buffer, so it happens only for a real change
 * and is followed by a frame in the same task: the next commit is a drawn
 * frame, never the cleared buffer (a blank flash on iOS, owner review D-033).
 * The page sends a size only when the scene's box changes, and that box no
 * longer follows the toolbar (`SceneViewport`) — in practice, a rotation.
 */
const resize = (s: Stage, size: SceneSize) => {
  const same = size.width === s.size.width && size.height === s.size.height && size.dpr === s.size.dpr;
  if (same) return;
  s.size = size;
  s.gl.setPixelRatio(size.dpr);
  s.gl.setSize(size.width, size.height, false);
  s.camera.aspect = size.width / Math.max(1, size.height);
  s.camera.updateProjectionMatrix();
  // R3F rebuilds the composers on a resize; resizing them draws the same.
  s.pipeline.bloomPass.resolution.set(size.width, size.height);
  sizePipeline(s.pipeline, size.dpr, size.width, size.height);
  if (s.visible) draw(s);
};

/** The surface sampled on this worker's own thread: the same functions the nested worker runs. */
const sampleHere = ({ tris, count, radius }: BrainGeometryRequest): BrainGeometryResult => {
  const { positions, normals } = sampleSurface(tris, count);
  centerAndScale(positions, 1.45);
  return { positions, normals, occlusion: computeOcclusion(positions, radius), seeds: makeSeeds(positions.length / 3) };
};

/** The model → triangles here, the surface sampled in a nested worker (as on the page). Where a worker cannot start a
 *  module worker of its own (the desktop app's preview browser could not, and the brain never appeared), the surface
 *  is sampled here instead: still off the page's thread, only a moment later. */
const buildBrain = (s: Stage) => {
  const manager = DefaultLoadingManager;
  manager.onStart = (_url, loaded, total) => post({ type: "progress", active: true, progress: (loaded / total) * 100 });
  manager.onProgress = (_url, loaded, total) =>
    post({ type: "progress", active: true, progress: (loaded / total) * 100 });
  manager.onLoad = () => post({ type: "progress", active: false, progress: 100 });
  manager.onError = () => post({ type: "progress", active: false, progress: 100 });

  new GLTFLoader().load(
    s.config.modelUrl,
    (gltf) => {
      const request = (): BrainGeometryRequest => ({
        tris: gatherTriangles(gltf.scene),
        count: Math.max(100, s.config.surfaceCount),
        radius: s.config.occlusionRadius,
      });
      const done = (result: BrainGeometryResult) => {
        const geom = new BufferGeometry();
        geom.setAttribute("position", new BufferAttribute(result.positions, 3));
        geom.setAttribute("aNormal", new BufferAttribute(result.normals, 3));
        geom.setAttribute("aSeed", new BufferAttribute(result.seeds, 1));
        geom.setAttribute("aOcclusion", new BufferAttribute(result.occlusion, 1));
        const material = new ShaderMaterial({
          uniforms: s.brainUniforms,
          vertexShader: BRAIN_VERTEX,
          fragmentShader: BRAIN_FRAGMENT,
          transparent: true,
          depthWrite: false,
          blending: AdditiveBlending,
        });
        measureParts(s, result.positions);
        const points = new Points(geom, material);
        points.frustumCulled = false;
        // Created after the ambient field, as on the page: both are additive
        // and sort by creation, so they draw in the same order.
        s.group.add(points);
        s.brainMaterial = material;
      };
      // The triangles are handed over (not copied), so the fallback gathers them again from the model.
      const fallback = () => {
        try {
          done(sampleHere(request()));
        } catch (error) {
          post({ type: "error", message: `geometry: ${String(error)}` });
        }
      };
      try {
        const geometry = new Worker(new URL("./brain-geometry.worker.ts", import.meta.url), {
          type: "module",
        });
        geometry.onmessage = (event: MessageEvent<BrainGeometryResult>) => {
          done(event.data);
          geometry.terminate();
        };
        geometry.onerror = () => {
          geometry.terminate();
          fallback();
        };
        const sent = request();
        geometry.postMessage(sent, [sent.tris.buffer]);
      } catch {
        fallback();
      }
    },
    undefined,
    (error) => post({ type: "error", message: `model: ${String(error)}` }),
  );
};

const init = (message: Extract<ToSceneWorker, { type: "init" }>) => {
  const { canvas, config } = message;
  // `<Canvas>`'s defaults: antialias, alpha, high-performance, ACES tone
  // mapping, sRGB output, `dpr={[1, 2]}` (clamped by the page).
  const gl = new WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
    powerPreference: "high-performance",
  });
  gl.toneMapping = ACESFilmicToneMapping;
  gl.outputColorSpace = SRGBColorSpace;

  const scene = new Scene();
  scene.background = new Color(config.backgroundColor);
  scene.fog = new Fog(config.backgroundColor, 0, 18);

  const camera = new PerspectiveCamera(config.cameraFov, message.width / Math.max(1, message.height), 0.1, 80);
  camera.position.set(...STORY_KEYFRAMES[0].position);
  camera.lookAt(0, 0, 0);

  const group = new Group();
  group.position.set(0, 0, REVEAL_START_Z);
  scene.add(group);

  const brainUniforms = makeBrainUniforms();
  const ambientUniforms = makeAmbientUniforms();
  const { positions, dirs, seeds } = makeAmbientBuffers(Math.max(0, config.ambientCount));
  const ambientGeometry = new BufferGeometry();
  ambientGeometry.setAttribute("position", new BufferAttribute(positions, 3));
  ambientGeometry.setAttribute("aDir", new BufferAttribute(dirs, 3));
  ambientGeometry.setAttribute("aSeed", new BufferAttribute(seeds, 1));
  const ambientMaterial = new ShaderMaterial({
    uniforms: ambientUniforms,
    vertexShader: AMBIENT_VERTEX,
    fragmentShader: AMBIENT_FRAGMENT,
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
  });
  const ambient = new Points(ambientGeometry, ambientMaterial);
  ambient.frustumCulled = false;
  group.add(ambient);

  gl.setPixelRatio(message.dpr);
  gl.setSize(message.width, message.height, false);
  const pipeline = createPipeline(gl, scene, camera, message.width, message.height);
  sizePipeline(pipeline, message.dpr, message.width, message.height);

  const s: Stage = {
    gl,
    scene,
    camera,
    group,
    pipeline,
    brainUniforms,
    ambientUniforms,
    brainMaterial: null,
    ambientMaterial,
    size: { width: message.width, height: message.height, dpr: message.dpr },
    config,
    reduced: message.reduced,
    progress: message.progress,
    entered: message.entered,
    warm: false,
    visible: true,
    clock: new Clock(),
    rig: makeCameraRig(),
    step: makeSceneStep(),
    sync: { corners: null },
    open: makeOpening(),
  };
  stage = s;

  buildBrain(s);
  const { done } = prewarmPipeline(gl, scene, camera, pipeline, () => stage === s);
  void done.then((ok) => {
    if (ok) s.warm = true;
  });

  early.splice(0).forEach(handle);
  post({ type: "ready" });
  raf(frame);
};

const handle = (message: ToSceneWorker) => {
  if (message.type === "init") {
    try {
      init(message);
    } catch (error) {
      post({ type: "error", message: String(error) });
    }
    return;
  }
  const s = stage;
  if (!s) {
    early.push(message);
    return;
  }
  switch (message.type) {
    case "size":
      resize(s, message);
      break;
    case "story":
      if (message.progress !== undefined) s.progress = message.progress;
      if (message.entered !== undefined) s.entered = message.entered;
      break;
    case "pointer":
      s.step.pointerNDC.set(message.x, message.y);
      s.step.cursorTarget = 1;
      break;
    case "pointerout":
      s.step.cursorTarget = 0;
      break;
    case "visible":
      s.visible = message.visible;
      break;
    case "split":
      s.open.target = message.open ? 1 : 0;
      if (!message.open) s.open.piece = -1;
      break;
    case "piece":
      s.open.piece = message.index;
      break;
  }
};

self.onmessage = (event: MessageEvent<ToSceneWorker>) => handle(event.data);
