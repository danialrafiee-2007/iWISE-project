/**
 * GLSL shader sources for the particle brain, ported verbatim from
 * `scenes/brain-particles.html`. Three groups:
 *   - ambient cloud (drifting points around the brain)
 *   - brain surface (the sampled point cloud + synapse flashes)
 *   - final composite (warped corner-gradient background + bloom layers)
 */

export const AMBIENT_VERTEX = /* glsl */ `
  attribute vec3 aDir;
  attribute float aSeed;
  uniform float iTime;
  uniform float iResolutionY;
  uniform float uSize;
  uniform float uSpeed;
  uniform float uRange;
  varying float vSeed;
  varying float vPhase;
  void main() {
    vSeed = aSeed;
    float speed = 0.35 + aSeed * 0.9;
    float phase = fract(iTime * uSpeed * speed + aSeed);
    vPhase = phase;
    vec3 dir = normalize(aDir + vec3(1e-5));
    vec3 p = position + dir * phase * uRange;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    float lifeSize = mix(1.0, 0.6, phase);
    gl_PointSize = uSize * lifeSize * (iResolutionY / 720.0) * (200.0 / -mv.z);
  }
`;

export const AMBIENT_FRAGMENT = /* glsl */ `
  uniform vec3 uColor;
  uniform float iAlpha;
  varying float vSeed;
  varying float vPhase;
  void main() {
    vec2 p = gl_PointCoord - 0.5;
    float r = length(p);
    if (r > 0.5) discard;
    float k = smoothstep(0.5, 0.0, r);
    float life = smoothstep(0.0, 0.1, vPhase) * smoothstep(1.0, 0.7, vPhase);
    float twinkle = 0.5 + 0.5 * sin(vSeed * 40.0 + vPhase * 30.0);
    gl_FragColor = vec4(uColor * k * life * (0.4 + 0.6 * twinkle), k * life * iAlpha * 0.6);
  }
`;

