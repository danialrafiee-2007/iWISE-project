/**
 * The "Neural Monitor" particle brain (src/components/brain of the template), recoloured from blue to the app's
 * teal through these colour keys only; everything else is as shipped.
 *
 * Tunable parameters for the particle-brain scene. These are scene *content*
 * (colours, counts, speeds), not CSS styling — they are passed into the WebGL
 * shaders, so they live here as a typed config object rather than as design
 * tokens. Ported from the original `scenes/brain-particles.html` prototype.
 */
export interface BrainConfig {
  /** Path to the GLB the surface particles are sampled from. */
  modelUrl: string;
  /** Cool / warm hue endpoints for the Y-axis brain tint. */
  brainCool: string;
  brainWarm: string;
  /** Silhouette colour (particles at the edge of the projected brain). */
  edgeColor: string;
  /** Colour particles fade toward near the projected centre. */
  centerColor: string;
  /** Screen-space radius of the centre region (NDC). */
  centerRadius: number;
  /** Falloff exponent for the edge→centre colour blend. */
  centerFalloff: number;
  /** Colour of the white-hot synapse flashes. */
  synapseColor: string;
  /** Colour of the drifting ambient particle cloud. */
  ambientColor: string;
  /** Base point size for brain / ambient particles. */
  particleSize: number;
  ambientSize: number;
  /** How many ambient cloud particles to spawn. */
  ambientCount: number;
  /** Ambient drift speed and travel range. */
  ambientSpeed: number;
  ambientRange: number;
  /** How many particles to sample on the brain surface. */
  surfaceCount: number;
  /** Idle auto-rotation speed (radians/sec, negative = clockwise). */
  rotationSpeed: number;
  /** Fraction of particles that fire synapse flashes. */
  synapseRate: number;
  /** Speed of the continuous tangential "flow" wander of the brain particles. */
  flowSpeed: number;
  /** Amplitude of that flow (model space) — kept small so the shape stays read-able. */
  flowAmount: number;
  /** Overall additive glow multiplier on the brain. */
  glowStrength: number;
  /** How much back-facing particles darken (0..1). */
  depthDarkness: number;
  /** Deepest colour — particles in folds/crevices (sulci) fade toward this. */
  deepColor: string;
  /** How strongly cavity occlusion darkens toward `deepColor` (0..1). */
  occlusionStrength: number;
  /** Neighbour radius used to bake per-particle cavity occlusion (model space). */
  occlusionRadius: number;
  /** Colour a highlighted brain region takes on when its chapter is active. */
  highlightColor: string;
  /** Model-space radius of the region-highlight falloff. */
  highlightRadius: number;
  /** How much the side opposite the active region fades out (0..1). */
  focusFadeStrength: number;
  /** How strongly the rest of the brain darkens toward `deepColor` while a region is active (0..1). */
  isolateStrength: number;
  /** Distance particles fly outward in the finale "blow up" (model space). */
  explodeDistance: number;
  /** Number of star "neuron" nodes revealed inside the brain at the finale. */
  constellationCount: number;
  /** Colour of those constellation nodes + their connecting lines. */
  constellationColor: string;
  /** Colour of the cursor halo that lights up particles under the pointer. */
  cursorColor: string;
  /** Overall intensity of the cursor halo (swell + glow + alpha lift). 0 = off. */
  cursorStrength: number;
  /** Base screen-space radius of the cursor halo (NDC, before distance scaling). */
  cursorRadius: number;
  /** How fast the halo trails the pointer (per-frame lerp, 0..1; higher = snappier). */
  cursorFollow: number;
  /** How fast the effect fades in/out as the pointer enters/leaves (per-frame lerp). */
  cursorFade: number;
  /** Multiplier on the brain's tilt-toward-cursor parallax. 0 = no tilt. */
  cursorParallax: number;
  /** Vertical field of view of the camera, in degrees (the template's was 45; 38 shows the brain 1.2 times larger). */
  cameraFov: number;
  /** Scene background and fog colour (the template's was "#01040e"). The output pass brightens dark values, so
   *  "#010403" shows as a deep forest green. */
  backgroundColor: string;
  /** Corner gradient colours for the warped background. */
  cornerBlue: string;
  cornerOrange: string;
  /** UnrealBloom intensity multiplier on the composited scene. */
  bloomStrength: number;
  /** UnrealBloom spread radius (how far the glow bleeds). */
  bloomRadius: number;
  /** UnrealBloom luminance cutoff — pixels below this don't bloom. Keep at 0 for
   *  temporal stability (no pixels popping in/out across the cutoff). */
  bloomThreshold: number;
}

export const BRAIN_CONFIG: BrainConfig = {
  modelUrl: "/assets/brain/rotten-brain.glb",
  brainCool: "#0a4a4a",
  brainWarm: "#7af0dc",
  edgeColor: "#1fb8a6",
  centerColor: "#000000",
  centerRadius: 0.37,
  centerFalloff: 4,
  synapseColor: "#eafff9",
  ambientColor: "#2b8a7f",
  particleSize: 0.029,
  ambientSize: 0.069,
  ambientCount: 4500,
  ambientSpeed: 0.03,
  ambientRange: 15.5,
  surfaceCount: 140000,
  rotationSpeed: -0.09,
  synapseRate: 0.1,
  flowSpeed: 2.3,
  flowAmount: 0.025,
  glowStrength: 2,
  depthDarkness: 1,
  deepColor: "#010e12",
  occlusionStrength: 0,
  occlusionRadius: 0.05,
  highlightColor: "#14b8a6",
  highlightRadius: 0.6,
  focusFadeStrength: 0.55,
  isolateStrength: 0.88,
  explodeDistance: 5,
  constellationCount: 170,
  constellationColor: "#a8fff0",
  cursorColor: "#000000",
  cursorStrength: 0.74,
  cursorRadius: 0.24,
  cursorFollow: 0.39,
  cursorFade: 0.1,
  cursorParallax: 1,
  // The background in iridology's forest greens, so the landing page's night ground matches the light pages.
  backgroundColor: "#010403",
  cameraFov: 38,
  cornerBlue: "#2f6b52",
  cornerOrange: "#0b1712",
  bloomStrength: 0.69,
  bloomRadius: 0.75,
  bloomThreshold: 0,
};

/**
 * Serialise a config back into the exact `BRAIN_CONFIG` source literal, so the
 * control panel can offer a copy-paste snippet to bake the current look into
 * this file. Strings are quoted, numbers are emitted raw; key order follows the
 * object's own insertion order (i.e. the definition above).
 */
export function serializeBrainConfig(config: BrainConfig): string {
  const body = Object.entries(config)
    .map(([key, value]) =>
      typeof value === "string" ? `  ${key}: ${JSON.stringify(value)},` : `  ${key}: ${value},`,
    )
    .join("\n");
  return `export const BRAIN_CONFIG: BrainConfig = {\n${body}\n};`;
}

/** Render layers — mirrors the original layered-bloom pipeline. */
export const BRAIN_LAYERS = {
  NONE: 0,
  TORUS_SCENE: 1,
  BLOOM_SCENE: 2,
  ENTIRE_SCENE: 3,
} as const;
