import { useEffect, useRef, useState } from "react";
import { paintShield, ShieldMark } from "../components/ShieldMark";
import { useI18n } from "../i18n";

// The opening of the site, after the "Jade Cipher" scene (docs/CREDITS.md): a wall of code and the columns of rain falling down
// three depth layers (the rain and the pointer's spotlight are the scene's, rewritten as one fragment shader without
// three.js, and its glyphs are fine zeros and ones here). Added here: the rain starts from the top of a dark screen, the
// name and shield of the project build themselves out of still finer digits as their columns reach them and then settle
// into the sharp logo, and on a click, scroll, touch or key every column falls away, the logo with it, uncovering the
// home page already loaded beneath.

const VERT = `#version 300 es
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

// The atlas: a 0 and a 1 side by side. Cells keep this shape on screen, so the digits stand close together in a column.
const TILE_W = 48;
const TILE_H = 64;

const FRAG = `#version 300 es
precision highp float;
uniform float iTime, iExit, uAspect, uCols, uLogoCols;
uniform vec2 iResolution, uMouse;
uniform vec4 uLogoRect;
uniform sampler2D uAtlas, uLogo;
out vec4 frag;

const float TILE_W = ${TILE_W}.0;
const float CELL = ${TILE_W / TILE_H};   // a cell's width over its height
const vec3 HEAD = vec3(0.902, 1.0, 0.949);
const vec3 TRAIL = vec3(0.235, 0.961, 0.604);
const vec3 AMBIENT = vec3(0.071, 0.247, 0.169);
const vec3 GROUND = vec3(0.012, 0.043, 0.031);
const float FORMED = 2.7;   // seconds until the sharp logo has replaced its glyphs

float hash11(float p) { p = fract(p * 0.1031); p *= p + 33.33; p *= p + p; return fract(p); }
float hash21(vec2 p) { vec3 q = fract(vec3(p.xyx) * 0.1031); q += dot(q, q.yzx + 33.33); return fract((q.x + q.y) * q.z); }

// How far a column has fallen on the way out, in screen heights: each lets go a little after the last and accelerates.
float drop(float column, float seed) {
  if (iExit < 0.0) return 0.0;
  float t = max(iExit - hash11(column * 2.7 + seed) * 0.42, 0.0);
  return t * t * 2.8;
}

// A 0 or a 1. The mip level is set by the cell's size: plain texture() would see a jump at every cell's edge and blur there.
float glyph(vec2 cell, vec2 local, float stepNo, float seed, float cols) {
  float bit = step(0.5, hash21(cell + stepNo * 0.137 + seed * 2.0));
  float lod = max(log2(TILE_W * cols / iResolution.x), 0.0);
  return textureLod(uAtlas, vec2((bit + clamp(local.x, 0.02, 0.98)) * 0.5, local.y), lod).r;
}

// One depth layer of falling digits; uv runs from the top left, down.
vec3 layer(vec2 uv, float cols, float parallax, float dim, float seed) {
  uv += (uMouse - 0.5) * parallax;
  float rows = max(floor(cols * CELL / uAspect), 1.0);
  float column = floor(uv.x * cols);
  float fallen = drop(column, seed);
  if (fallen > 0.0 && uv.y < fallen) return vec3(0.0);
  uv.y -= fallen;
  vec2 cell = vec2(column, floor(uv.y * rows));
  vec2 local = vec2(fract(uv.x * cols), fract(uv.y * rows));

  float cseed = hash11(column * 1.37 + seed * 17.0);
  float alive = step(0.35, hash11(column * 0.91 + seed * 3.1 + 5.0));
  float trail = rows * (0.3 + cseed * 0.4);
  float head = rows * (iTime * (0.22 + cseed * 0.5) - hash11(column * 3.3 + seed) * 0.6);
  float reached = step(cell.y, head);     // nothing below a column's first head: the rain starts from the top
  float behind = mod(head - cell.y, rows + trail + 2.0);
  float streak = alive * clamp(1.0 - behind / trail, 0.0, 1.0);
  streak *= streak;
  float isHead = smoothstep(1.4, 0.0, behind) * alive;

  float cov = glyph(cell, local, floor(iTime * 3.5 * (0.3 + cseed) + hash21(cell + seed) * 13.0), seed, cols);
  float twinkle = 1.0 - 0.12 * (0.5 + 0.5 * sin(iTime * 1.8 + hash21(cell + seed) * 6.2831));
  vec3 c = AMBIENT * 0.16 * twinkle + TRAIL * streak + HEAD * isHead * (0.5 + streak) * 1.35;
  // On the way out the top of each falling column burns bright, like a head.
  if (fallen > 0.0) c += HEAD * smoothstep(5.0, 0.0, cell.y) * 1.2;
  return c * cov * reached * dim;
}

