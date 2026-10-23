// 📖 Docs: obsidian/frontend/components/brain.md

/**
 * The particle brain's frame — plain three.js, no React, no DOM.
 *
 * Two hosts run it: the page's R3F scene (`BrainCanvas` → `BrainScene`,
 * `BrainCameraRig`, `BrainRenderer`) on desktop and as the fallback, and the
 * scene worker (`brain-scene.worker.ts`) on phones and tablets, where the whole
 * scene renders to an OffscreenCanvas off the main thread. Both call the same
 * functions here — the uniforms, the composer pipeline and its prewarm, the
 * camera rig and the per-frame scene update — so the two draw the same frame.
 * They were lifted out of those components unchanged.
 */
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  Points,
  Scene,
  ShaderMaterial,
  Vector2,
  Vector3,
  type Camera,
  type Group,
  type IUniform,
  type Material,
  type WebGLRenderer,
  type WebGLRenderTarget,
} from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { GammaCorrectionShader } from "three/examples/jsm/shaders/GammaCorrectionShader.js";

import { BRAIN_CONFIG, type BrainConfig } from "../config";
import { makeStorySample, sampleStory, type StorySample } from "../story/story-keyframes";
import { hexToVec3 } from "./sampling";
import { BRAIN_FRAGMENT, BRAIN_VERTEX, FINAL_FRAGMENT, FINAL_VERTEX } from "./shaders";

export type Uniforms = Record<string, IUniform>;

// ─── Uniforms ────────────────────────────────────────────────────────────────

export const makeBrainUniforms = (): Uniforms => ({
  iTime: { value: 0 },
  iAlpha: { value: 0 },
  iResolutionY: { value: 720 },
  uCool: { value: hexToVec3(BRAIN_CONFIG.brainCool) },
  uWarm: { value: hexToVec3(BRAIN_CONFIG.brainWarm) },
  uEdgeColor: { value: hexToVec3(BRAIN_CONFIG.edgeColor) },
  uCenterColor: { value: hexToVec3(BRAIN_CONFIG.centerColor) },
  uCenterRadius: { value: BRAIN_CONFIG.centerRadius },
  uCenterFalloff: { value: BRAIN_CONFIG.centerFalloff },
  uSynapse: { value: hexToVec3(BRAIN_CONFIG.synapseColor) },
  uSize: { value: BRAIN_CONFIG.particleSize },
  uSynapseRate: { value: BRAIN_CONFIG.synapseRate },
  uFlowSpeed: { value: BRAIN_CONFIG.flowSpeed },
  uFlowAmount: { value: BRAIN_CONFIG.flowAmount },
  uGlow: { value: BRAIN_CONFIG.glowStrength },
  uDepthDarkness: { value: BRAIN_CONFIG.depthDarkness },
  uDeepColor: { value: hexToVec3(BRAIN_CONFIG.deepColor) },
  uOcclusionStrength: { value: BRAIN_CONFIG.occlusionStrength },
  uHighlightColor: { value: hexToVec3(BRAIN_CONFIG.highlightColor) },
  uHighlightPos: { value: new Vector3(0, 0, 0) },
  uHighlightRadius: { value: BRAIN_CONFIG.highlightRadius },
  uHighlightStrength: { value: 0 },
  uFocusFadeStrength: { value: BRAIN_CONFIG.focusFadeStrength },
  uIsolateStrength: { value: BRAIN_CONFIG.isolateStrength },
  uExplode: { value: 0 },
  uExplodeDist: { value: BRAIN_CONFIG.explodeDistance },
  // Cursor halo (driven by the scene step from pointer events). Starts off-screen.
  uMouse: { value: new Vector2(-10, -10) },
  uCursor: { value: 0 },
  uAspect: { value: 1 },
  uCursorRadius: { value: BRAIN_CONFIG.cursorRadius },
  uCursorColor: { value: hexToVec3(BRAIN_CONFIG.cursorColor) },
  uCursorStrength: { value: BRAIN_CONFIG.cursorStrength },
});