export const BRAIN_VERTEX = /* glsl */ `
  attribute float aSeed;
  attribute float aOcclusion;
  attribute vec3 aNormal;
  uniform float iTime;
  uniform float iResolutionY;
  uniform float uSize;
  uniform float uSynapseRate;
  uniform float uCenterRadius;
  uniform float uFlowSpeed;
  uniform float uFlowAmount;
  uniform vec3 uHighlightPos;
  uniform float uHighlightRadius;
  uniform float uHighlightStrength;
  uniform float uExplode;
  uniform float uExplodeDist;
  uniform vec2 uMouse;        // cursor in NDC (-1..1)
  uniform float uCursor;      // cursor effect strength (0..1)
  uniform float uAspect;      // viewport width / height (circular halo)
  uniform float uCursorRadius;// NDC halo radius (shrinks as the brain gets far)
  uniform float uCursorStrength; // overall halo intensity multiplier
  uniform float uSplit;       // Truth Guardian: 0 whole .. 1 cracked open into three parts
  uniform float uSplitDist;   // how far each part moves out
  uniform float uPiece;       // the part under the pointer (0..2), kept while its light fades
  uniform float uPieceLift;   // 0..1, eased: how lit that part is
  uniform float uRiftScale, uRiftDepth, uRiftWidth, uRiftGapWidth, uRiftGapGlow, uRiftFine, uRiftPulse, uRiftCore, uRiftSpread;
  uniform vec3 uRiftSeeds[3];  // each part's seed (x, y): 0 text, 1 sound, 2 images (rift.ts)
  varying float vSeed;
  varying float vSynapse;
  varying float vHemi;
  varying float vDepth;
  varying float vFrontness;
  varying float vCenterness;
  varying float vOcclusion;
  varying float vHighlight;
  varying float vFar;
  varying float vCursor;
  varying float vHot;
  varying float vCold;
  varying float vRift;        // how much crack light this particle gives (0 whole .. bright on a seam)
  varying float vRiftBleed;   // the softer glow around the seams
  varying vec3 vWorldPos;
  // Rift Stone's 3D Voronoi: the two nearest feature distances, and the two nearest cells' centres (scaled space). The
  // hash uses no sin(), which differs between graphics cards: the same cracks on every screen, and rift.ts can follow them.
  vec3 riftHash(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yxz + 33.33);
    return fract((p.xxy + p.yxx) * p.zyx);
  }
  vec2 riftCells(vec3 p, out vec3 cell, out vec3 next) {
    vec3 n = floor(p);
    vec3 f = fract(p);
    float f1 = 9.0, f2 = 9.0;
    cell = n;
    next = n;
    for (int k = -1; k <= 1; k++)
    for (int j = -1; j <= 1; j++)
    for (int i = -1; i <= 1; i++) {
      vec3 g = vec3(float(i), float(j), float(k));
      vec3 o = 0.28 + 0.44 * riftHash(n + g);  // seeds kept near their cell's centre, so no seam blows up
      vec3 r = g + o - f;
      float d = dot(r, r);
      if (d < f1) { f2 = f1; f1 = d; next = cell; cell = n + g + o; } else if (d < f2) { f2 = d; next = n + g + o; }
    }
    return vec2(sqrt(f1), sqrt(f2));
  }
  // The part a cell belongs to, whole: the nearest of the three seeds to its centre (model space).
  float riftPiece(vec3 c) {
    float d0 = distance(c.xy, uRiftSeeds[0].xy), d1 = distance(c.xy, uRiftSeeds[1].xy), d2 = distance(c.xy, uRiftSeeds[2].xy);
    return d0 < d1 ? (d0 < d2 ? 0.0 : 2.0) : (d1 < d2 ? 1.0 : 2.0);
  }
  void main() {
    vSeed = aSeed;
    vOcclusion = aOcclusion;
    vec3 p = position;
    vWorldPos = p;
    vHemi = step(0.0, p.x);
    // Region highlight: 1 at the active anchor, fading out over uHighlightRadius.
    vHighlight = (1.0 - smoothstep(0.0, uHighlightRadius, distance(position, uHighlightPos))) * uHighlightStrength;
    // vFar: 0 on the side facing the active region, 1 on the opposite side —
    // used to fade the far half of the brain to accent the focus.
    vec3 focalDir = normalize(uHighlightPos + vec3(1e-5));
    float align = dot(normalize(position + vec3(1e-5)), focalDir);
    vFar = smoothstep(0.55, -0.35, align);
    vec3 rad = normalize(p + vec3(1e-5));
    float breathe = sin(iTime * 1.6 + aSeed * 6.0) * 0.012;
    p += rad * breathe;
    // Continuous looped flow: each particle traces a full closed circle within
    // its surface tangent plane, so it orbits *around* on the brain's shape
    // (never leaving it) — alive, but the silhouette stays readable.
    vec3 nrm = normalize(aNormal + vec3(1e-5));
    vec3 ref = abs(nrm.y) < 0.95 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 tA = normalize(cross(nrm, ref));
    vec3 tB = cross(nrm, tA);
    float ph = iTime * uFlowSpeed + aSeed * 6.2831;
    vec3 loopDir = tA * cos(ph) + tB * sin(ph);
    p += loopDir * uFlowAmount;
    // Finale: blow the particles outward along a seeded radial direction.
    vec3 exDir = normalize(rad + vec3(sin(aSeed * 41.0), cos(aSeed * 57.0), sin(aSeed * 73.0)) * 0.45);
    p += exDir * uExplode * uExplodeDist;
    // Truth Guardian: opened, the brain cracks like GetLayers' Rift Stone into three unequal parts (0 text, 1 sound,
    // 2 images): every Voronoi cell goes whole to its nearest seed, so the parts break apart along the cells' jagged
    // edges. The cells are long in depth (RIFT_DEPTH in rift.ts), so from the front a crack runs on unbroken over the
    // brain's folds. Particles along an edge between parts stay behind in the gap as the light of a main crack; the
    // cells' other edges are thin cracks inside a part, and the cells drift a little apart as shards (a slight per-shard
    // stagger). Each part moves out toward its seed and a little toward the viewer; the part under the pointer moves
    // further and lights up, the others dim. Only while open.
    float piece = 0.0;
    float gap = 0.0;
    vRift = 0.0;
    vRiftBleed = 0.0;
    if (uSplit > 0.001) {
      vec3 cell, next;
      vec3 depth = vec3(1.0, 1.0, uRiftDepth);
      vec2 v = riftCells(position * uRiftScale * depth, cell, next);
      piece = riftPiece(cell / uRiftScale);
      float between = step(0.5, abs(riftPiece(next / uRiftScale) - piece));  // the nearest edge parts two of them
      float seam = v.y - v.x;
      float rnd = fract(sin(dot(cell, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
      float k = clamp(uSplit * (0.6 + 0.7 * rnd), 0.0, 1.0);
      vec3 outward = normalize(vec3(cell.x, cell.y * 0.7, cell.z / uRiftDepth) / uRiftScale + 1e-4);
      // A wall makes a thin line only where it cuts through a surface turned to the viewer; where the surface runs along
      // it, or edge-on down a fold, a whole stretch would pile up as one white patch, so it stays dark.
      float turned = smoothstep(0.03, 0.25, abs(normalize(normalMatrix * nrm).z));
      float cut = turned * smoothstep(0.1, 0.4, 1.0 - abs(dot(nrm, normalize((next - cell) * depth))));
      // Most of those along an edge gather on the line itself: a thread of light down a gap's middle.
      float near = 1.0 - clamp(seam / uRiftGapWidth, 0.0, 1.0);
      float line = cut * (1.0 - pow(1.0 - near, 3.0));
      gap = between * line;
      p += outward * k * uRiftSpread * (0.55 + 0.9 * rnd) * (1.0 - line);
      float cracks = (1.0 - smoothstep(0.0, uRiftWidth * uRiftScale, seam)) * mix(uRiftFine, 1.0, between) * cut;
      float bleed = (1.0 - smoothstep(0.0, uRiftWidth * uRiftScale * 2.0, seam)) * mix(uRiftFine * 0.4, 1.0, between) * cut;
      float coreMask = mix(1.0, 1.0 - smoothstep(0.0, 1.6, length(position)), uRiftCore);
      float pulse = 1.0 + uRiftPulse * sin(iTime * 1.6 + v.x * 8.0);
      float open = uSplit * (1.0 + uSplit * 0.9);  // the light flares as the parts pull apart
      vRift = max(cracks, gap * gap * uRiftGapGlow) * pulse * coreMask * open;  // hottest on the line itself
      vRiftBleed = bleed * coreMask * open;
    }
    float mine = 1.0 - step(0.5, abs(piece - uPiece));
    vec2 seed = uRiftSeeds[int(piece + 0.5)].xy;
    vec3 apart = normalize(vec3(seed, 0.3 * length(seed)));
    p += apart * (1.0 - gap) * uSplit * uSplitDist * (1.0 + mine * uPieceLift * 0.6);
    vHot = mine * uPieceLift * uSplit;
    vCold = (1.0 - mine) * uPieceLift * uSplit;
    float period = mix(3.0, 9.0, aSeed);
    float firePhase = aSeed * period;
    float ft = mod(iTime + firePhase, period);
    float fire = pow(clamp(1.0 - ft / 0.4, 0.0, 1.0), 2.5);
    if (aSeed > uSynapseRate) fire = 0.0;
    vSynapse = fire;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vec4 centerMv = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
    float rel = centerMv.z - mv.z;
    vFrontness = clamp(rel * 0.6 + 0.5, 0.0, 1.0);
    // The cracks of the far side would show through as a second network; only the side facing the viewer gives light.
    float facing = smoothstep(0.3, 0.6, vFrontness);
    vRift *= facing;
    vRiftBleed *= facing;
    gl_Position = projectionMatrix * mv;
    vec4 centerClip = projectionMatrix * centerMv;
    vec2 centerNDC = centerClip.xy / max(0.0001, centerClip.w);
    vec2 pNDC = gl_Position.xy / max(0.0001, gl_Position.w);
    float screenDist = length(pNDC - centerNDC);
    vCenterness = 1.0 - clamp(screenDist / max(0.05, uCenterRadius), 0.0, 1.0);
    // Cursor halo: particles whose screen position is near the pointer light up
    // and swell, so neurons appear to fire wherever you point. Aspect-corrected
    // so the halo stays circular, not stretched.
    vec2 dMouse = pNDC - uMouse;
    dMouse.x *= uAspect;
    vCursor = (1.0 - smoothstep(0.0, uCursorRadius, length(dMouse))) * uCursor;
    float baseSize = uSize * (iResolutionY / 720.0) * (200.0 / -mv.z);
    gl_PointSize = baseSize * (1.0 + fire * 2.5 + vHighlight * 1.8 + vCursor * 1.3 * uCursorStrength + vHot * 0.25 + vRift * 0.4);
    vDepth = -mv.z;
  }
`;

