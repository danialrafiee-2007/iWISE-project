// The plain HTML front end's script: no framework, no build step. It asks the same API as the React app.
// It keeps three lamps up to date, each in the banner's chips and in the rail, one under the other (D-202, D-204):
// 1. the local models that answer and read files, offline on this computer (/api/ask/generators, /api/media/status);
// 2. the free online models (/api/online/status);
// 3. the Guardian itself, the models that check every answer (/api/health).
// Green when ready, amber while loading or when only part is there, red when not there.

const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);

// One lamp: its chip in the banner (lamp and words) and its twin in the rail (lamp and tooltip).
function lamp(chipLamp, chipText, rail) {
  const chip = document.getElementById(chipText)?.closest(".status-chip");
  const lamps = [document.getElementById(chipLamp), document.querySelector(`#${rail} .lamp`)].filter(Boolean);
  const railEl = document.getElementById(rail);
  const textEl = document.getElementById(chipText);
  let last = null;
  function show(key, kind, detail = "") {
    if (!last || last[0] !== key) window.TGLog?.log("lamp", chipText === "state" ? "local models" : chipText === "online-state" ? "online models" : "guardian", `${tr(key)}${detail ? ` (${detail})` : ""}`, kind === "bad" ? "error" : "ok");
    last = [key, kind, detail];
    const text = tr(key);
    const tip = detail ? `${text}: ${detail}` : text;
    if (textEl) textEl.textContent = text;
    for (const el of lamps) {
      el.classList.toggle("ready", kind === "ok");
      el.classList.toggle("bad", kind === "bad");
    }
    if (chip) chip.title = tip;
    if (railEl) {
      railEl.title = tip;
      railEl.setAttribute("aria-label", tip);
    }
  }
  return { show, again: () => last && show(...last) };
}

const local = lamp("chip-lamp", "state", "rail-lamp");
const onlineLamp = lamp("online-lamp", "online-state", "rail-online-lamp");
const guard = lamp("guard-lamp", "guard-state", "rail-guard-lamp");

const json = async (url) => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
  return res.json();
};

// ---- 1. The local models: the one that writes answers and the three readers (speech, text in images, what an image
// shows). Each counts when its files are present and its runtime is installed. ----
// Qwen3-VL-2B both writes the answers and says what an image shows, so it is named once.
const READERS = { vision: "Qwen3-VL-2B", speech: "Whisper Small", ocr: "Tesseract 5" };
async function pollLocal() {
  try {
    const [writers, media] = await Promise.all([json("/api/ask/generators"), json("/api/media/status")]);
    const rows = Object.fromEntries((media.components || []).map((row) => [row.name, row]));
    const parts = Object.entries(READERS).map(([name, label]) => {
      const row = rows[name];
      const ok = !!(row && row.files_present && row.runtime_ready) && (name !== "vision" || !!writers.local);
      return [label, ok];
    });
    const ready = parts.filter(([, ok]) => ok).map(([name]) => name);
    const missing = parts.filter(([, ok]) => !ok).map(([name]) => name);
    if (!missing.length) local.show("engine.ready", "ok", ready.join(" · "));
    else if (ready.length) local.show("html.local.partly", "wait", missing.join(" · "));
    else local.show("html.local.none", "bad");
    setTimeout(pollLocal, 60000);
  } catch {
    local.show("engine.unreachable", "bad");
    setTimeout(pollLocal, 5000);
  }
}

// ---- 2. The free online models: green when a model and Wikipedia answer, amber when only one of them does, red when
// none. The server keeps its answer a minute, so asking once a minute costs nothing. A 404 means the server was started
// before this lamp existed: the internet may well be there, so it asks for the server to be restarted. ----
const NAMES = { groq: "Groq", openrouter: "OpenRouter", pollinations: "Pollinations", wikipedia: "Wikipedia", tavily: "Tavily" };
async function pollOnline() {
  try {
    const online = await json("/api/online/status");
    const names = [...online.answer, ...online.search].map((n) => NAMES[n] || n).join(" · ");
    const key = { online: "html.online.on", partly: "html.online.partly" }[online.state] || "html.online.off";
    onlineLamp.show(key, { online: "ok", partly: "wait" }[online.state] || "bad", names);
  } catch (e) {
    onlineLamp.show(e.status === 404 ? "html.online.restart" : "html.online.off", e.status === 404 ? "wait" : "bad");
  }
  setTimeout(pollOnline, 60000);
}

// ---- 3. The Guardian: the models that check every answer, loaded and warmed up on the server (/api/health) ----
async function pollGuard() {
  try {
    const h = await json("/api/health");
    if (h.state === "ready") return guard.show("html.guard.ready", "ok", h.model_version || "");
    if (h.state === "error" || h.state === "failed") return guard.show("html.guard.failed", "bad", h.error || "");
    guard.show("html.guard.loading", "wait");
  } catch {
    guard.show("engine.unreachable", "bad");
  }
  setTimeout(pollGuard, 2000);
}

if (window.TG) window.TG.onLang(() => { local.again(); onlineLamp.again(); guard.again(); });
local.show("engine.connecting", "wait");
onlineLamp.show("html.online.checking", "wait");
guard.show("html.guard.loading", "wait");
pollLocal();
pollOnline();
pollGuard();
