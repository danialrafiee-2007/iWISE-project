// Fool the Guardian, as on the previous site's page (pages/Fool.tsx): take a grounded answer, slip one lie into it with
// one of eight tricks (or edit it by hand), and see whether the Guardian finds the exact words. The tricks are the
// previous site's cards cascade (js/cascade.js: the wheel over it turns the cards, the dots and the counter beside it),
// each card with the share of its trick caught in the project's suite. While the edit is checked, the engine's stages
// come in one by one; the result is the project's shield in green (caught and found), amber (flagged but not placed,
// or only cautioned) or red (it got through) beside its title, then the full report. The sources are a list always in
// view: a click opens one in full (marked in peach), and its words can be selected with the mouse. The score of tries
// and lies that got through counts this visit only and starts at zero each time the site is opened. A trick with
// nothing to change in the current answer is marked on its card, and its button finds an answer it fits instead, so
// none ends in "does not apply". Nothing can be tricked or checked before the models are ready.
// Server: /api/health, /api/fool/answers, /api/fool/tricks/{id} (the tricks that fit an answer), /api/fool/edit (a trick
// on an answer), /api/fool/check (streamed), /api/model-card.

(() => {
  const root = document.getElementById("fool-tab");
  const scoreEl = document.getElementById("fool-score");
  if (!root) return;
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const lang = () => (window.TG ? window.TG.lang : "en");
  const loc = () => ({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang();
  const num = (x, d = 2) => (x == null ? "–" : new Intl.NumberFormat(loc(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(x));
  const int = (x, digits = 1) => new Intl.NumberFormat(loc(), { minimumIntegerDigits: digits }).format(x);
  const pct = (x) => (x == null ? "–" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 0 }).format(x));
  // The previous site's eight tricks, in its order, each with its card's colours.
  const KINDS = ["number", "entity", "negation", "role_swap", "addition", "antonym", "quantifier", "certainty"];
  const FILL = {
    number: "linear-gradient(150deg,#0f766e,#134e4a 55%,#042f2e)",
    entity: "linear-gradient(150deg,#1d4ed8,#1e3a8a 55%,#0b1437)",
    negation: "linear-gradient(150deg,#be123c,#7f1d1d 55%,#2a0a0f)",
    role_swap: "linear-gradient(150deg,#7c3aed,#4c1d95 55%,#1a0b33)",
    addition: "linear-gradient(150deg,#b45309,#78350f 55%,#2a1405)",
    antonym: "linear-gradient(150deg,#0e7490,#164e63 55%,#06202a)",
    quantifier: "linear-gradient(150deg,#4d7c0f,#365314 55%,#121c06)",
    certainty: "linear-gradient(150deg,#a21caf,#701a75 55%,#24062a)",
  };

  let answers = [];
  let index = 0;
  let text = "";
  let trick = 0;
  let edit = null; // { original, new } from the last trick
  let opened = new Set(); // the sources shown in full
  let notice = null;
  let card = null;
  let ready = false;
  let check = { running: false, queued: false, stages: [], result: null, error: null, abort: null };
  let score = { tries: 0, fooled: 0 }; // this visit's: back to zero each time the site is opened
  let fits = null; // the tricks that can change the current answer (/api/fool/tricks), null until known
  let finding = false;

  const current = () => answers[index];
  const kindName = (k) => tr(`kind.${k}`);

  // The page's parts, each drawn on its own so typing in the answer never redraws the deck or loses the caret. The
  // answer comes first (on the left), the tricks' deck beside it, with its "Apply" row inside the deck at the bottom.
  root.innerHTML = `
    <div class="fool-grid">
      <div class="rp-card fool-answer" id="fool-answer-card"></div>
      <div class="fool-left"><div id="fool-deck"></div></div>
    </div>
    <div class="fool-results" id="fool-results"></div>`;
  const deckEl = root.querySelector("#fool-deck");
  const applyEl = Object.assign(document.createElement("div"), { id: "fool-apply-row", className: "fool-apply-row" });
  const answerEl = root.querySelector("#fool-answer-card");
  const resultsEl = root.querySelector("#fool-results");

  // ---- The server's streamed answer: each line an event, the stages as they pass; "result" ends it. ----
  async function stream(url, body, onEvent, signal) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
    if (!res.ok || !res.body) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let at;
      while ((at = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, at).trim();
        buffer = buffer.slice(at + 1);
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === "error") throw new Error(event.message);
        if (event.type === "result") return event;
        onEvent(event);
      }
      if (done) throw new Error("the connection closed before the result arrived");
    }
  }

  function resetCheck() {
    check.abort?.abort();
    check = { running: false, queued: false, stages: [], result: null, error: null, abort: null };
  }

  // Which tricks can change the current answer; the cards and the button follow.
  async function loadFits() {
    const c = current();
    fits = null;
    markCards();
    if (!c || !ready) return;
    try {
      const res = await fetch(`/api/fool/tricks/${encodeURIComponent(c.id)}`);
      if (!res.ok) return;
      const body = await res.json();
      if (current()?.id !== body.answer_id) return;
      fits = new Set(body.kinds);
    } catch { /* unknown: every trick stays open */ }
    markCards();
    drawApply();
  }
  const fitsTrick = (k) => !fits || fits.has(k);

  function markCards() {
    deckEl.querySelectorAll(".cascade-card").forEach((el, i) => el.classList.toggle("unfit", !fitsTrick(KINDS[i])));
  }

  function showAnswer(i) {
    index = i;
    opened = new Set();
    text = current().answer;
    edit = null;
    notice = null;
    resetCheck();
    drawApply();
    drawAnswer();
    drawResults();
    loadFits();
  }

  // The next answer, after the current one, that the chosen trick can change.
  async function findAnswer() {
    if (finding || !answers.length) return;
    finding = true;
    drawApply();
    const kind = KINDS[trick];
    try {
      for (let step = 1; step < answers.length; step++) {
        const i = (index + step) % answers.length;
        const res = await fetch(`/api/fool/tricks/${encodeURIComponent(answers[i].id)}`);
        if (!res.ok) continue;
        if ((await res.json()).kinds.includes(kind)) { finding = false; showAnswer(i); return; }
      }
    } catch { /* leave it as it is */ }
    finding = false;
    drawApply();
  }

  async function applyTrick() {
    const c = current();
    if (!c || !ready || check.running) return;
    notice = null;
    try {
      const res = await fetch("/api/fool/edit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answer_id: c.id, kind: KINDS[trick], seed: Math.floor(Math.random() * 1000) }) });
      const body = await res.json();
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : tr("fool.trickFailed"));
      text = body.answer;
      edit = body.edit;
      resetCheck();
    } catch (e) {
      notice = e.message || tr("fool.trickFailed");
    }
    drawApply();
    drawAnswer();
    drawResults();
  }

  async function run() {
    const c = current();
    if (!c || !text.trim() || !ready || check.running) return;
    resetCheck();
    const controller = new AbortController();
    check.running = true;
    check.abort = controller;
    drawAll();
    resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    const started = performance.now();
    try {
      const result = await stream("/api/fool/check", { answer_id: c.id, answer: text }, (e) => {
        if (e.type === "queued") check.queued = true;
        if (e.type === "stage") { check.queued = false; check.stages.push({ stage: e.stage, t: e.t ?? (performance.now() - started) / 1000 }); }
        const list = resultsEl.querySelector("#fool-progress");
        if (list && window.TGReport) list.innerHTML = window.TGReport.progress(check.stages, check.queued);
      }, controller.signal);
      check.result = { ...result, text };
      if (result.edit) {
        score = { tries: score.tries + 1, fooled: score.fooled + (result.caught ? 0 : 1) };
      }
    } catch (e) {
      if (controller.signal.aborted) return;
      check.error = e.message;
    } finally {
      if (check.abort === controller) {
        check.running = false;
        check.abort = null;
        drawAll();
      }
    }
  }

  function outcome(result) {
    if (!result.edit) return { signal: "amber", title: tr("fool.noneTitle"), text: tr("fool.noneText") };
    if (result.caught && result.located) return { signal: "green", title: tr("fool.locatedTitle"), text: tr("fool.locatedText") };
    if (result.caught) return { signal: "amber", title: tr("fool.flaggedTitle"), text: tr("fool.flaggedText") };
    if (result.cautioned) return { signal: "amber", title: tr("fool.cautionedTitle"), text: tr("fool.cautionedText") };
    return { signal: "red", title: tr("fool.fooledTitle"), text: tr("fool.fooledText") };
  }

  // The project's shield (the rail's logo) in the outcome's colour: green with a tick when the lie was caught and found,
  // amber with "!" when it was only partly caught, red with a cross when it got through.
  const SHIELD = {
    green: ["#9dffc4", "#2fb36a", "#0f5a34", "#06301b", '<path d="M8.5 12l2.5 2.5 4.5-5"/>'],
    amber: ["#ffe9a8", "#e0a526", "#8a5d05", "#4a3202", '<path d="M12 7.6v5"/><path d="M12 15.9v.1"/>'],
    red: ["#ffc2c2", "#e0484d", "#8f1f1f", "#4a0b0d", '<path d="M9.2 9.2l5.6 5.6M14.8 9.2l-5.6 5.6"/>'],
  };
  function shield(signal) {
    const [top, mid, low, edge, mark] = SHIELD[signal];
    const id = `fool-shield-${signal}`;
    return `<svg class="outcome-shield" viewBox="3 1.5 19 21.5" aria-hidden="true">
      <defs><linearGradient id="${id}" x1="0.15" y1="0" x2="0.85" y2="1"><stop offset="0" stop-color="${top}"/><stop offset="0.45" stop-color="${mid}"/><stop offset="1" stop-color="${low}"/></linearGradient></defs>
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" fill="${edge}" transform="translate(0.9 1.1)"/>
      <path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" fill="url(#${id})" stroke="#ffffff" stroke-opacity="0.7" stroke-width="0.7" stroke-linejoin="round"/>
      <path d="M12 4.6l5.6 2.4" stroke="#ffffff" stroke-opacity="0.75" stroke-width="0.9" stroke-linecap="round"/>
      <g fill="none" stroke="#fffdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${mark}</g>
    </svg>`;
  }

  // ---- Drawing ----
  function drawScore() {
    if (!scoreEl) return;
    scoreEl.innerHTML = `
      <div><span class="score-n">${int(score.tries)}</span><span class="rp-small">${esc(tr("fool.tries"))}</span></div>
      <div><span class="score-n bad">${int(score.fooled)}</span><span class="rp-small">${esc(tr("fool.through"))}</span></div>`;
  }

  function drawDeck() {
    const rates = card?.fool_the_guardian?.edits;
    const n = int(KINDS.length, 2);
    window.TGCascade?.mount(deckEl, {
      height: 620,
      active: trick,
      label: tr("fool.tricks"),
      tabsLabel: tr("fool.chooseTrick"),
      announce: (i) => tr("fool.trickOf", { i: int(i + 1), n: int(KINDS.length), label: kindName(KINDS[i]) }),
      onActive: (i) => { trick = i; drawApply(); },
      cards: KINDS.map((k, i) => ({
        key: k,
        label: kindName(k),
        fill: FILL[k],
        html: `
          <div class="cascade-top"><span class="cascade-chip" dir="ltr">${esc(tr("fool.cardCount", { i: int(i + 1, 2), n }))}</span><span class="cascade-rate">${rates?.[k] ? esc(tr("fool.caughtRate", { p: pct(rates[k].detected) })) : ""}</span></div>
          <span class="cascade-unfit">${esc(tr("html.f.unfit"))}</span>
          <div><p class="cascade-kicker">${esc(tr("fool.trick", { i: int(i + 1, 2) }))}</p><h3 class="cascade-title">${esc(kindName(k))}</h3><p class="cascade-hint">${esc(tr(`fool.hint.${k}`))}</p></div>`,
      })),
    });
    deckEl.querySelector(".cascade-stage")?.appendChild(applyEl); // the Apply row sits inside the deck, over its foot
    markCards();
  }

  function drawApply() {
    const rates = card?.fool_the_guardian?.edits?.[KINDS[trick]];
    const unfit = ready && !fitsTrick(KINDS[trick]);
    applyEl.innerHTML = `
      <div class="chips">
        <button type="button" class="btn-primary" id="fool-apply" ${!ready || !current() || check.running || finding ? "disabled" : ""}>${esc(!ready ? tr("common.loadingModels") : finding ? tr("html.f.finding") : unfit ? tr("html.f.find") : tr("fool.apply", { trick: kindName(KINDS[trick]) }))}</button>
        <span class="rp-small">${rates ? esc(tr("fool.suite", { n: int(rates.n), c: pct(rates.detected), l: pct(rates.located) })) : ""}</span>
      </div>
      ${unfit && !finding ? `<p class="rp-small fool-unfit-note">${esc(tr("html.f.unfitNote"))}</p>` : ""}
      ${notice ? `<p class="rp-warn" role="alert">${esc(notice[0].toUpperCase() + notice.slice(1))}.</p>` : ""}`;
    applyEl.querySelector("#fool-apply").addEventListener("click", () => (ready && !fitsTrick(KINDS[trick]) ? findAnswer() : applyTrick()));
  }

  function editHTML() {
    if (!edit) return "";
    return `<span class="fix bad" dir="auto">${esc(edit.original ? tr("fool.edited", { a: edit.original, b: edit.new }) : tr("fool.added", { x: edit.new }))}</span>`;
  }

  function drawAnswer() {
    const c = current();
    if (!c) {
      answerEl.innerHTML = `<h4>${esc(tr("fool.loadingAnswers"))}</h4>`;
      return;
    }
    answerEl.innerHTML = `
      <h4>${esc(tr("fool.answerTitle"))}</h4>
      ${c.question ? `<p class="rp-text"><span class="rp-small">${esc(tr("fool.question"))}</span> <span dir="auto">${esc(c.question)}</span></p>` : ""}
      <div class="fool-sources">
        <h5 class="fool-sources-title">${esc(tr("fool.sources", { n: int(c.sources.length) }))}</h5>
        <ol class="fool-sources-list">${c.sources.map((s, i) => `<li class="fool-source${opened.has(i) ? " open" : ""}" data-source="${i}" tabindex="0" role="button" aria-expanded="${opened.has(i)}"><span class="mono">[${int(i + 1)}]</span><span class="fool-source-text" dir="auto">${esc(s)}</span></li>`).join("")}</ol>
      </div>
      <label class="rp-small" for="fool-answer">${esc(tr("fool.answerLabel"))}</label>
      <textarea id="fool-answer" class="code plain" dir="auto" maxlength="5000">${esc(text)}</textarea>
      <div id="fool-edit">${editHTML()}</div>
      <div class="chips" id="fool-buttons"></div>`;
    // A click opens a source in full (and closes it again); a drag that selects its words leaves it as it is.
    answerEl.querySelectorAll("[data-source]").forEach((li) => {
      const toggle = () => {
        const i = Number(li.dataset.source);
        if (opened.has(i)) opened.delete(i); else opened.add(i);
        li.classList.toggle("open", opened.has(i));
        li.setAttribute("aria-expanded", String(opened.has(i)));
      };
      li.addEventListener("click", () => { if (!String(window.getSelection() || "").trim()) toggle(); });
      li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    });
    answerEl.querySelector("#fool-answer").addEventListener("input", (e) => {
      text = e.target.value;
      edit = null;
      answerEl.querySelector("#fool-edit").innerHTML = "";
      if (check.result || check.error) { resetCheck(); drawResults(); }
      drawButtons();
    });
    drawButtons();
  }

  function drawButtons() {
    const c = current();
    const box = answerEl.querySelector("#fool-buttons");
    if (!box || !c) return;
    box.innerHTML = `
      <button type="button" class="btn-primary" data-act="check" ${!ready || check.running || !text.trim() ? "disabled" : ""}>${esc(check.running ? tr("fool.checking") : ready ? tr("fool.check") : tr("common.loadingModels"))}</button>
      <button type="button" class="btn-ghost" data-act="undo" ${check.running || text === c.answer ? "disabled" : ""}>${esc(tr("fool.undo"))}</button>
      <button type="button" class="btn-ghost" data-act="another" ${check.running || answers.length < 2 ? "disabled" : ""}>${esc(tr("fool.another"))}</button>`;
    box.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.act === "check") run();
      if (b.dataset.act === "undo") { text = c.answer; edit = null; resetCheck(); drawAnswer(); drawResults(); }
      if (b.dataset.act === "another") showAnswer((index + 1) % answers.length);
    }));
  }

  function drawResults() {
    const r = check.result;
    const o = r ? outcome(r) : null;
    resultsEl.innerHTML = `
      ${check.running ? `<div class="rp-card"><h4>${esc(tr("fool.checkingEdit"))}</h4><div id="fool-progress">${window.TGReport ? window.TGReport.progress(check.stages, check.queued) : ""}</div></div>` : ""}
      ${check.error ? `<p class="rp-warn" role="alert">${esc(tr("common.checkFailed", { error: check.error }))}</p>` : ""}
      ${r && o ? `
        <div class="rp-card outcome ${o.signal}" aria-live="polite">
          <div class="outcome-head">${shield(o.signal)}
            <div><span class="outcome-word">${esc(o.signal === "green" ? tr("fool.signalCaught") : o.signal === "red" ? tr("fool.signalThrough") : tr("fool.signalPartly"))}</span>
              <h3 class="outcome-title">${esc(o.title)}</h3></div></div>
          <p class="rp-text">${esc(o.text)}</p>
          <p class="mono rp-small">${esc(tr("fool.meta", { r: num(r.report.risk), d: num(r.report.response_threshold), s: num(r.seconds, 1) }))}${card?.fool_the_guardian ? esc(tr("fool.controls", { p: pct(card.fool_the_guardian.controls_flagged) })) : ""}</p>
        </div>
        <div id="fool-report"></div>` : ""}`;
    const report = resultsEl.querySelector("#fool-report");
    if (report && window.TGReport && r) window.TGReport.render(report, { text: r.text, report: r.report });
  }

  function drawAll() {
    drawScore();
    drawApply();
    drawButtons();
    drawResults();
  }

  function drawEverything() {
    drawScore();
    drawDeck();
    drawApply();
    drawAnswer();
    drawResults();
  }

  // The models' state: tricks and checks wait until they are ready.
  async function poll() {
    try {
      const h = await (await fetch("/api/health", { cache: "no-store" })).json();
      if (h.state === "ready") { ready = true; drawApply(); drawButtons(); loadFits(); return; }
    } catch { /* not up yet */ }
    setTimeout(poll, 2000);
  }

  fetch("/api/fool/answers").then((r) => r.json()).then((list) => {
    answers = list || [];
    index = Math.floor(Math.random() * Math.max(1, answers.length));
    text = current()?.answer || "";
    drawApply();
    drawAnswer();
    loadFits();
  }).catch(() => {});
  fetch("/api/model-card").then((r) => r.json()).then((c) => { card = c; drawDeck(); drawApply(); }).catch(() => {});
  if (window.TG) window.TG.onLang(drawEverything);
  drawEverything();
  poll();
})();
