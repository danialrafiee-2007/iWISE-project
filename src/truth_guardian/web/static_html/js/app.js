// The plain HTML front end's script: no framework, no build step. It asks the same API as the React app.
// For now it keeps the models' lamp on the rail and the chip in the banner up to date (/api/health), in the
// previous site's words for each state (engine.* in js/i18n.js).

const stateEl = document.getElementById("state");
const lamps = [document.querySelector("#rail-lamp .lamp"), document.getElementById("chip-lamp")].filter(Boolean);
const railLamp = document.getElementById("rail-lamp");
const tr = (key) => (window.TG ? window.TG.t(key) : key);
let lastKey = "engine.connecting";
let lastKind = "wait";

function show(key, kind) {
  lastKey = key;
  lastKind = kind;
  const text = tr(key);
  if (stateEl) stateEl.textContent = text;
  for (const lamp of lamps) {
    lamp.classList.toggle("ready", kind === "ok");
    lamp.classList.toggle("bad", kind === "bad");
  }
  if (railLamp) {
    railLamp.title = text;
    railLamp.setAttribute("aria-label", text);
  }
}

async function poll() {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const h = await res.json();
    if (h.state === "ready") return show(h.online && h.online.configured ? "engine.readyOnline" : "engine.ready", "ok");
    if (h.state === "error" || h.state === "failed") return show("engine.failed", "bad");
    show(h.state === "warming" ? "engine.warming" : "engine.loading", "wait");
  } catch {
    show("engine.unreachable", "bad");
  }
  setTimeout(poll, 2000);
}

if (window.TG) window.TG.onLang(() => show(lastKey, lastKind));
show("engine.connecting", "wait");
poll();
