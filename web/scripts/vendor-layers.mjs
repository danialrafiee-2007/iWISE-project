// Turns the purchased scene bundles in layers-src/ into offline pages under public/layers/, and copies the exact
// three.js builds they were made with (plus only the add-ons they import) under public/vendor/.
//
// Changes to each scene, nothing else: CDN URLs point to the local copies; the authoring panel is hidden and the
// saved-tweaks lookup in localStorage is skipped; palette keys in CONFIG are recoloured to the app's palette (the way
// their makers say to tint them); the render loop skips frames while the app pauses it; a small postMessage bridge
// (same origin only) lets the app pause it, update CONFIG and, for Signal Array, choose the lit lamp.
//
// Run: npm run layers   (after npm install)

import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, posix } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const THREE = { "0.170.0": join(web, "node_modules/three"), "0.143.0": join(web, "node_modules/three-r143") };

const SCENES = {
  "glass-halo": {
    bg: "'#0e141c'", bgGrey: "'#18222d'", bgPool: "0.34", bgVignette: "0.55",
    glassColor: "'#0f5f58'", attenuationColor: "'#5eead4'", shadowColor: "'#000000'", shadowOpacity: "0.4",
  },
  "halftone-iris": {
    colDot: "'#cfe9e4'", colDotDeep: "'#4b7a75'", colIris: "'#1f9c8a'", colHalo: "'#2dd4bf'", colCatchlight: "'#ffe3a8'", colAura: "'#0f3b3a'",
  },
  "lumen-grid": {},
  "signal-array": { bgTop: "'#06080b'", bgBottom: "'#010203'", glowPool: "0.1", accentGlow: "0.3", autoCycle: "0" },
};

const BRIDGE = `
/* ---- Truth Guardian bridge (added by web/scripts/vendor-layers.mjs) ---- */
window.__tgPaused = false
addEventListener('message', (e) => {
  if (e.origin !== location.origin || !e.data || e.data.tg !== 1) return
  if ('paused' in e.data) window.__tgPaused = !!e.data.paused
  if (e.data.config) { Object.assign(CONFIG, e.data.config); applyConfig() }
  if (e.data.signal && typeof applyState === 'function') { CONFIG.autoCycle = 0; applyState(e.data.signal) }
})
parent.postMessage({ tg: 1, ready: true }, location.origin)
`;

function copy(from, to) {
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
}

/** Copy an add-on and every module it imports by relative path. */
function copyAddon(root, out, rel, seen) {
  if (seen.has(rel)) return;
  seen.add(rel);
  const src = join(root, "examples/jsm", rel);
  copy(src, join(out, "examples/jsm", rel));
  for (const m of readFileSync(src, "utf8").matchAll(/from\s+['"](\.{1,2}\/[^'"]+)['"]/g)) {
    copyAddon(root, out, posix.normalize(posix.join(posix.dirname(rel), m[1])), seen);
  }
}

const used = {};
for (const [name, overrides] of Object.entries(SCENES)) {
  let html = readFileSync(join(web, "layers-src", `${name}.html`), "utf8").replace(/\r\n/g, "\n");
  const version = html.match(/unpkg\.com\/three@([\d.]+)\/build/)[1];
  const base = `/vendor/three@${version}`;
  html = html
    .replaceAll(`https://unpkg.com/three@${version}/build/three.module.js`, `${base}/build/three.module.js`)
    .replaceAll(`https://unpkg.com/three@${version}/examples/jsm/`, `${base}/examples/jsm/`)
    .replace("https://www.gstatic.com/draco/versioned/decoders/1.5.7/", `${base}/examples/jsm/libs/draco/gltf/`)
    .replace(/localStorage\.getItem\(STORAGE_KEY\)/, "null")
    .replace("canvas.addEventListener('click', () => advance())", "/* click-to-advance removed: the app sets the lamp */")
    .replace("</head>", "<style>#ui-panel{display:none!important}</style>\n</head>")
    .replace(/(function (render|animate)\(\) \{\n\s*requestAnimationFrame\(\2\);?\n)/, "$1  if (window.__tgPaused) return\n");
  if (!html.includes("if (window.__tgPaused) return")) throw new Error(`${name}: render loop not found`);
  for (const [key, value] of Object.entries(overrides)) {
    const pattern = new RegExp(`(\\n\\s*${key}:\\s*)([^,\\n]+)(,)`);
    if (!pattern.test(html)) throw new Error(`${name}: CONFIG key ${key} not found`);
    html = html.replace(pattern, `$1${value}$3`);
  }
  const end = html.lastIndexOf("</script>");
  html = html.slice(0, end) + BRIDGE + html.slice(end);
  const external = html.match(/https?:\/\/(?!www\.w3\.org)[^\s"'`)]+/g)?.filter((u) => !u.startsWith("http://www.w3.org"));
  if (external?.length) console.warn(`${name}: still references`, [...new Set(external)]);
  mkdirSync(join(web, "public/layers"), { recursive: true });
  writeFileSync(join(web, "public/layers", `${name}.html`), html);
  for (const m of html.matchAll(/from\s+['"]three\/addons\/([^'"]+)['"]/g)) (used[version] ??= new Set()).add(m[1]);
  used[version] ??= new Set();
  if (html.includes("libs/draco/gltf/")) used[version].add("@draco");
  console.log(`layers/${name}.html  three ${version}`);
}

for (const [version, addons] of Object.entries(used)) {
  const root = THREE[version];
  if (!existsSync(root)) throw new Error(`three ${version} is not installed (npm install)`);
  const out = join(web, "public/vendor", `three@${version}`);
  copy(join(root, "build/three.module.js"), join(out, "build/three.module.js"));
  if (existsSync(join(root, "build/three.core.js"))) copy(join(root, "build/three.core.js"), join(out, "build/three.core.js"));
  copy(join(root, "LICENSE"), join(out, "LICENSE"));
  const seen = new Set();
  for (const rel of addons) {
    if (rel === "@draco") {
      for (const f of ["draco_decoder.js", "draco_decoder.wasm", "draco_wasm_wrapper.js"]) copy(join(root, "examples/jsm/libs/draco/gltf", f), join(out, "examples/jsm/libs/draco/gltf", f));
    } else copyAddon(root, out, rel, seen);
  }
  console.log(`vendor/three@${version}: ${seen.size} add-on files`);
}