export const BRAIN_FRAGMENT = /* glsl */ `
  uniform vec3 uCool;
  uniform vec3 uWarm;
  uniform vec3 uEdgeColor;
  uniform vec3 uCenterColor;
  uniform float uCenterFalloff;
  uniform vec3 uSynapse;
  uniform float iAlpha;
  uniform float uGlow;
  uniform float uDepthDarkness;
  uniform vec3 uDeepColor;
  uniform float uOcclusionStrength;
  uniform vec3 uHighlightColor;
  uniform float uHighlightStrength;
  uniform float uFocusFadeStrength;
  uniform float uIsolateStrength;
  uniform float uExplode;
  uniform vec3 uCursorColor;
  uniform float uCursorStrength;
  uniform vec3 uRiftColor;
  uniform float uRiftGlow, uRiftBleed, uRiftDim, uSplit;
  varying float vRift;
  varying float vRiftBleed;
  varying float vSeed;
  varying float vSynapse;
  varying float vHemi;
  varying float vDepth;
  varying float vFrontness;
  varying float vCenterness;
  varying float vOcclusion;
  varying float vHighlight;
  varying float vFar;
  varying float vCursor;
  varying float vHot;
  varying float vCold;
  varying vec3 vWorldPos;
  void main() {
    vec2 p = gl_PointCoord - 0.5;
    float r = length(p);
    if (r > 0.5) discard;
    float core = pow(smoothstep(0.5, 0.0, r), 2.2);
    float t = pow(vCenterness, max(0.05, uCenterFalloff));
    vec3 base = mix(uEdgeColor, uCenterColor, t);
    vec3 yTint = mix(uCool, uWarm, smoothstep(-0.6, 1.0, vWorldPos.y) * 0.6 + vSeed * 0.25);
    yTint = mix(yTint, yTint * vec3(0.95, 1.0, 1.05), vHemi * 0.4);
    base *= mix(vec3(1.0), yTint, 0.35);
    // Cavity depth: particles in folds (sulci) sink toward the deep colour.
    base = mix(base, uDeepColor, clamp(vOcclusion * uOcclusionStrength, 0.0, 1.0));
    vec3 col = base + uSynapse * vSynapse * 2.0;
    // Active-region highlight: tint the local cluster toward a deeper green and
    // add a gentle glow so it reads as the focal accent.
    col = mix(col, uHighlightColor, vHighlight * 0.5);
    col += uHighlightColor * vHighlight * 0.7;
    // Isolate the focus: while a region is active, darken everything that ISN'T
    // the highlighted cluster toward the deep green so the zone clearly stands out.
    float nonFocus = (1.0 - vHighlight) * uHighlightStrength;
    col = mix(col, uDeepColor, nonFocus * uIsolateStrength);
    float depthMul = mix(1.0 - uDepthDarkness, 1.0, vFrontness);
    col *= depthMul;
    float alphaOut = core * iAlpha * mix(1.0 - uDepthDarkness * 0.7, 1.0, vFrontness);
    alphaOut *= 1.0 + vHighlight * 0.8;
    // Fade the side opposite the active region to focus attention.
    float focusDim = 1.0 - uHighlightStrength * uFocusFadeStrength * vFar;
    col *= focusDim;
    alphaOut *= focusDim;
    // Cursor halo: gently lift particles under the pointer (additive, so even dim
    // particles register where you point — kept subtle).
    col += uCursorColor * vCursor * 0.8 * uCursorStrength;
    alphaOut += vCursor * core * 0.32 * uCursorStrength;
    // Finale: the brain blows up and thins out as it disperses.
    alphaOut *= 1.0 - smoothstep(0.0, 1.0, uExplode) * 0.8;
    // Truth Guardian: the part under the pointer brightens, the other two dim.
    col += uHighlightColor * vHot * 0.4;
    col *= 1.0 - vCold * 0.55;
    alphaOut *= 1.0 + vHot * 0.25 - vCold * 0.45;
    // Truth Guardian: the Rift Stone's light out of the cracks, with a soft bleed into the parts around them; the
    // stone between the cracks darkens as it opens, so the light stands out.
    float stone = 1.0 - uRiftDim * uSplit * (1.0 - clamp(vRift, 0.0, 1.0));
    col *= stone;
    alphaOut *= stone;
    col = mix(col, uRiftColor, clamp(vRift, 0.0, 1.0) * 0.75);
    col += uRiftColor * (vRift * uRiftGlow + vRiftBleed * uRiftBleed);
    alphaOut += core * (vRift * 0.6 + vRiftBleed * 0.25);
    gl_FragColor = vec4(clamp(col, 0.0, 1000.0) * uGlow, alphaOut);
  }
`;