export const makeAmbientUniforms = (): Uniforms => ({
  iTime: { value: 0 },
  iAlpha: { value: 0 },
  iResolutionY: { value: 720 },
  uColor: { value: hexToVec3(BRAIN_CONFIG.ambientColor) },
  uSize: { value: BRAIN_CONFIG.ambientSize },
  uSpeed: { value: BRAIN_CONFIG.ambientSpeed },
  uRange: { value: BRAIN_CONFIG.ambientRange },
});

// ─── Composer pipeline ──────────────────────────────────────────────────────

export interface BrainPipeline {
  sceneComposer: EffectComposer;
  finalComposer: EffectComposer;
  finalPass: ShaderPass;
  bloomPass: UnrealBloomPass;
  gammaPass: ShaderPass;
}

export const createPipeline = (
  gl: WebGLRenderer,
  scene: Scene,
  camera: Camera,
  width: number,
  height: number,
): BrainPipeline => {
  const resolution = new Vector2(width, height);

  const sceneComposer = new EffectComposer(gl);
  sceneComposer.renderToScreen = false;
  sceneComposer.addPass(new RenderPass(scene, camera));
  const gammaPass = new ShaderPass(GammaCorrectionShader);
  sceneComposer.addPass(gammaPass);
  // Real UnrealBloom, applied once to the whole brain. Seeded from config; the
  // three params are then live-synced from the store each frame (see renderPipeline).
  const bloomPass = new UnrealBloomPass(
    resolution,
    BRAIN_CONFIG.bloomStrength,
    BRAIN_CONFIG.bloomRadius,
    BRAIN_CONFIG.bloomThreshold,
  );
  sceneComposer.addPass(bloomPass);

  const finalPass = new ShaderPass({
    uniforms: {
      iTime: { value: 0 },
      tScene: { value: null },
      iCornerBlue: { value: hexToVec3(BRAIN_CONFIG.cornerBlue) },
      iCornerOrange: { value: hexToVec3(BRAIN_CONFIG.cornerOrange) },
    },
    vertexShader: FINAL_VERTEX,
    fragmentShader: FINAL_FRAGMENT,
  });

  const finalComposer = new EffectComposer(gl);
  finalComposer.addPass(finalPass);

  return { sceneComposer, finalComposer, finalPass, bloomPass, gammaPass };
};

/** Keep both composers sized to the canvas (CSS pixels × the renderer's DPR). */
export const sizePipeline = (
  pipeline: BrainPipeline,
  dpr: number,
  width: number,
  height: number,
) => {
  for (const composer of [pipeline.sceneComposer, pipeline.finalComposer]) {
    composer.setPixelRatio(dpr);
    composer.setSize(width, height);
  }
};

export const disposePipeline = (pipeline: BrainPipeline) => {
  pipeline.sceneComposer.dispose();
  pipeline.finalComposer.dispose();
};

/**
 * Prewarm: compile every program the first frames draw before drawing any —
 * the first composer frame used to link ~a dozen programs (the scene's points,
 * gamma, five bloom blurs, high-pass, composite, blend, the final composite)
 * in one ~320 ms task on a throttled phone. Each is compiled against the
 * target it really renders to (a composer buffer, or the screen for the final
 * pass) so nothing re-links later, one program per task, and its uniforms are
 * read in a task of their own. The brain's own material only exists once the
 * surface is sampled, so a twin of it (same shaders and flags → the same cached
 * program) is compiled here too and kept alive until `dispose`.
 *
 * Resolves `true` once every step ran, `false` if `alive()` turned false.
 */