// The logo: premultiplied colour and coverage, first of small digits, then sharp, then digits again as it falls.
vec4 logo(vec2 uv) {
  float rows = max(floor(uLogoCols * CELL / uAspect), 1.0);
  vec2 grid = vec2(uLogoCols, rows);
  float column = floor(uv.x * uLogoCols);
  vec2 p = vec2(uv.x, uv.y - drop(column, 3.0));
  if (p.y < 0.0) return vec4(0.0);
  vec2 cell = vec2(column, floor(p.y * rows));
  vec2 local = vec2(fract(p.x * uLogoCols), fract(p.y * rows));
  vec2 centre = (cell + 0.5) / grid;
  vec2 at = (centre - uLogoRect.xy) / uLogoRect.zw;
  vec4 small = vec4(0.0);
  if (all(greaterThanEqual(at, vec2(0.0))) && all(lessThanEqual(at, vec2(1.0)))) {
    float seed = hash11(column * 1.37 + 9.0);
    // A column's head reaches this cell, lights it and leaves it burning, so the shape builds from the top down.
    float arrives = centre.y * (1.15 + 0.8 * seed) + seed * 0.35 + 0.2;
    float age = iTime - arrives;
    float lit = smoothstep(0.0, 0.1, age) * step(0.5, texture(uLogo, at).a);
    float settled = min(iTime, arrives + 0.5);
    float cov = glyph(cell, local, floor(settled * 9.0 + hash21(cell) * 13.0), 4.0, uLogoCols);
    vec3 tone = mix(TRAIL, HEAD, exp(-max(age, 0.0) * 4.0) * 0.9 + 0.2);
    small = vec4(tone * cov * lit, cov * lit);
  }
  vec2 sharpAt = (p - uLogoRect.xy) / uLogoRect.zw;
  vec4 sharp = vec4(0.0);
  if (all(greaterThanEqual(sharpAt, vec2(0.0))) && all(lessThanEqual(sharpAt, vec2(1.0)))) sharp = texture(uLogo, sharpAt);
  float toCode = iExit < 0.0 ? 0.0 : smoothstep(0.0, 0.2, iExit);
  return mix(small, sharp, smoothstep(FORMED - 0.55, FORMED, iTime) * (1.0 - toCode));
}

