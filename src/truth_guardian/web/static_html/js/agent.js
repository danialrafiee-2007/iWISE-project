// Check an agent, as on the previous site's agent page (pages/Agent.tsx): pick a ready-made agent run or paste one's
// steps, choose how strict the live Guardian is, and watch the steps arrive one by one; each is checked only against the
// question and the tool outputs before it, and the Guardian stops the run at the step where it would have stepped in.
// Then the tracer's suspicion for every step, the final answer's report, and how the stopping was measured.
// The steps are drawn as the Guardian's path (D-220): a rail down the steps with a shield on each step it has checked,
// green where the step passed, amber for a warning, red where it stopped the run, the rail cut under the stop; the
// step just reached lands on the rail as the rail fills down to it.
// Server: /api/examples (the agents), /api/examples/{id}, /api/agent (streamed, its result is the report).

(() => {
  const root = document.getElementById("agent-tab");
  if (!root) return;
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const has = (key) => tr(key) !== key;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const lang = () => (window.TG ? window.TG.lang : "en");
  const loc = () => ({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang();
  const num = (x, d = 2) => (x == null ? "–" : new Intl.NumberFormat(loc(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(x));
  const int = (x) => new Intl.NumberFormat(loc()).format(x);
  const pct = (x) => (x == null ? "–" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 0 }).format(x));
  const short = (text, n = 600) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);
  const STEP_MS = 1400;
  const SAMPLE = {
    question: "When did the Marlow Public Library open, and who designed it?",
    steps: [
      { step: 1, kind: "action", content: "call search('opening year of the Marlow Public Library')", observation: "The Marlow Public Library opened in 1932 and holds about 40,000 books." },
      { step: 2, kind: "thought", content: "The library opened in 1932. The question also asks who designed the building." },
      { step: 3, kind: "thought", content: "The building was designed by the architect Helen Ward." },
      { step: 4, kind: "answer", content: "The Marlow Public Library opened in 1932; its building was designed by Helen Ward." },
    ],
  };

  let examples = [];
  let current = null; // the chosen example's id
  let policy = "strict";
  let run = null; // { question, steps, answer, report }
  let shown = 0;
  let playing = false;
  let timer = 0;
  let busy = false;
  let error = null;
  let card = null;
  let custom = JSON.stringify(SAMPLE, null, 2);
  let drawnShown = 0; // how many steps the last drawing showed: the ones after it are the steps just reached

  // The path's marks, drawn for this site: the shield (its outline as on the rail's logo) with a tick, a bar or "!",
  // and a small sign for each kind of step.
  const SHIELD = '<path class="gp-shield-body" d="M12 2.6l7.4 3.1v5.4c0 4.7-3.1 8.6-7.4 10.4-4.3-1.8-7.4-5.7-7.4-10.4V5.7z"/>';
  const MARK = { pass: '<path d="M8.6 12.1l2.4 2.4 4.4-4.8"/>', warn: '<path d="M12 7.6v5.2M12 15.9v.2"/>', stop: '<path d="M8.6 11.9h6.8"/>' };
  const KIND = {
    action: '<path d="M14.5 4.5a4.5 4.5 0 0 0-4.2 6.1L4.5 16.4l3.1 3.1 5.8-5.8a4.5 4.5 0 0 0 6.1-4.2l-2.6 1.1-2.4-.8-.8-2.4z"/>',
    thought: '<path d="M4.5 6.5h15v9.5h-8.5l-4 3.2V16h-2.5z"/><path d="M8.5 11.2h.1M12 11.2h.1M15.5 11.2h.1"/>',
    answer: '<path d="M6.5 20.5v-16M6.5 5h11l-2.2 3.8 2.2 3.8h-11"/>',
    observation: '<path d="M2.8 12s3.4-5.8 9.2-5.8 9.2 5.8 9.2 5.8-3.4 5.8-9.2 5.8S2.8 12 2.8 12z"/><circle cx="12" cy="12" r="2.4"/>',
  };
  const icon = (paths, cls) => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;

  const kindName = (k) => (has(`agent.kind.${k}`) ? tr(`agent.kind.${k}`) : k);
  const exampleTitle = (e) => (has(`example.${e.id}.title`) ? tr(`example.${e.id}.title`) : e.title);
  const exampleAbout = (e) => (has(`example.${e.id}.about`) ? tr(`example.${e.id}.about`) : e.about);

  async function stream(url, payload) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const text = await res.text();
    let result = null;
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "error") throw new Error(event.message);
      if (event.type === "result") result = event;
    }
    return result;
  }

  async function start(body, steps, question, answer) {
    clearTimeout(timer);
    busy = true;
    error = null;
    run = null;
    shown = 0;
    drawnShown = 0;
    playing = false;
    draw();
    try {
      const result = await stream("/api/agent", { ...body, policy });
      run = { question, steps, answer, report: result.report };
      playing = true;
      tick();
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
      draw();
    }
  }

  const agent = () => run?.report?.agent;
  const stopIndex = () => {
    const at = agent()?.guardian_stop;
    return at == null ? -1 : run.steps.findIndex((s) => s.step === at);
  };

  // Plays the steps one by one and halts after the step where the Guardian stops the run, as the previous site did.
  function tick() {
    clearTimeout(timer);
    if (!playing || !run) return;
    const stop = stopIndex();
    if (shown >= run.steps.length || (stop >= 0 && shown === stop + 1)) {
      playing = false;
      draw();
      return;
    }
    timer = setTimeout(() => {
      shown += 1;
      draw();
      tick();
    }, shown === 0 ? 300 : STEP_MS);
  }

  async function pick(id) {
    current = id;
    const res = await fetch(`/api/examples/${encodeURIComponent(id)}`);
    const { example: e } = await res.json();
    await start({ example_id: id }, e.agent_steps, e.question ?? "", e.answer);
  }

  function runCustom() {
    try {
      const parsed = JSON.parse(custom);
      if (!Array.isArray(parsed.steps) || !parsed.steps.length) throw new Error(tr("agent.stepsError"));
      current = null;
      const answer = parsed.answer ?? [...parsed.steps].reverse().find((s) => s.kind === "answer")?.content ?? "";
      start({ question: parsed.question ?? null, steps: parsed.steps, answer: parsed.answer ?? null }, parsed.steps, parsed.question ?? "", answer);
    } catch (e) {
      error = e.message;
      draw();
    }
  }

  // The Guardian's path: one row per step, the rail and its mark on the inline start, the step's card beside it.
  function pathHTML(a, stop, finished) {
    const alertFor = (step) => a?.alerts?.find((x) => x.step === step);
    const n = run.steps.length;
    const titleOf = (s, alert) => {
      if (alert) return tr(alert.level === "stop" ? "agent.titleStop" : "agent.titleWarn");
      if (s.kind === "action") return tr("agent.titleAction");
      if (s.kind === "answer") return tr("agent.titleAnswer");
      if (s.kind === "thought") return tr("agent.titleReason");
      return kindName(s.kind);
    };
    return `<ol class="gp-path">${run.steps.map((s, i) => {
      const alert = alertFor(s.step);
      const reached = i < shown;
      const skipped = stop >= 0 && i > stop;
      const state = !reached ? "ahead" : skipped ? "skipped" : alert?.level === "stop" ? "stop" : alert?.level === "warning" ? "warn" : "pass";
      // The rail under this step: walked (both ends reached), being walked (the Guardian heads for the next step), cut
      // under a stop, or not yet.
      const line = i === n - 1 ? "" : state === "stop" ? "line-cut" : reached && i + 1 < shown && !skipped ? "line-done"
        : reached && !skipped && playing && i === shown - 1 ? "line-next" : "line-ahead";
      const fresh = reached && i >= drawnShown;
      const filling = i + 1 < shown && i + 1 >= drawnShown && line === "line-done";
      const front = reached && i === shown - 1 && !finished && (playing || state === "stop");
      const tag = !reached ? tr("agent.notYet") : skipped ? tr("agent.wouldNot")
        : alert ? tr(alert.level === "stop" ? "agent.stoppedAt" : "agent.warningAt", { i: int(s.step) }) : "";
      const mark = state === "ahead" || state === "skipped" ? '<span class="gp-dot"></span>' : icon(SHIELD + MARK[state], `gp-shield ${state}`);
      return `<li class="gp-step is-${state} ${line}${fresh ? " fresh" : ""}${filling ? " filling" : ""}${front ? " is-front" : ""}">
        <div class="gp-rail" aria-hidden="true"><span class="gp-line"></span><span class="gp-node">${mark}</span></div>
        <div class="gp-card">
          <div class="gp-head">
            <span class="gp-num" dir="ltr">${String(s.step).padStart(2, "0")}</span>
            <span class="gp-kind">${icon(KIND[s.kind] || KIND.thought, "gp-kind-icon")}${esc(kindName(s.kind))}</span>
            ${finished && a.suspected_step === s.step ? `<span class="pill contested">${esc(tr("agent.origin"))}</span>` : ""}
            ${tag ? `<span class="gp-tag">${esc(tag)}</span>` : ""}
          </div>
          ${reached ? `
            <h5 class="gp-title">${esc(titleOf(s, skipped ? null : alert))}</h5>
            <p class="gp-text" dir="auto">${esc(short(s.content))}</p>
            ${s.observation ? `<div class="gp-tool">${icon(KIND.observation, "gp-tool-icon")}<span dir="auto">${esc(short(s.observation))}</span></div>` : ""}
            ${alert && !skipped ? `<p class="gp-alert ${alert.level}">${esc(alert.level === "stop" ? tr("agent.alertStop", { reason: alert.reason }) : tr("agent.alertWarning", { reason: alert.reason }))}</p>` : ""}` : ""}
        </div>
      </li>`;
    }).join("")}</ol>`;
  }

  function draw() {
    const a = agent();
    const stop = stopIndex();
    const halted = stop >= 0 && run && shown > stop;
    const finished = run && shown >= run.steps.length;
    const tg = card?.guardian;

    root.innerHTML = `
      <div class="rp-card">
        <h4>${esc(tr("agent.pick"))}</h4>
        <div class="chips">${examples.map((e) => `<button type="button" class="chip" data-example="${esc(e.id)}" aria-pressed="${current === e.id}" ${busy ? "disabled" : ""}>${esc(exampleTitle(e))}</button>`).join("")}</div>
        ${current ? `<p class="rp-small">${esc(exampleAbout(examples.find((e) => e.id === current) || {}))}</p>` : ""}
        <div class="chips" role="radiogroup" aria-label="${esc(tr("agent.policyLabel"))}"><span class="rp-small">${esc(tr("agent.policy"))}</span>
          ${["strict", "lenient"].map((p) => `<button type="button" class="chip" role="radio" data-policy="${p}" aria-checked="${policy === p}" aria-pressed="${policy === p}">${esc(tr(`agent.${p}`))}</button>`).join("")}</div>
        <details class="own"><summary>${esc(tr("agent.own"))}</summary>
          <textarea class="code" id="agent-json" dir="ltr" spellcheck="false" aria-label="${esc(tr("agent.json"))}">${esc(custom)}</textarea>
          <button type="button" class="btn-primary" id="agent-run" ${busy ? "disabled" : ""}>${esc(tr("agent.run"))}</button>
        </details>
      </div>
      ${busy ? `<div class="rp-card"><h4>${esc(tr("agent.preparing"))}</h4><p class="rp-small">${esc(tr("agent.preparingText"))}</p></div>` : ""}
      ${error ? `<p class="rp-warn">${esc(tr("agent.failed", { error }))}</p>` : ""}
      ${a && run ? `
        ${run.question ? `<p class="rp-text"><span class="rp-small">${esc(tr("agent.task"))}</span> ${esc(run.question)}</p>` : ""}
        <div class="agent-head rp-card ${halted ? "halted" : ""}" aria-live="polite">
          <span class="agent-state">${esc(halted ? tr("agent.stopped") : finished ? tr("agent.finished") : tr("agent.watching"))}</span>
          <span class="rp-small">${esc(halted ? tr("agent.stoppedText", { i: int(agent().guardian_stop ?? 0) }) : finished ? (agent().guardian_stop == null ? tr("agent.letFinish") : tr("agent.pastStop")) : tr("agent.progress", { i: int(Math.max(1, shown)), n: int(run.steps.length) }))}</span>
          <div class="chips">
            <button type="button" class="btn-primary" data-act="play" ${finished || (halted && !playing) ? "disabled" : ""}>${esc(playing ? tr("common.pause") : shown === 0 ? tr("agent.play") : tr("agent.resume"))}</button>
            <button type="button" class="btn-ghost" data-act="next" ${finished ? "disabled" : ""}>${esc(tr("agent.next"))}</button>
            <button type="button" class="btn-ghost" data-act="replay">${esc(tr("agent.replay"))}</button>
            ${halted && !finished ? `<button type="button" class="btn-ghost" data-act="rest">${esc(tr("agent.wouldHave"))}</button>` : ""}
          </div>
        </div>
        <div class="rp-card gp-trail"><h4>${esc(tr("agent.trajectory"))}</h4>${pathHTML(a, stop, finished)}</div>
        ${finished ? `
          <div class="rp-grid">
            <div class="rp-main">
              <div class="rp-card"><h4>${esc(tr("agent.tracerTitle"))}</h4>
                ${a.steps.map((s) => `<div class="tracer-row"><span class="mono">${esc(tr("agent.step", { i: int(s.step) }))}</span><div class="bar ${s.step === a.suspected_step ? "warn" : "none"}"><span style="width:${Math.max(2, s.suspicion * 100).toFixed(0)}%"></span></div><span class="mono">${num(s.suspicion)}</span></div>`).join("")}
                <span class="rp-small">${esc(tr("agent.tracerNote"))}</span></div>
              <div class="rp-card"><h4>${esc(tr("agent.finalTitle"))}</h4><div id="agent-final"></div></div>
            </div>
            <aside class="rp-side">
              ${tg ? `<div class="rp-card"><h4>${esc(tr("agent.measuredTitle"))}</h4><p class="rp-small">${esc(tr("agent.measured", { a: pct(tg.strict?.stop_tpr), b: pct(tg.strict?.stop_fpr), c: pct(tg.strict?.stop_on_responsible_step), d: pct(tg.lenient?.stop_tpr), e: pct(tg.lenient?.stop_fpr) }))}</p></div>` : ""}
            </aside>
          </div>` : ""}
      ` : ""}`;

    root.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => pick(b.dataset.example)));
    root.querySelectorAll("[data-policy]").forEach((b) => b.addEventListener("click", () => { policy = b.dataset.policy; draw(); }));
    root.querySelector("#agent-json")?.addEventListener("input", (e) => { custom = e.target.value; });
    root.querySelector("#agent-run")?.addEventListener("click", runCustom);
    root.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
      const act = b.dataset.act;
      if (act === "play") { playing = !playing; tick(); }
      if (act === "next") { playing = false; shown = Math.min(run.steps.length, shown + 1); }
      if (act === "replay") { shown = 0; playing = true; tick(); }
      if (act === "rest") { playing = false; shown = run.steps.length; }
      draw();
    }));
    const final = root.querySelector("#agent-final");
    if (final && window.TGReport && run) window.TGReport.render(final, { text: run.answer, report: run.report }, { compact: true });
    drawnShown = shown;
  }

  fetch("/api/examples").then((r) => r.json()).then((e) => { examples = e.agents || []; draw(); }).catch(() => {});
  fetch("/api/model-card").then((r) => r.json()).then((c) => { card = c; draw(); }).catch(() => {});
  if (window.TG) window.TG.onLang(draw);
  draw();
})();