export const prewarmPipeline = (
  gl: WebGLRenderer,
  scene: Scene,
  camera: Camera,
  pipeline: BrainPipeline,
  alive: () => boolean,
): { done: Promise<boolean>; dispose: () => void } => {
  const { sceneComposer, finalPass, bloomPass, gammaPass } = pipeline;
  const quadCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const quad = new PlaneGeometry(2, 2);
  const dot = new BufferGeometry();
  dot.setAttribute("position", new BufferAttribute(new Float32Array(3), 3));
  const brainTwin = new ShaderMaterial({
    vertexShader: BRAIN_VERTEX,
    fragmentShader: BRAIN_FRAGMENT,
    transparent: true,
    depthWrite: false,
    blending: AdditiveBlending,
  });
  const twinScene = new Scene();
  const twin = new Points(dot, brainTwin);
  twin.frustumCulled = false;
  twinScene.add(twin);

  const buffer = sceneComposer.renderTarget1;
  const steps: {
    target: WebGLRenderTarget | null;
    build: () => { root: Scene | Mesh; materials: Material[] };
  }[] = [
    { target: buffer, build: () => ({ root: scene, materials: [] }) },
    { target: buffer, build: () => ({ root: twinScene, materials: [brainTwin] }) },
    ...[
      gammaPass.material,
      bloomPass.materialHighPassFilter,
      ...bloomPass.separableBlurMaterials,
      bloomPass.compositeMaterial,
      bloomPass.blendMaterial,
    ].map((material) => ({
      target: buffer,
      build: () => ({ root: new Mesh(quad, material), materials: [material] }),
    })),
    {
      target: null,
      build: () => ({ root: new Mesh(quad, finalPass.material), materials: [finalPass.material] }),
    },
  ];
  const nextTask = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  const done = (async () => {
    for (const step of steps) {
      if (!alive()) return false;
      const { root, materials } = step.build();
      const previous = gl.getRenderTarget();
      gl.setRenderTarget(step.target);
      const compiled = gl.compileAsync(root, root instanceof Scene ? camera : quadCamera, scene);
      gl.setRenderTarget(previous);
      await compiled;
      await nextTask();
      if (!alive()) return false;
      const all = root instanceof Scene ? [] : materials;
      if (root instanceof Scene) {
        root.traverse((object) => {
          const material = (object as Mesh).material;
          if (material && !Array.isArray(material)) all.push(material);
        });
      }
      for (const material of all) {
        const { currentProgram } = gl.properties.get(material) as {
          currentProgram?: { getUniforms: () => unknown };
        };
        currentProgram?.getUniforms();
      }
      await nextTask();
    }
    return alive();
  })();

  return {
    done,
    dispose: () => {
      quad.dispose();
      dot.dispose();
      // The twin holds the brain's program in the cache until the real
      // material uses it; release it only with the pipeline.
      brainTwin.dispose();
    },
  };
};

/** Last corner colours pushed to a pipeline's composite (identity check). */
export interface PipelineSync {
  corners: { blue: string; orange: string } | null;
}

/** One frame through both composers — the scene + bloom, then the composite. */
export const renderPipeline = (
  p: BrainPipeline,
  config: BrainConfig,
  time: number,
  sync: PipelineSync,
) => {
  const { cornerBlue, cornerOrange, bloomStrength, bloomRadius, bloomThreshold } = config;
  if (sync.corners?.blue !== cornerBlue || sync.corners?.orange !== cornerOrange) {
    sync.corners = { blue: cornerBlue, orange: cornerOrange };
    p.finalPass.uniforms.iCornerBlue.value.copy(hexToVec3(cornerBlue));
    p.finalPass.uniforms.iCornerOrange.value.copy(hexToVec3(cornerOrange));
  }

  // Live-sync bloom — these are plain props on the pass, safe to assign each
  // frame (the pass reads them at render time, no rebuild needed).
  p.bloomPass.strength = bloomStrength;
  p.bloomPass.radius = bloomRadius;
  p.bloomPass.threshold = bloomThreshold;

  p.finalPass.uniforms.iTime.value = time;
  p.sceneComposer.render();
  p.finalPass.uniforms.tScene.value = p.sceneComposer.readBuffer.texture;
  p.finalComposer.render();
};

// ─── Camera rig ──────────────────────────────────────────────────────────────

// Damping rate — higher = the camera catches up to the scroll target faster.
// Frame-rate independent (see `MathUtils.damp`), so it feels identical at any FPS.
const DAMP = 3.2;

export interface CameraRigState {
  sample: StorySample;
  lookAt: Vector3;
  initialised: boolean;
}

export const makeCameraRig = (): CameraRigState => ({
  sample: makeStorySample(),
  lookAt: new Vector3(),
  initialised: false,
});

/**
 * The scroll-driven camera. Every frame it samples the story keyframes at the
 * current scroll `progress` and **damps** the camera position + look-at target
 * toward that sample — one continuous, weighty flythrough. `progress` is 0
 * under reduced motion (the opening framing).
 */
