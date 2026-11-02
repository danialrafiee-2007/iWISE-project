import { useEffect, useRef } from "react";

// The gradient engine of Pharos, Loupe and Riffle (docs/CREDITS.md): one fullscreen triangle, one fragment shader, every CONFIG
// key uploaded as u + Key, a clamped accumulating clock and the pointer rig the gradient ships with. Sized to its
// container instead of the window; it stops drawing when paused, hidden, off screen or under reduced motion.

type Config = Readonly<Record<string, string | number>>;
export type Rig = "lead" | "chain";

const VERT = `#version 300 es
void main() {
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const hexToVec3 = (hex: string): [number, number, number] => {
  const n = parseInt(hex.replace("#", ""), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};

export function ShaderCanvas({
  frag,
  config,
  rig,
  rest = [0, 0],
  paused = false,
  className,
}: {
  frag: string;
  config: Config;
  rig: Rig;
  rest?: [number, number];
  paused?: boolean;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, depth: false, stencil: false, powerPreference: "high-performance" });
    if (!gl) {
      canvas.style.display = "none";
      return;
    }
    const compile = (type: number, src: string) => {
      const sh = gl.createShader(type)!;
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh) ?? "shader");
      return sh;
    };
    const program = gl.createProgram()!;
    try {
      gl.attachShader(program, compile(gl.VERTEX_SHADER, VERT));
      gl.attachShader(program, compile(gl.FRAGMENT_SHADER, frag));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? "link");
    } catch (e) {
      console.warn("gradient disabled:", e);
      canvas.style.display = "none";
      return;
    }
    gl.useProgram(program);
    gl.bindVertexArray(gl.createVertexArray());
    const locations = new Map<string, WebGLUniformLocation | null>();
    const loc = (n: string) => {
      if (!locations.has(n)) locations.set(n, gl.getUniformLocation(program, n));
      return locations.get(n)!;
    };
    for (const [k, v] of Object.entries(config)) {
      if (k === "maxDpr") continue;
      const names = k === "bgColor" ? ["uBg", "uBgColor"] : ["u" + k[0].toUpperCase() + k.slice(1)];
      for (const n of names) {
        if (typeof v === "string") gl.uniform3f(loc(n), ...hexToVec3(v));
        else gl.uniform1f(loc(n), v);
      }
    }

    const maxDpr = Number(config.maxDpr ?? 1);
    let width = 1, height = 1;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
      width = Math.max(1, Math.round(rect.width * dpr));
      height = Math.max(1, Math.round(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      gl.viewport(0, 0, width, height);
      gl.uniform2f(loc("iResolution"), width, height);
    };
    const observer = new ResizeObserver(() => {
      resize();
      draw();
    });

    const P = { tx: rest[0], ty: rest[1], ax: rest[0], ay: rest[1], hx: rest[0], hy: rest[1], mx: rest[0], my: rest[1], sx: rest[0], sy: rest[1], e: 0 };
    let seeded = false, intro = 0, clock = 0, prevT = performance.now(), raf = 0, visible = true;
    const aim = (e: PointerEvent) => {
      if (!config.cursor) return;
      const rect = canvas.getBoundingClientRect();
      if (rect.height === 0) return;
      P.tx = ((e.clientX - rect.left) / rect.width - 0.5) * (rect.width / rect.height);
      P.ty = 0.5 - (e.clientY - rect.top) / rect.height;
      if (rig === "chain" && !seeded) {
        seeded = true;
        P.hx = P.mx = P.sx = P.tx;
        P.hy = P.my = P.sy = P.ty;
      }
    };

    const draw = () => {
      gl.uniform1f(loc("iTime"), clock);
      if (rig === "lead") {
        gl.uniform2f(loc("iMouse"), P.hx, P.hy);
      } else {
        gl.uniform1f(loc("iIntro"), intro);
        gl.uniform1f(loc("iEnergy"), P.e);
        gl.uniform2f(loc("iMouse"), P.hx, P.hy);
        gl.uniform2f(loc("iLag"), P.mx, P.my);
        gl.uniform2f(loc("iTail"), P.sx, P.sy);
      }
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const still = () => pausedRef.current || document.hidden || !visible || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const raw = now - prevT;
      prevT = now;
      if (still()) return;
      if (rig === "lead") {
        const ms = raw > 50 ? 50 : raw < 4.167 ? 4.167 : raw;
        const s = ms > 36.7 ? 2.2 : ms * 0.06;
        clock += ms * 0.001;
        const kLead = 0.105 * s, kBody = 0.043 * s;
        P.ax += (P.tx - P.ax) * kLead;
        P.ay += (P.ty - P.ay) * kLead;
        P.hx += (P.ax - P.hx) * kBody;
        P.hy += (P.ay - P.hy) * kBody;
      } else {
        const dt = raw > 50 ? 0.05 : raw < 4.167 ? 0.004167 : raw * 0.001;
        clock += dt;
        const kh = 1 - Math.exp(-5.6 * dt), km = 1 - Math.exp(-2.4 * dt), ks = 1 - Math.exp(-1.15 * dt);
        P.hx += (P.tx - P.hx) * kh; P.hy += (P.ty - P.hy) * kh;
        P.mx += (P.hx - P.mx) * km; P.my += (P.hy - P.my) * km;
        P.sx += (P.mx - P.sx) * ks; P.sy += (P.my - P.sy) * ks;
        const ex = P.hx - P.sx, ey = P.hy - P.sy;
        const want = Math.min(Math.sqrt(ex * ex + ey * ey) * 5.5, 1);
        P.e += (want - P.e) * (1 - Math.exp(-(want > P.e ? 4.5 : 0.42) * dt));
        intro += ((seeded ? 1 : 0) - intro) * (1 - Math.exp(-3.0 * dt));
      }
      draw();
    };

    const io = new IntersectionObserver((es) => (visible = es[0].isIntersecting), { threshold: 0 });
    io.observe(canvas);
    observer.observe(canvas);
    window.addEventListener("pointermove", aim, { passive: true });
    window.addEventListener("pointerdown", aim, { passive: true });
    resize();
    draw();
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      observer.disconnect();
      window.removeEventListener("pointermove", aim);
      window.removeEventListener("pointerdown", aim);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, [frag, config, rig, rest[0], rest[1]]);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" style={{ display: "block", width: "100%", height: "100%" }} />;
}