export const FINAL_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 1.0);
  }
`;

export const FINAL_FRAGMENT = /* glsl */ `
  uniform float iTime;
  uniform sampler2D tScene;   // brain + real bloom, rendered off-screen
  uniform vec3 iCornerBlue;
  uniform vec3 iCornerOrange;
  varying vec2 vUv;
  vec3 warp3d(vec3 pos, float t) {
    float curv = .8, a = 1.9, b = 0.7; pos *= 2.;
    pos.x += curv * sin(t + a * pos.y) + t * b; pos.y += curv * cos(t + a * pos.x);
    pos.y += curv * sin(t + a * pos.z) + t * b; pos.z += curv * cos(t + a * pos.y);
    pos.z += curv * sin(t + a * pos.x) + t * b; pos.x += curv * cos(t + a * pos.z);
    return 0.5 + 0.5 * cos(pos.xyz + vec3(1, 2, 4));
  }
  void main() {
    vec2 uv = 2. * vUv - 1.;
    vec3 w = pow(warp3d(vec3(uv.x, sin(uv.y), uv.y), iTime * 1.5), vec3(1.5));
    vec3 col = 1.5 * iCornerBlue * w.x; col *= w.y; col += iCornerOrange * w.z;
    col *= smoothstep(0.6, 1., abs(uv.y));
    col *= smoothstep(-.5, 1., -uv.y * uv.x); col *= smoothstep(-.5, 1., -uv.y * uv.x);
    gl_FragColor = vec4(col + texture2D(tScene, vUv).xyz, 1.);
  }
`;