export const stepCameraRig = (
  rig: CameraRigState,
  camera: Camera,
  progress: number,
  width: number,
  height: number,
  delta: number,
) => {
  const s = sampleStory(progress, rig.sample);

  // Responsive framing: on narrow/portrait viewports (tablet/phone), centre the
  // brain (drop the lateral offset) and pull the camera back so it isn't cropped
  // or shoved off-screen by the side-framed keyframes.
  const aspect = width / Math.max(1, height);
  const mobile = Math.max(0, Math.min(1, (1.1 - aspect) / 0.6));
  if (mobile > 0) {
    s.target.x *= 1 - 0.85 * mobile;
    s.target.y *= 1 - 0.4 * mobile;
    s.position.multiplyScalar(1 + 0.4 * mobile);
  }

  if (!rig.initialised) {
    // Snap to the first framing on mount so there is no fly-in from the
    // canvas's default camera position.
    rig.initialised = true;
    camera.position.copy(s.position);
    rig.lookAt.copy(s.target);
    camera.lookAt(rig.lookAt);
    return;
  }

  // Frame-rate-independent exponential damp toward the sampled framing.
  const k = 1 - Math.exp(-DAMP * Math.min(delta, 0.1));
  camera.position.lerp(s.position, k);
  rig.lookAt.lerp(s.target, k);
  camera.lookAt(rig.lookAt);
};

// ─── Scene step ──────────────────────────────────────────────────────────────

const APPEAR_DURATION = 3.0; // seconds
// Reveal: the brain flies in *from the camera* (starts large/near the viewer) and
// settles back to its resting depth while unwinding one full horizontal turn.
export const REVEAL_START_Z = 3.6; // near the opening camera (z≈5.4), not clipping its near plane
const REVEAL_SPIN = Math.PI * 2; // one full 360° rotation about Y, unwound into place

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clampUnit = (v: number) => Math.max(-1, Math.min(1, v));

export interface SceneStepState {
  appearStart: number | null;
  /** Last config applied to the uniforms — identity check (no per-frame colour work). */
  lastConfig: BrainConfig | null;
  storySample: StorySample;
  /** Latest pointer position in NDC; whether the pointer is present (0/1). */
  pointerNDC: Vector2;
  cursorTarget: number;
  parallaxRY: number;
  parallaxRX: number;
}

export const makeSceneStep = (): SceneStepState => ({
  appearStart: null,
  lastConfig: null,
  storySample: makeStorySample(),
  pointerNDC: new Vector2(-10, -10),
  cursorTarget: 0,
  parallaxRY: 0,
  parallaxRX: 0,
});

export interface SceneFrame {
  time: number;
  /** Canvas size in CSS pixels, and its pixel ratio. */
  width: number;
  height: number;
  dpr: number;
  camera: Camera;
  config: BrainConfig;
  progress: number;
  entered: boolean;
  warm: boolean;
  hasBrain: boolean;
  /**
   * How many 60 Hz frames this update stands for — the per-frame easings
   * (cursor halo, parallax) are scaled by it, so a host that renders at a
   * lower rate (the scene worker, ~35 fps) keeps their speed. Omitted: one
   * frame, exactly as on the page.
   */
  steps?: number;
}

/** A per-frame lerp factor `k`, applied over `steps` frames at once. */
const ease = (k: number, steps: number) => (steps === 1 ? k : 1 - Math.pow(1 - k, steps));

/** Push live, user-editable params into the uniforms when the config changes. */
const syncConfig = (state: SceneStepState, config: BrainConfig, brainU?: Uniforms, ambientU?: Uniforms) => {
  // Not applied until the brain's material exists: it mounts only once the
  // surface lands, and a sync spent before then would never re-run.
  if (config === state.lastConfig || !brainU) return;
  state.lastConfig = config;
  brainU.uCool.value.copy(hexToVec3(config.brainCool));
  brainU.uWarm.value.copy(hexToVec3(config.brainWarm));
  brainU.uEdgeColor.value.copy(hexToVec3(config.edgeColor));
  brainU.uCenterColor.value.copy(hexToVec3(config.centerColor));
  brainU.uCenterRadius.value = config.centerRadius;
  brainU.uCenterFalloff.value = config.centerFalloff;
  brainU.uSynapse.value.copy(hexToVec3(config.synapseColor));
  brainU.uSize.value = config.particleSize;
  brainU.uSynapseRate.value = config.synapseRate;
  brainU.uFlowSpeed.value = config.flowSpeed;
  brainU.uFlowAmount.value = config.flowAmount;
  brainU.uGlow.value = config.glowStrength;
  brainU.uDeepColor.value.copy(hexToVec3(config.deepColor));
  brainU.uOcclusionStrength.value = config.occlusionStrength;
  brainU.uCursorColor.value.copy(hexToVec3(config.cursorColor));
  brainU.uCursorStrength.value = config.cursorStrength;
  if (ambientU) {
    ambientU.uColor.value.copy(hexToVec3(config.ambientColor));
    ambientU.uSize.value = config.ambientSize;
    ambientU.uSpeed.value = config.ambientSpeed;
    ambientU.uRange.value = config.ambientRange;
  }
};

