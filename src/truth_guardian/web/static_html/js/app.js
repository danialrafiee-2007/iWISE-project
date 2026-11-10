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
    if (h.state === "ready") return show("engine.ready", "ok");
    if (h.state === "error" || h.state === "failed") return show("engine.failed", "bad");
    show(h.state === "warming" ? "engine.warming" : "engine.loading", "wait");
  } catch {
    show("engine.unreachable", "bad");
  }
  setTimeout(poll, 2000);
}

// ---- The second lamp: whether the free online models answer now (/api/online/status, D-202) ----
// Green when a model and Wikipedia answer, amber when only one of them does, red when none. Its tooltip names the
// services that answered. The server keeps its answer a minute, so asking once a minute costs nothing.
const onlineEl = document.getElementById("online-state");
const onlineLamps = [document.getElementById("online-lamp"), document.querySelector("#rail-online-lamp .lamp")].filter(Boolean);
const railOnline = document.getElementById("rail-online-lamp");
const onlineChip = document.getElementById("online-chip");
const NAMES = { groq: "Groq", openrouter: "OpenRouter", pollinations: "Pollinations", wikipedia: "Wikipedia", tavily: "Tavily" };
let online = null;

function showOnline() {
  const state = online ? online.state : "checking";
  const key = { online: "html.online.on", partly: "html.online.partly", offline: "html.online.off", restart: "html.online.restart" }[state] || "html.online.checking";
  if (onlineEl) onlineEl.textContent = tr(key);
  for (const lamp of onlineLamps) {
    lamp.classList.toggle("ready", state === "online");
    lamp.classList.toggle("bad", state === "offline");
  }
  const names = online ? [...online.answer, ...online.search].map((n) => NAMES[n] || n) : [];
  const tip = names.length ? `${tr(key)}: ${names.join(" · ")}` : tr(key);
  if (onlineChip) onlineChip.title = tip;
  if (railOnline) {
    railOnline.title = tip;
    railOnline.setAttribute("aria-label", tip);
  }
}

async function pollOnline() {
  try {
    const res = await fetch("/api/online/status", { cache: "no-store" });
    // 404: the server was started before this page had its online lamp (D-203); the internet may well be there, so
    // the lamp asks for the server to be restarted instead of saying "not connected".
    if (res.status === 404) online = { state: "restart", answer: [], search: [] };
    else if (!res.ok) throw new Error(`HTTP ${res.status}`);
    else online = await res.json();
  } catch {
    online = { state: "offline", answer: [], search: [] };
  }
  showOnline();
  setTimeout(pollOnline, 60000);
}

if (window.TG) window.TG.onLang(() => { show(lastKey, lastKind); showOnline(); });
show("engine.connecting", "wait");
showOnline();
poll();
pollOnline();
