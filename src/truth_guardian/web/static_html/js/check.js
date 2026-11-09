// Check an answer, as on the previous site's page of the same name (pages/Analyze.tsx, components/InputForm.tsx,
// components/report/HealRounds.tsx): try a ready-made example from the deck, or give your own question, sources (typed
// or read from files) and the AI answer; the check is streamed with each stage of the engine as it passes; then the
// Guardian's report in full (js/report.js), downloadable, and "Heal this answer": its fixes applied round by round, each
// round checked again, with what changed and why and the risk after each round.
// "Truth Guardian check" under the chat brings the chat's last answer here with its report (TGCheck.showChat).
// Server: /api/examples, /api/examples/{id}, /api/health (profiles), /api/documents, /api/analyze, /api/heal, /api/model-card.

(() => {
  const root = document.getElementById("check-tab");
  if (!root) return;
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const has = (key) => tr(key) !== key;
  const tp = (key, n, vars) => tr(n === 1 && has(`${key}.one`) ? `${key}.one` : `${key}.other`, { n: int(n), ...vars });
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const lang = () => (window.TG ? window.TG.lang : "en");
  const loc = () => ({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang();
  const num = (x, d = 2) => (x == null ? "–" : new Intl.NumberFormat(loc(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(x));
  const int = (x) => new Intl.NumberFormat(loc()).format(x);
  const pct = (x) => (x == null ? "–" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 0 }).format(x));
  const label = (family, key) => (has(`${family}.${key}`) ? tr(`${family}.${key}`) : String(key).replace(/_/g, " "));
  const MAX_SOURCES = 10;
  const MAX_FILE_BYTES = 10_000_000;
  const ACCEPT = ".pdf,.docx,.txt,.md,.markdown,.html,.htm,.csv,.json,.log";
  const LONG_SOURCES = 60_000;
  // The previous site's card colours for the examples deck (components/ExamplesDeck.tsx).
  const GLOW = ["#fb7185", "#c4b5fd", "#a78bfa", "#fbbf24", "#34d399", "#60a5fa", "#2dd4bf", "#f472b6", "#fb923c", "#93c5fd", "#5eead4", "#e879f9"];
  const exampleTitle = (e) => (has(`example.${e.id}.title`) ? tr(`example.${e.id}.title`) : e.title);
  const exampleAbout = (e) => (has(`example.${e.id}.about`) ? tr(`example.${e.id}.about`) : e.about);

  const blank = () => ({ question: "", sources: [""], names: [null], answer: "", task: "qa", profile: "", exampleId: null });
  let examples = [];
  let input = blank();
  let example = null; // the picked example in full (its annotators' verdict is shown with the report)
  let view = null; // { report, seconds, cached, input, gold, chat }
  let ready = false;
  let profiles = [];
  let card = null;
  let check = { running: false, queued: false, stages: [], error: null, abort: null };
  let heal = { running: false, queued: false, checks: 0, result: null, error: null, abort: null, round: 0 };
  let note = null; // { text, bad } after files are read
  let reading = false;
  let picking = 0;

  // ---- The server's streamed answers: each line an event; "result" ends it. ----
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

  function body(value) {
    if (value.exampleId) return { example_id: value.exampleId };
    const kept = value.sources.map((s, i) => ({ text: s.trim(), name: value.names[i] ? value.names[i].split(" · ")[0] : null })).filter((s) => s.text);
    return {
      question: value.question.trim() || null,
      sources: kept.map((s) => s.text),
      source_names: kept.map((s) => s.name),
      answer: value.answer,
      task: value.task,
      profile: value.profile || null,
    };
  }

  function stopHeal() {
    heal.abort?.abort();
    heal = { running: false, queued: false, checks: 0, result: null, error: null, abort: null, round: 0 };
  }

  async function run(value, gold = null) {
    stopHeal();
    check.abort?.abort();
    const controller = new AbortController();
    check = { running: true, queued: false, stages: [], error: null, abort: controller };
    draw();
    root.querySelector(".ck-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const started = performance.now();
      const result = await stream("/api/analyze", body(value), (e) => {
        if (e.type === "queued") check.queued = true;
        if (e.type === "stage") { check.queued = false; check.stages.push({ stage: e.stage, t: e.t ?? (performance.now() - started) / 1000 }); }
        drawProgress();
      }, controller.signal);
      view = { report: result.report, seconds: result.seconds ?? (performance.now() - started) / 1000, cached: !!result.cached, input: { ...value, sources: [...value.sources] }, gold, chat: null };
    } catch (e) {
      if (controller.signal.aborted) return;
      check.error = e.message;
    } finally {
      if (check.abort === controller) { check.running = false; check.abort = null; draw(); }
    }
  }

  async function startHeal() {
    if (!view) return;
    heal.abort?.abort();
    const controller = new AbortController();
    heal = { running: true, queued: false, checks: 0, result: null, error: null, abort: controller, round: 0 };
    draw();
    try {
      const result = await stream("/api/heal", body(view.input), (e) => {
        if (e.type === "queued") heal.queued = true;
        if (e.type === "check") { heal.queued = false; heal.checks += 1; }
        drawHealing();
      }, controller.signal);
      heal.result = result;
      heal.round = result.rounds.length - 1;
    } catch (e) {
      if (controller.signal.aborted) return;
      heal.error = e.message;
    } finally {
      if (heal.abort === controller) { heal.running = false; heal.abort = null; draw(); }
    }
  }

  // Only the latest click counts: an earlier example that answers late is ignored and its check cancelled.
  async function pick(id) {
    const turn = ++picking;
    try {
      const res = await fetch(`/api/examples/${encodeURIComponent(id)}`);
      const { example: e, report } = await res.json();
      if (turn !== picking) return;
      const task = ["qa", "summary", "data2text"].includes(e.task) ? e.task : "other";
      const sources = e.sources.length ? [...e.sources] : [""];
      input = { question: e.question ?? "", sources, names: sources.map(() => null), answer: e.answer, task, profile: e.profile ?? "", exampleId: e.id };
      example = e;
      if (report) {
        check.abort?.abort();
        check = { running: false, queued: false, stages: [], error: null, abort: null };
        stopHeal();
        view = { report, seconds: 0, cached: true, input: { ...input }, gold: e, chat: null };
        draw();
        root.querySelector(".ck-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
      } else if (ready) {
        await run(input, e);
      } else {
        draw();
      }
    } catch (err) {
      console.error(err);
    }
  }

  // ---- Files into sources: /api/documents reads a PDF, Word, HTML or text file into parts. ----
  async function base64(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(binary);
  }

  function place(parts, labels) {
    let placed = 0;
    for (let k = 0; k < parts.length; k++) {
      const empty = input.sources.findIndex((s) => !s.trim());
      if (empty >= 0) { input.sources[empty] = parts[k]; input.names[empty] = labels[k]; }
      else if (input.sources.length < MAX_SOURCES) { input.sources.push(parts[k]); input.names.push(labels[k]); }
      else break;
      placed++;
    }
    input.exampleId = null;
    return placed;
  }

  async function addFiles(files) {
    if (!files.length) return;
    reading = true;
    note = null;
    draw();
    const done = [];
    let short = false;
    try {
      for (const file of files) {
        if (file.size > MAX_FILE_BYTES) { note = { text: tr("form.tooBig", { name: file.name, mb: num(file.size / 1e6, 1) }), bad: true }; continue; }
        let read;
        try {
          const res = await fetch("/api/documents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: file.name, data: await base64(file) }) });
          if (!res.ok) {
            let detail = `HTTP ${res.status}`;
            try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
            throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
          }
          read = await res.json();
        } catch (e) {
          note = { text: tr("form.fileError", { name: file.name, error: e.message }), bad: true };
          continue;
        }
        const n = read.parts.length;
        const labels = read.parts.map((_, k) => (n > 1 ? `${file.name} · ${k + 1}/${n}` : file.name));
        const placed = place(read.parts, labels);
        const size = `${read.pages ? tp("form.pages", read.pages) : ""}${tr("form.chars", { n: int(read.chars) })}`;
        done.push(placed === n ? tp("form.addedAs", n, { name: file.name, size }) : tr("form.partial", { placed: int(placed), n: int(n), name: file.name, max: int(MAX_SOURCES) }));
        if (placed < n) { short = true; break; }
      }
      if (done.length) note = { text: tr("form.added", { list: done.reduce((a, b) => tr("form.list", { a, b })) }), bad: short };
    } finally {
      reading = false;
      draw();
    }
  }

  // ---- Drawing ----
  // The ready-made examples as the previous site's coverflow deck (js/spectra.js), each card in its own colour; it
  // waits while a check runs or a report is shown, as there.
  function drawDeck() {
    const el = root.querySelector("#ck-deck");
    if (!el || !window.TGSpectra) return;
    const n = examples.length;
    window.TGSpectra.mount(el, {
      label: tr("examples.button"),
      browse: tr("deck.browse"),
      cta: tr("examples.cta"),
      itemLabel: (i) => tr("deck.item", { label: exampleTitle(examples[i]), i: int(i + 1), n: int(n) }),
      paused: () => check.running || heal.running || !!view,
      onOpen: (i) => pick(examples[i].id),
      cards: examples.map((e, i) => {
        const glow = GLOW[i % GLOW.length];
        return {
          key: e.id,
          label: exampleTitle(e),
          glow,
          c1: `color-mix(in oklab, ${glow} 48%, #2c3a34)`,
          c2: "#1f2a25",
          html: `
            <span class="spectra-chip" dir="ltr">${esc(new Intl.NumberFormat(loc(), { minimumIntegerDigits: 2 }).format(i + 1))}</span>
            <span class="spectra-text">
              ${has(`task.${e.task}`) ? `<span class="spectra-kicker">${esc(tr(`task.${e.task}`))}</span>` : ""}
              <span class="spectra-title" dir="auto">${esc(exampleTitle(e))}</span>
              <span class="spectra-about" dir="auto">${esc(exampleAbout(e))}</span>
            </span>`,
        };
      }),
    });
  }

  function formHTML() {
    const busy = check.running || heal.running;
    const ok = input.answer.trim() && (input.sources.some((s) => s.trim()) || input.question.trim());
    const total = input.sources.reduce((n, s) => n + s.length, 0);
    return `
      <form class="ck-form" id="ck-form" novalidate>
        <label class="field">${esc(tr("form.question"))} <span class="rp-small">${esc(tr("form.questionHint"))}</span>
          <input id="ck-question" dir="auto" maxlength="1000" value="${esc(input.question)}" placeholder="${esc(tr("form.questionPlaceholder"))}">
        </label>
        <fieldset class="ck-sources" id="ck-sources">
          <legend class="field">${esc(tr("form.sources"))}</legend>
          ${input.sources.map((s, i) => `
            <div class="ck-source">
              <span class="ck-n mono" aria-hidden="true">[${int(i + 1)}]</span>
              <div class="field">
                ${input.names[i] ? `<span class="rp-small mono" dir="auto">${esc(tr("form.from", { name: input.names[i] }))}</span>` : ""}
                <textarea data-source="${i}" dir="auto" rows="3" maxlength="20000" aria-label="${esc(tr("form.source", { i: int(i + 1) }))}" placeholder="${esc(tr("form.sourcePlaceholder"))}">${esc(s)}</textarea>
              </div>
              ${input.sources.length > 1 ? `<button type="button" class="ck-remove" data-remove="${i}" aria-label="${esc(tr("form.remove", { i: int(i + 1) }))}">×</button>` : ""}
            </div>`).join("")}
          <div class="chips ck-indent">
            ${input.sources.length < MAX_SOURCES ? `<button type="button" class="chip" id="ck-add">${esc(tr("form.add"))}</button>` : ""}
            <input type="file" id="ck-files" multiple accept="${ACCEPT}" hidden>
            <label for="ck-files" class="chip file-btn${reading ? " off" : ""}">${esc(reading ? tr("form.reading") : tr("form.addFiles"))}</label>
            <span class="rp-small">${esc(tr("form.fileTypes"))}</span>
          </div>
          ${note ? `<p class="rp-small ck-indent${note.bad ? " bad" : ""}" role="status">${esc(note.text)}</p>` : ""}
          ${total > LONG_SOURCES ? `<p class="rp-small ck-indent">${esc(tr("form.long", { n: int(total) }))}</p>` : ""}
        </fieldset>
        <label class="field">${esc(tr("form.answer"))}
          <textarea id="ck-answer" dir="auto" rows="5" maxlength="5000" placeholder="${esc(tr("form.answerPlaceholder"))}">${esc(input.answer)}</textarea>
        </label>
        <div class="ck-foot">
          <label class="field">${esc(tr("form.task"))}
            <select id="ck-task">${["qa", "summary", "data2text", "other"].map((t) => `<option value="${t}"${input.task === t ? " selected" : ""}>${esc(label("task", t))}</option>`).join("")}</select>
          </label>
          ${profiles.length ? `<label class="field">${esc(tr("form.profile"))}
            <select id="ck-profile"><option value="">${esc(tr("form.profileDefault"))}</option>${profiles.map((p) => `<option value="${esc(p)}"${input.profile === p ? " selected" : ""}>${esc(p)}</option>`).join("")}</select>
          </label>` : ""}
          <button type="submit" class="btn-primary ck-submit" ${!ok || busy || !ready ? "disabled" : ""}>${esc(ready ? tr("analyze.submit") : tr("common.loadingModels"))}</button>
        </div>
        <span class="rp-small">${esc(tr("form.hint"))}</span>
      </form>`;
  }

  function progressHTML() {
    return `
      <div class="rp-grid">
        <div class="rp-card ck-checking"><span class="ck-pulse" aria-hidden="true"></span><span class="mono rp-small">${esc(tr("analyze.checking"))}</span></div>
        <div class="rp-card"><h4>${esc(tr("analyze.progress"))}</h4>${window.TGReport ? window.TGReport.progress(check.stages, check.queued) : ""}</div>
      </div>`;
  }

  function goldHTML() {
    const g = view.gold;
    if (!g?.gold) return "";
    const n = g.gold_spans?.length || 0;
    return `<p class="rp-small ck-gold">${esc(tr("analyze.goldPre"))}<b>${esc(label("verdict", g.gold))}</b>${n ? esc(tp("analyze.goldSpans", n)) : ""}${esc(tr("analyze.goldPost"))}</p>`;
  }

  // The previous answer with one round's changes shown inline: removed text struck through, new text marked.
  function diffHTML(before, changes) {
    let html = "";
    let at = 0;
    for (const c of [...changes].sort((a, b) => a.start - b.start)) {
      if (c.start > at) html += esc(before.slice(at, c.start));
      if (c.original) html += `<del title="${esc(c.reason)}">${esc(c.original)}</del>`;
      if (c.new) html += `<ins title="${esc(c.reason)}">${esc(c.new)}</ins>`;
      at = Math.max(at, c.end);
    }
    return html + esc(before.slice(at));
  }

  function riskHTML(r) {
    const risk = r.domain?.calibrated_risk ?? r.risk;
    return `<div class="gauge"><span class="gauge-fill" style="width:${(risk * 100).toFixed(1)}%"></span></div>`;
  }

  function healHTML() {
    const res = heal.result;
    const rounds = res.rounds;
    const i = heal.round;
    const shown = rounds[i];
    const before = i > 0 ? rounds[i - 1].answer : null;
    const measured = card?.healing?.hallucinated;
    return `
      <div class="ck-heal">
        <div class="ck-heal-head">
          <h3 class="section-title small">${esc(tr("heal.title"))}</h3>
          <p class="section-text">${esc(tr("heal.lead"))}</p>
        </div>
        <div class="ck-bar">
          <div class="chips" role="tablist" aria-label="${esc(tr("heal.rounds"))}">${rounds.map((_, k) => `<button type="button" class="chip" role="tab" data-round="${k}" aria-selected="${k === i}" aria-pressed="${k === i}">${esc(k === 0 ? tr("heal.original") : tr("heal.round", { i: int(k) }))}</button>`).join("")}</div>
          <div class="chips">
            <button type="button" class="btn-ghost" data-act="copy">${esc(tr("heal.copy"))}</button>
            <button type="button" class="btn-ghost" data-act="heal-json">${esc(tr("common.download"))}</button>
          </div>
        </div>
        <div class="rp-grid">
          <div class="rp-main">
            <div class="rp-card"><h4>${esc(i === 0 ? tr("heal.originalAnswer") : tp("heal.roundTitle", shown.changes.length, { i: int(i) }))}</h4>
              ${i === 0 || !before ? `<div id="ck-heal-answer"></div>` : `<p class="rp-answer ck-diff" dir="auto">${diffHTML(before, shown.changes)}</p>`}
            </div>
            ${i > 0 ? `<div class="rp-card"><h4>${esc(tr("heal.why"))}</h4><ul class="ck-why">${shown.changes.map((c) => `<li><span class="mono" dir="auto">${esc(c.new ? `“${c.original}” → “${c.new}”` : `− “${c.original.length > 120 ? `${c.original.slice(0, 117)}…` : c.original}”`)}</span><span class="rp-small" dir="auto">${esc(c.reason ? c.reason[0].toUpperCase() + c.reason.slice(1) : "")}.</span></li>`).join("")}</ul></div>` : ""}
            ${i === rounds.length - 1 && i > 0 ? `<div class="rp-card"><h4>${esc(tr("heal.healed"))}</h4><p class="rp-answer" dir="auto">${esc(res.answer)}</p>${shown.report.verdict !== "grounded" ? `<p class="rp-warn">${esc(tr("heal.stopped"))}</p>` : ""}</div>` : ""}
          </div>
          <aside class="rp-side">
            <div class="rp-card"><h4>${esc(tr("heal.riskRounds"))}</h4>
              <ol class="ck-rounds">${rounds.map((r, k) => `
                <li><button type="button" class="ck-round${k === i ? " on" : ""}" data-round="${k}">
                  <span class="ck-round-row"><span>${esc(k === 0 ? tr("heal.original") : tr("heal.round", { i: int(k) }))}</span>
                    <span class="ck-round-verdict">${r.report.card?.grade ? `<span class="grade g${r.report.card.grade}">${r.report.card.grade}</span>` : ""}<span><b class="v-${r.report.verdict}">${esc(label("verdict", r.report.verdict))}</b><span class="mono rp-small">${esc(tr("heal.risk", { r: num(r.report.risk) }))}</span></span></span></span>
                  ${riskHTML(r.report)}
                </button></li>`).join("")}</ol>
            </div>
            ${measured ? `<div class="rp-card"><h4>${esc(tr("heal.measuredTitle"))}</h4><p class="rp-small">${esc(tr("heal.measured", { n: int(measured.n), a: pct(measured.grounded_after_among_flagged), b: pct(measured.edit_recall), c: pct(measured.edit_precision) }))}</p></div>` : ""}
          </aside>
        </div>
      </div>`;
  }

  function healingHTML() {
    return `<div class="rp-card" id="ck-healing"><h4>${esc(tr("heal.healing"))}</h4>
      <p class="rp-small" aria-live="polite">${esc(heal.queued ? tr("panels.waiting") : heal.checks <= 1 ? tr("heal.checkingOriginal") : tr("heal.checkingRound", { i: int(heal.checks - 1) }))}</p>
      <div class="ck-slide"><span></span></div></div>`;
  }

  function resultsHTML() {
    if (!view) return "";
    const state = check.running ? tr("analyze.previous") : view.cached ? tr("analyze.readyMade") : tr("analyze.checkedIn", { s: num(view.seconds, 1) });
    const healable = !view.chat && view.report.verdict !== "grounded";
    return `
      <div class="ck-view${check.running ? " dim" : ""}" aria-busy="${check.running}">
        ${view.chat ? `<p class="section-note">${esc(tr("html.c.fromChat", { q: view.chat }))}</p>` : ""}
        <div class="ck-bar">
          <span class="mono rp-small">${esc(view.chat ? (view.report.model_version ? `model ${view.report.model_version}` : "") : tr("analyze.model", { state, v: view.report.model_version ?? "" }))}</span>
          <div class="chips">
            ${heal.result ? `<button type="button" class="btn-ghost" data-act="back">${esc(tr("heal.showReport"))}</button>` : `
              <button type="button" class="btn-ghost" data-act="json">${esc(tr("analyze.download"))}</button>
              ${healable ? `<button type="button" class="btn-primary" data-act="heal" ${heal.running || check.running ? "disabled" : ""}>${esc(tr("analyze.heal"))}</button>` : ""}`}
          </div>
        </div>
        ${heal.running ? healingHTML() : ""}
        ${heal.error ? `<p class="rp-warn" role="alert">${esc(tr("heal.failed", { error: heal.error }))}</p>` : ""}
        ${heal.result ? healHTML() : `${goldHTML()}<div id="ck-report"></div>`}
      </div>`;
  }

  function draw() {
    const focus = document.activeElement && root.contains(document.activeElement) ? document.activeElement.id || document.activeElement.dataset?.source : null;
    root.querySelector("#ck-try-label").textContent = tr("analyze.try");
    root.querySelector("#ck-form-card").innerHTML = `<h4>${esc(tr("common.orOwn"))}</h4>${formHTML()}`;
    root.querySelector(".ck-results").innerHTML = `
        ${check.running ? `<div id="ck-progress">${progressHTML()}</div>` : ""}
        ${check.error ? `<p class="rp-warn" role="alert">${esc(tr("common.checkFailed", { error: check.error }))}</p>` : ""}
        ${resultsHTML()}`;
    wire();
    const reportEl = root.querySelector("#ck-report");
    if (reportEl && view && window.TGReport) window.TGReport.render(reportEl, { text: view.input.answer, report: view.report });
    const healAnswer = root.querySelector("#ck-heal-answer");
    if (healAnswer && heal.result && window.TGReport) {
      window.TGReport.render(healAnswer, { text: heal.result.rounds[0].answer, report: heal.result.rounds[0].report }, { compact: true });
      healAnswer.querySelector(".rp-verdict")?.remove();
    }
    if (focus) {
      const el = root.querySelector(`#${CSS.escape(focus)}`) || root.querySelector(`[data-source="${focus}"]`);
      if (el) { el.focus(); if (el.setSelectionRange && typeof el.value === "string") el.setSelectionRange(el.value.length, el.value.length); }
    }
  }

  // Only the parts that change while a check or a heal streams, so the form keeps its focus.
  function drawProgress() {
    const el = root.querySelector("#ck-progress");
    if (el) el.innerHTML = progressHTML();
  }
  function drawHealing() {
    const el = root.querySelector("#ck-healing");
    if (el) el.outerHTML = healingHTML();
  }

  // Typing changes the input without drawing the whole tab again; only the submit button's state follows it.
  function refreshSubmit() {
    const btn = root.querySelector(".ck-submit");
    const ok = input.answer.trim() && (input.sources.some((s) => s.trim()) || input.question.trim());
    if (btn) btn.disabled = !ok || check.running || heal.running || !ready;
  }

  function download(name, data) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
  }

  function wire() {
    const form = root.querySelector("#ck-form");
    const edit = () => { input.exampleId = null; refreshSubmit(); };
    root.querySelector("#ck-question")?.addEventListener("input", (e) => { input.question = e.target.value; edit(); });
    root.querySelector("#ck-answer")?.addEventListener("input", (e) => { input.answer = e.target.value; edit(); });
    root.querySelectorAll("[data-source]").forEach((t) => t.addEventListener("input", (e) => { input.sources[Number(t.dataset.source)] = e.target.value; edit(); }));
    root.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => {
      const i = Number(b.dataset.remove);
      input.sources.splice(i, 1);
      input.names.splice(i, 1);
      input.exampleId = null;
      draw();
    }));
    root.querySelector("#ck-add")?.addEventListener("click", () => { input.sources.push(""); input.names.push(null); input.exampleId = null; draw(); });
    root.querySelector("#ck-files")?.addEventListener("change", (e) => addFiles([...(e.target.files || [])]));
    root.querySelector("#ck-task")?.addEventListener("change", (e) => { input.task = e.target.value; input.exampleId = null; });
    root.querySelector("#ck-profile")?.addEventListener("change", (e) => { input.profile = e.target.value; input.exampleId = null; });
    const sources = root.querySelector("#ck-sources");
    sources?.addEventListener("dragover", (e) => { if (e.dataTransfer?.types.includes("Files")) { e.preventDefault(); sources.classList.add("drop"); } });
    sources?.addEventListener("dragleave", (e) => { if (!sources.contains(e.relatedTarget)) sources.classList.remove("drop"); });
    sources?.addEventListener("drop", (e) => { e.preventDefault(); sources.classList.remove("drop"); addFiles([...e.dataTransfer.files]); });
    const submit = () => {
      const ok = input.answer.trim() && (input.sources.some((s) => s.trim()) || input.question.trim());
      if (!ok || check.running || heal.running || !ready) return;
      picking++;
      run(input, example && example.id === input.exampleId ? example : null);
    };
    form?.addEventListener("submit", (e) => { e.preventDefault(); submit(); });
    form?.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); } });
    root.querySelectorAll("[data-round]").forEach((b) => b.addEventListener("click", () => { heal.round = Number(b.dataset.round); draw(); }));
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
      const act = b.dataset.act;
      if (act === "json") download(`truth-guardian-report-${view.report.id ?? "answer"}.json`, { input: body(view.input), report: view.report });
      if (act === "heal") startHeal();
      if (act === "back") { stopHeal(); draw(); }
      if (act === "copy") navigator.clipboard?.writeText(heal.result.answer);
      if (act === "heal-json") download("truth-guardian-healing.json", { input: body(view.input), healing: heal.result });
    }));
  }

  // The chat's last answer and its report, brought here by "Truth Guardian check" (js/chat.js).
  function showChat(question, answer) {
    if (!answer?.report) return;
    check.abort?.abort();
    check = { running: false, queued: false, stages: [], error: null, abort: null };
    stopHeal();
    const sources = (answer.citations || []).map((c) => c.text);
    view = { report: answer.report, seconds: 0, cached: true, input: { ...blank(), question, answer: answer.text, sources: sources.length ? sources : [""] }, gold: null, chat: question };
    draw();
  }
  window.TGCheck = { showChat };

  // The models' state: the check waits until they are ready, and the domain profiles come with it.
  async function poll() {
    try {
      const h = await (await fetch("/api/health", { cache: "no-store" })).json();
      profiles = h.profiles || [];
      if (h.state === "ready") { ready = true; draw(); return; }
    } catch { /* not up yet */ }
    setTimeout(poll, 2000);
  }

  // The page's parts: the deck stays mounted (drawn again only for new examples or a new language), so checking,
  // typing and reports never restart it; the form and the results are drawn by draw().
  root.innerHTML = `
    <div class="ck-top">
      <div class="ck-try"><h4 class="ck-label" id="ck-try-label"></h4><div id="ck-deck"></div></div>
      <div class="rp-card ck-form-card" id="ck-form-card"></div>
    </div>
    <div class="ck-results"></div>`;

  fetch("/api/examples").then((r) => r.json()).then((e) => { examples = e.answers || []; drawDeck(); draw(); }).catch(() => {});
  fetch("/api/model-card").then((r) => r.json()).then((c) => { card = c; }).catch(() => {});
  if (window.TG) window.TG.onLang(() => { drawDeck(); draw(); });
  draw();
  poll();
})();