/**
 * The brain's per-frame update: the config sync, the entrance (held until the
 * loader hands off, the surface exists and its shaders are compiled), the
 * scroll story's region focus and finale dispersal, the cursor halo, and the
 * group's fly-in + reveal spin + cursor parallax.
 */
export const stepScene = (
  state: SceneStepState,
  frame: SceneFrame,
  group: Group | null,
  brainU: Uniforms | undefined,
  ambientU: Uniforms | undefined,
) => {
  const t = frame.time;
  const steps = frame.steps ?? 1;
  const resY = frame.height * frame.dpr;
  const config = frame.config;
  syncConfig(state, config, brainU, ambientU);

  if (frame.entered && frame.warm && frame.hasBrain && state.appearStart === null) state.appearStart = t;
  const p = state.appearStart === null ? 0 : Math.min(1, (t - state.appearStart) / APPEAR_DURATION);
  const eased = 1 - Math.pow(1 - p, 4); // easeOutQuart — smooth settle

  // Scroll-story focus: each chapter scans a region, the last disperses the brain.
  const story = sampleStory(frame.progress, state.storySample);

  if (brainU) {
    brainU.iTime.value = t;
    brainU.iResolutionY.value = resY;
    brainU.iAlpha.value = eased;
    brainU.uHighlightPos.value.copy(story.region);
    brainU.uHighlightStrength.value = story.highlight;
    // Only the scroll-driven finale disperses the brain — the entrance keeps the
    // brain fully assembled and flies it in instead (see the group block below).
    brainU.uExplode.value = story.explode;
    // Cursor halo: trail the pointer (eased) and fade the effect in/out. Shrink
    // the NDC radius as the camera pulls away.
    brainU.uMouse.value.lerp(state.pointerNDC, ease(config.cursorFollow, steps));
    brainU.uAspect.value = frame.width / Math.max(1, frame.height);
    brainU.uCursor.value +=
      (state.cursorTarget - brainU.uCursor.value) * ease(config.cursorFade, steps);
    const camDist = frame.camera.position.length(); // brain is centred at origin
    const cr = config.cursorRadius;
    brainU.uCursorRadius.value = Math.min(cr * 1.3, Math.max(cr * 0.4, (cr * 4.6) / camDist));
  }
  if (ambientU) {
    ambientU.iTime.value = t;
    ambientU.iResolutionY.value = resY;
    ambientU.iAlpha.value = eased;
  }

  if (group) {
    // Reveal: fly in from near the camera back to the resting depth.
    group.position.z = lerp(REVEAL_START_Z, 0, eased);
    // Subtle cursor parallax — the brain tilts a touch toward the pointer.
    const k = (brainU ? brainU.uCursor.value : 0) * config.cursorParallax;
    const targetRY = clampUnit(state.pointerNDC.x) * 0.12 * k;
    const targetRX = -clampUnit(state.pointerNDC.y) * 0.07 * k;
    state.parallaxRY += (targetRY - state.parallaxRY) * ease(0.04, steps);
    state.parallaxRX += (targetRX - state.parallaxRX) * ease(0.04, steps);
    // Reveal: one full 360° turn that unwinds as the brain settles in.
    const revealSpin = (1 - eased) * REVEAL_SPIN;
    group.rotation.y = state.parallaxRY + revealSpin;
    group.rotation.x = state.parallaxRX;
  }
};