void main() {
  vec2 uv = vec2(gl_FragCoord.x / iResolution.x, 1.0 - gl_FragCoord.y / iResolution.y);

  vec3 rain = layer(uv, uCols, 0.05, 1.0, 1.0);
  rain += layer(uv, uCols * 1.4, 0.0275, 0.55, 7.0);
  rain += layer(uv, uCols * 1.85, 0.014, 0.3025, 19.0);
  float spot = smoothstep(0.22, 0.0, length((uv - uMouse) * vec2(uAspect, 1.0))) * 0.9;
  rain += rain * spot;

  // Once the logo stands, the rain draws back from it so it reads clearly.
  float formed = smoothstep(FORMED - 0.8, FORMED + 0.4, iTime);
  vec2 fromLogo = (uv - uLogoRect.xy - uLogoRect.zw * 0.5) / (uLogoRect.zw * vec2(0.72, 1.6));
  rain *= mix(1.0, mix(0.72, 0.1, smoothstep(1.25, 0.45, length(fromLogo))), formed);

  // The ground falls away with its front layer's columns, in step with the rain.
  float ground = 1.0;
  if (iExit >= 0.0) {
    vec2 front = uv + (uMouse - 0.5) * 0.05;
    float fallen = drop(floor(front.x * uCols), 1.0);
    if (fallen > 0.0) ground = smoothstep(0.0, 0.015, front.y - fallen);
  }
  vec3 scene = (GROUND + rain) * ground;
  vec4 mark = logo(uv);
  frag = vec4(scene * (1.0 - mark.a) + mark.rgb, ground + (1.0 - ground) * mark.a);
}`;

const NAME = "Truth Guardian";
const EXIT_SECONDS = 1.25;
const STOP_KEYS = new Set(["Enter", "Escape", " ", "Tab", "ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End"]);
// The page beneath listens on the window, so covering it is not enough: the click that enters would also open the brain.
const HELD_BACK = ["pointerdown", "pointermove", "pointerup", "mousedown", "mousemove", "mouseup", "click", "dblclick", "wheel", "keydown", "keyup", "touchstart", "touchmove", "touchend"];

function paintAtlas() {
  const atlas = document.createElement("canvas");
  atlas.width = TILE_W * 2;
  atlas.height = TILE_H;
  const g = atlas.getContext("2d")!;
  g.fillStyle = "#000";
  g.fillRect(0, 0, atlas.width, atlas.height);
  g.fillStyle = "#fff";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.font = `600 ${Math.round(TILE_H * 0.86)}px ui-monospace,"Cascadia Mono",Consolas,Menlo,"DejaVu Sans Mono",monospace`;
  g.fillText("0", TILE_W * 0.5, TILE_H * 0.54);
  g.fillText("1", TILE_W * 1.5, TILE_H * 0.54);
  return atlas;
}

/** The logo as in the top bar: the shield, then the name, in light letters since it stands on the dark screen. */
async function paintLogo() {
  const font = '500 190px Fraunces, Georgia, serif';
  await Promise.race([document.fonts.load(font, NAME), new Promise((done) => setTimeout(done, 800))]).catch(() => {});
  const logo = document.createElement("canvas");
  const g = logo.getContext("2d")!;
  g.font = font;
  const shield = 300;
  const shieldWidth = (shield * 19) / 21.5;
  const margin = 30;
  logo.width = Math.ceil(margin * 2 + shieldWidth + 56 + g.measureText(NAME).width);
  logo.height = shield + margin * 2;
  paintShield(g, margin, margin, shield);
  g.font = font;
  g.textBaseline = "middle";
  const fill = g.createLinearGradient(0, margin, 0, margin + shield);
  fill.addColorStop(0, "#f6fffa");
  fill.addColorStop(1, "#c6f6dc");
  g.fillStyle = fill;
  g.shadowColor = "rgb(60 245 154 / 0.35)";
  g.shadowBlur = 22;
  g.fillText(NAME, margin + shieldWidth + 56, margin + shield / 2 + 8);
  return logo;
}

function texture(gl: WebGL2RenderingContext, unit: number, image: HTMLCanvasElement, mipmaps: boolean) {
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, mipmaps ? gl.LINEAR_MIPMAP_LINEAR : gl.LINEAR);
  if (mipmaps) gl.generateMipmap(gl.TEXTURE_2D);
}

export function JadeIntro({ onDone }: { onDone: () => void }) {
  const { t } = useI18n();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const leave = useRef(() => {});
  const [still] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches || !document.createElement("canvas").getContext("webgl2"));
  const [leaving, setLeaving] = useState(false);

  // Any of these enters the site. Meanwhile the page beneath stays where it is, without hiding its scrollbar and so
  // shifting sideways at the end, and hears nothing until the opening has gone.
  useEffect(() => {
    const go = () => leave.current();
    const hold = (e: Event) => e.stopPropagation();
    HELD_BACK.forEach((type) => window.addEventListener(type, hold, { passive: true, capture: true }));
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      go();
    };
    const onTouchMove = (e: TouchEvent) => e.preventDefault();
    const onPointer = (e: PointerEvent) => {
      if (e.button === 0) go();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || !STOP_KEYS.has(e.key)) return;
      e.preventDefault();
      go();
    };
    window.addEventListener("wheel", onWheel, { passive: false, capture: true });
    window.addEventListener("touchmove", onTouchMove, { passive: false, capture: true });
    window.addEventListener("pointerdown", onPointer, true);
    window.addEventListener("keydown", onKey, true);
    // The page's own scrollbar, once it has really moved: a phone also sends a scroll as the page loads, with nothing moved.
    const onScroll = () => {
      if (window.scrollY > 0) go();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      HELD_BACK.forEach((type) => window.removeEventListener(type, hold, true));
      window.removeEventListener("wheel", onWheel, true);
      window.removeEventListener("touchmove", onTouchMove, true);
      window.removeEventListener("pointerdown", onPointer, true);
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  useEffect(() => {
    if (still) {
      leave.current = () => {
        setLeaving(true);
        window.setTimeout(onDone, 350);
      };
      return;
    }
    const canvas = canvasRef.current;
    const gl = canvas?.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false, powerPreference: "high-performance" });
    if (!canvas || !gl) {
      leave.current = onDone;
      return;
    }
    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? "shader");
      return shader;
    };
    const program = gl.createProgram()!;
    try {
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VERT));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? "link");
    } catch (e) {
      console.warn("intro skipped:", e);
      onDone();
      return;
    }
    gl.useProgram(program);
    gl.bindVertexArray(gl.createVertexArray());
    const at = (name: string) => gl.getUniformLocation(program, name);

    let raf = 0;
    let stopped = false;
    let started = 0;
    let exitAt = -1;
    let logoAspect = 5;
    const mouse = [0.5, 0.5];
    const onMove = (e: PointerEvent) => {
      mouse[0] = e.clientX / window.innerWidth;
      mouse[1] = e.clientY / window.innerHeight;
    };
    window.addEventListener("pointermove", onMove, { passive: true, capture: true });

    const resize = () => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(at("iResolution"), canvas.width, canvas.height);
      gl.uniform1f(at("uAspect"), width / height);
      gl.uniform1f(at("uCols"), width / (width < 640 ? 10 : 12));
      gl.uniform1f(at("uLogoCols"), width / (width < 640 ? 3.6 : 5.5));
      const w = Math.min(width * 0.8, 880) / width;
      const h = (w * width) / logoAspect / height;
      gl.uniform4f(at("uLogoRect"), 0.5 - w / 2, 0.46 - h / 2, w, h);
    };
    window.addEventListener("resize", resize);

    const frame = (now: number) => {
      if (stopped) return;
      raf = requestAnimationFrame(frame);
      if (!started) started = now;
      const exit = exitAt < 0 ? -1 : (now - exitAt) / 1000;
      gl.uniform1f(at("iTime"), (now - started) / 1000);
      gl.uniform1f(at("iExit"), exit);
      gl.uniform2f(at("uMouse"), mouse[0], mouse[1]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (exit > EXIT_SECONDS) {
        stopped = true;
        gl.getExtension("WEBGL_lose_context")?.loseContext();
        onDone();
      }
    };

    leave.current = () => {
      if (exitAt >= 0) return;
      exitAt = performance.now();
      setLeaving(true);
    };

    paintLogo().then((logo) => {
      if (stopped) return;
      logoAspect = logo.width / logo.height;
      texture(gl, 0, paintAtlas(), true);
      texture(gl, 1, logo, true);
      gl.uniform1i(at("uAtlas"), 0);
      gl.uniform1i(at("uLogo"), 1);
      resize();
      raf = requestAnimationFrame(frame);
    });

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove, true);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div role="button" tabIndex={0} aria-label={t("splash.enter")} className={`fixed inset-0 z-[100] cursor-pointer select-none outline-none ${still ? `grid place-items-center bg-[#030b08] transition-opacity duration-300 ${leaving ? "opacity-0" : ""}` : ""}`}>
      {still ? (
        <div className="flex items-center gap-4" lang="en">
          <ShieldMark size={72} />
          <span className="font-display text-[clamp(32px,6vw,60px)] font-medium text-[#f0fff7]">{NAME}</span>
        </div>
      ) : (
        <canvas ref={canvasRef} aria-hidden="true" className="block h-full w-full" />
      )}
      {!leaving && (
        <p className="intro-hint absolute inset-x-4 bottom-[8vh] m-0 text-center font-sans text-[15px] tracking-wide text-[#c6f6dc]">
          <span className="inline-block rounded-full bg-[#030b08]/80 px-4 py-1.5">{t("splash.enter")}</span>
        </p>
      )}
    </div>
  );
}
