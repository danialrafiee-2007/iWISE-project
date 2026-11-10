// Model performance: the models' measured results, read live from the server's model card (/api/model-card, built
// from eval/results), laid out after the reference video's dashboard: a row of figures, "candles" of Truth Guardian
// against the baselines on each locked test set, the tables in detail and the calibration. Nothing here is typed in by
// hand: when the evaluation files change, this changes with them.

(() => {
  const body = document.getElementById("models-body");
  if (!body) return;
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const lang = () => (window.TG ? window.TG.lang : "en");
  let card = null;

  // Numbers in the page language's digits, as on the previous site (Persian digits in Persian, Latin in Arabic).
  const loc = () => ({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang();
  const num = (x, digits = 3) => (x == null || Number.isNaN(x) ? "–" : new Intl.NumberFormat(loc(), { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(x));
  const pct = (x) => (x == null ? "–" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 1 }).format(x));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // One candle: a rounded bar whose height is the value on a 0.5 to 1 scale (0.5 is chance for AUROC).
  function candle(value, kind, label) {
    const h = value == null ? 0 : Math.max(4, Math.min(100, ((value - 0.5) / 0.5) * 100));
    return `<span class="candle ${kind}" style="--h:${h.toFixed(1)}%" title="${esc(label)}: ${num(value)}"><span class="candle-value">${num(value, 2)}</span></span>`;
  }

  // ---- The reliability diagram, as on the previous site (its CalibrationChart, D-204): for each set, the predicted
  // risk (the bin's average) against the share of its answers really hallucinated, with the dashed line of perfect
  // calibration; beside it, how to read it. A point shows its numbers under the pointer or the keyboard. ----
  const SERIES = [
    { key: "ragtruth_dev", label: "card.seriesDev", color: "#3987e5", at: [7, -10, -10, "end"] },
    { key: "ragtruth_test", label: "card.seriesTest", color: "#14a38b", at: [4, 10, 18, "start"] },
    { key: "halueval", label: "card.seriesHalu", color: "#d95926", at: [3, 0, -12, "middle"] },
  ];
  const W = 560, H = 360, PAD = { left: 52, right: 20, top: 16, bottom: 48 };
  const X = (v) => PAD.left + v * (W - PAD.left - PAD.right);
  const Y = (v) => H - PAD.bottom - v * (H - PAD.top - PAD.bottom);
  function calibration() {
    const series = SERIES.filter((s) => card.calibration?.[s.key]).map((s) => ({ ...s, name: tr(s.label), ...card.calibration[s.key], bins: (card.calibration[s.key].bins || []).filter((b) => b.n > 0) }));
    if (!series.length) return "";
    const ticks = [0, 0.2, 0.4, 0.6, 0.8, 1];
    const point = (s, b) => tr("calib.point", { label: s.name, a: num(b.low, 1), b: num(b.high, 1), m: num(b.mean_risk, 2), o: pct(b.observed), n: num(b.n, 0) });
    const svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(tr("calib.aria"))}">
      ${ticks.map((t) => `<line class="grid" x1="${X(0)}" x2="${X(1)}" y1="${Y(t)}" y2="${Y(t)}"/><text class="tick" x="${X(0) - 8}" y="${Y(t)}" dy="0.32em" text-anchor="end">${num(t, 1)}</text><text class="tick" x="${X(t)}" y="${Y(0) + 18}" text-anchor="middle">${num(t, 1)}</text>`).join("")}
      <text class="axis" x="${(X(0) + X(1)) / 2}" y="${H - 8}" text-anchor="middle">${esc(tr("calib.x"))}</text>
      <text class="axis" transform="translate(14 ${(Y(0) + Y(1)) / 2}) rotate(-90)" text-anchor="middle">${esc(tr("calib.y"))}</text>
      <line x1="${X(0)}" y1="${Y(0)}" x2="${X(1)}" y2="${Y(1)}" stroke="#5f6f67" stroke-width="1.5" stroke-dasharray="5 5"/>
      ${series.map((s) => `<polyline points="${s.bins.map((b) => `${X(b.mean_risk)},${Y(b.observed)}`).join(" ")}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>${s.bins.map((b) => `<circle cx="${X(b.mean_risk)}" cy="${Y(b.observed)}" r="4" fill="${s.color}" stroke="#f7f3e9" stroke-width="2"/>`).join("")}`).join("")}
      ${series.map((s) => { const [i, dx, dy, anchor] = s.at; const b = s.bins[Math.min(i, s.bins.length - 1)]; return b ? `<text class="name" x="${X(b.mean_risk) + dx}" y="${Y(b.observed) + dy}" text-anchor="${anchor}">${esc(s.name)}</text>` : ""; }).join("")}
      ${series.map((s, si) => s.bins.map((b, bi) => `<circle class="hit" cx="${X(b.mean_risk)}" cy="${Y(b.observed)}" r="12" tabindex="0" data-s="${si}" data-b="${bi}" aria-label="${esc(point(s, b))}"/>`).join("")).join("")}
    </svg>`;
    const lows = Array.from({ length: 10 }, (_, i) => i / 10);
    const table = `<details class="calib-table"><summary>${esc(tr("calib.table"))}</summary><div><table>
      <thead><tr><th>${esc(tr("calib.band"))}</th>${series.map((s) => `<th>${esc(tr("calib.col", { label: s.name }))}</th>`).join("")}</tr></thead>
      <tbody>${lows.map((low) => `<tr><td>${esc(tr("calib.range", { a: num(low, 1), b: num(low + 0.1, 1) }))}</td>${series.map((s) => { const b = s.bins.find((v) => Math.abs(v.low - low) < 1e-9); return `<td>${esc(b ? tr("calib.cell", { m: num(b.mean_risk, 2), o: pct(b.observed), n: num(b.n, 0) }) : tr("calib.none"))}</td>`; }).join("")}</tr>`).join("")}</tbody>
    </table></div></details>`;
    calibSeries = series;
    return `<div class="calib-box">
      <div class="calib-chart">
        <ul class="calib-legend" aria-label="${esc(tr("calib.legend"))}">${series.map((s) => `<li><span class="calib-dot" style="background:${s.color}"></span>${esc(tr("calib.ece", { label: s.name, v: num(s.ece, 3) }))}</li>`).join("")}<li><span class="calib-dash"></span>${esc(tr("calib.perfect"))}</li></ul>
        <div class="calib-plot" dir="ltr">${svg}<div class="calib-tip" hidden></div></div>
        ${table}
      </div>
      <div class="calib-read"><p>${esc(tr("card.calib1"))}</p><p>${esc(tr("card.calib2"))}</p><p>${esc(tr("card.calib3"))}</p><small>${esc(tr("card.calibNote"))}</small></div>
    </div>`;
  }
  let calibSeries = [];
  // The point's numbers in a small dark card above it, under the pointer or the keyboard.
  function tipOn(hit) {
    const plot = hit.closest(".calib-plot");
    const tip = plot?.querySelector(".calib-tip");
    const s = calibSeries[+hit.dataset.s];
    const b = s?.bins[+hit.dataset.b];
    if (!tip || !b) return;
    tip.innerHTML = `<b><span class="calib-dot" style="background:${s.color}"></span>${esc(s.name)}</b><div>${esc(tr("calib.tipRisk", { a: num(b.low, 1), b: num(b.high, 1), m: num(b.mean_risk, 2) }))}</div><div>${esc(tr("calib.tipReal", { o: pct(b.observed) }))}</div><div>${esc(tr("calib.tipN", { n: num(b.n, 0) }))}</div>`;
    const left = X(b.mean_risk) / W;
    const shift = left < 0.3 ? "-12px" : left > 0.7 ? "calc(-100% + 12px)" : "-50%";
    Object.assign(tip.style, { left: `${left * 100}%`, top: `${(Y(b.observed) / H) * 100}%`, transform: `translate(${shift}, calc(-100% - 14px))` });
    tip.hidden = false;
  }
  const tipOff = (hit) => { const tip = hit.closest(".calib-plot")?.querySelector(".calib-tip"); if (tip) tip.hidden = true; };
  for (const [on, off] of [["mouseover", "mouseout"], ["focusin", "focusout"]]) {
    body.addEventListener(on, (e) => { if (e.target.classList?.contains("hit")) tipOn(e.target); });
    body.addEventListener(off, (e) => { if (e.target.classList?.contains("hit")) tipOff(e.target); });
  }

  function render() {
    if (!card) return;
    const test = card.locked_test || {};
    const halu = card.locked_halueval || {};
    const base = card.locked_baselines || {};
    const ref = card.locked_reference || {};
    const agent = card.locked_agenthallu || {};
    const speed = card.speed || {};
    const bestBase = (key) => Math.max(...Object.values(base).map((b) => b[key] ?? 0));

    const sets = [
      { name: "RAGTruth", tg: test.auroc, base: bestBase("ragtruth"), ref: ref.ragtruth },
      { name: "HaluEval QA", tg: halu.qa?.auroc, base: bestBase("qa"), ref: ref.qa },
      { name: "HaluEval dialogue", tg: halu.dialogue?.auroc, base: bestBase("dialogue"), ref: ref.dialogue },
      { name: "HaluEval summary", tg: halu.summary?.auroc, base: bestBase("summary"), ref: ref.summary },
    ];

    const tiles = [
      { label: tr("html.m.auroc"), value: num(test.auroc), note: "RAGTruth test" },
      { label: tr("html.m.f1"), value: num(test.f1), note: "RAGTruth test" },
      { label: tr("html.m.ece"), value: num(test.ece), note: "RAGTruth test" },
      { label: tr("html.m.speed"), value: num(speed.mean, 1), note: `p95 ${num(speed.p95, 1)}` },
    ];

    const tasks = Object.entries(test.by_task || {});

    const rows = [
      ["RAGTruth test", test],
      ["HaluEval QA", halu.qa],
      ["HaluEval dialogue", halu.dialogue],
      ["HaluEval summary", halu.summary],
    ].filter(([, m]) => m);

    body.innerHTML = `
      <div class="stat-row">
        ${tiles.map((t) => `<div class="stat"><span class="stat-label">${esc(t.label)}</span><span class="stat-value">${t.value}</span><span class="stat-note" lang="en">${esc(t.note)}</span></div>`).join("")}
      </div>

      <div class="model-grid">
        <figure class="chart-box">
          <figcaption class="chart-title">${esc(tr("html.m.candles"))} <span class="chart-unit">AUROC</span></figcaption>
          <div class="candles" role="img" aria-label="${esc(tr("html.m.candles"))}">
            ${sets.map((s) => `<div class="candle-group"><div class="candle-bars">${candle(s.tg, "tg", tr("html.m.tg"))}${candle(s.base, "base", tr("html.m.base"))}${candle(s.ref, "ref", tr("html.m.ref"))}</div><span class="candle-name" lang="en">${esc(s.name)}</span></div>`).join("")}
          </div>
          <div class="legend"><span class="key tg"></span>${esc(tr("html.m.tg"))}<span class="key base"></span>${esc(tr("html.m.base"))}<span class="key ref"></span>${esc(tr("html.m.ref"))}</div>
        </figure>

        <figure class="chart-box">
          <figcaption class="chart-title">${esc(tr("html.m.byTask"))} <span class="chart-unit">AUROC</span></figcaption>
          <div class="candles slim">
            ${tasks.map(([name, m]) => `<div class="candle-group"><div class="candle-bars">${candle(m.auroc, "tg", name)}</div><span class="candle-name" lang="en">${esc(name)}</span></div>`).join("")}
          </div>
          <div class="agent-box">
            <span class="chart-title">${esc(tr("html.m.agent"))}</span>
            <div class="meter"><span style="width:${((agent.exact ?? 0) * 100).toFixed(1)}%"></span></div>
            <div class="meter-row"><span>${esc(tr("html.m.exact"))}</span><strong>${pct(agent.exact)}</strong></div>
            <div class="meter muted"><span style="width:${((agent.random ?? 0) * 100).toFixed(1)}%"></span></div>
            <div class="meter-row"><span>${esc(tr("html.m.random"))}</span><strong>${pct(agent.random)}</strong></div>
          </div>
        </figure>
      </div>

      <figure class="chart-box calib-figure">
        <figcaption class="chart-title">${esc(tr("card.calibTitle"))}</figcaption>
        ${calibration()}
      </figure>

      <div class="table-wrap">
        <table class="facts">
          <caption class="chart-title">${esc(tr("html.m.table"))}</caption>
          <thead><tr><th>${esc(tr("html.col.set"))}</th><th class="num">${esc(tr("html.col.answers"))}</th><th class="num">AUROC</th><th class="num">${esc(tr("html.m.f1"))}</th><th class="num">${esc(tr("html.m.precision"))}</th><th class="num">${esc(tr("html.m.recall"))}</th><th class="num">${esc(tr("html.m.ece"))}</th></tr></thead>
          <tbody>
            ${rows.map(([name, m]) => `<tr><td lang="en">${esc(name)}</td><td class="num">${num(m.answers, 0)}</td><td class="num strong">${num(m.auroc)}</td><td class="num">${num(m.f1)}</td><td class="num">${num(m.precision)}</td><td class="num">${num(m.recall)}</td><td class="num">${num(m.ece)}</td></tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  }

  // The models that read sound and images, as on the previous site's "Models and status" pages (/api/media/status):
  // for each, four separate states on this computer (files present, runtime installed, run on known samples, quality
  // evaluated on labelled data) and what its run on the samples showed.
  const media = document.getElementById("media-models");
  let mediaRows = null;
  const STATES = [["files_present", "models.files"], ["runtime_ready", "models.runtime"], ["run_tested", "models.tested"], ["quality_evaluated", "models.evaluated"]];
  function renderMedia() {
    if (!media || !mediaRows) return;
    // The readers behind sound and images, as on the previous site (its READERS): speech, text in images, what it shows.
    media.innerHTML = mediaRows.filter((row) => ["speech", "ocr", "vision"].includes(row.name)).map((row) => {
      const p = row.pilot;
      const seconds = p?.seconds ? Object.values(p.seconds).reduce((a, b) => a + b, 0) : 0;
      return `<div class="media-card">
        <span class="stage-no">${esc(tr(`models.role.${row.name}`))}</span>
        <strong dir="ltr">${esc(row.model)}</strong>
        <p class="section-note">${esc(tr(`models.about.${row.name}`))}</p>
        <ul class="state-list">${STATES.map(([k, key]) => `<li class="${row[k] ? "yes" : "no"}"><span aria-hidden="true">${row[k] ? "✓" : "–"}</span>${esc(tr(key))}<span class="sr-only">${esc(tr(row[k] ? "models.yes" : "models.no"))}</span></li>`).join("")}</ul>
        ${p?.checks != null ? `<p class="section-note">${esc(tr("models.pilot", { passed: num(p.passed_checks ?? 0, 0), checks: num(p.checks, 0), s: num(seconds, 1), mb: num(Math.round((p.peak_mb ?? 0) + (p.server_peak_mb ?? 0)), 0) }))}</p>` : ""}
      </div>`;
    }).join("");
  }
  fetch("/api/media/status", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
    .then((data) => { mediaRows = data.components || []; renderMedia(); })
    .catch(() => { if (media) media.innerHTML = `<p class="section-note">${esc(tr("models.error"))}</p>`; });
  if (window.TG) window.TG.onLang(renderMedia);

  // How well the sound and image readers did on real media (eval/results/media_eval.json through the model card, D-139):
  // speech per language (errors in words or characters, the language told, and how well the check then tells a true
  // transcript's answer from a changed one), text in images per set, and the image model's answers right.
  const quality = document.getElementById("media-quality");
  function renderQuality() {
    const m = card?.media;
    if (!quality || !m) return;
    const languageName = (code) => { try { return new Intl.DisplayNames([lang()], { type: "language" }).of(code) || code; } catch { return code; } };
    quality.innerHTML = `
      <div class="table-wrap"><table class="facts">
        <caption class="chart-title">${esc(tr("html.mq.speech"))}</caption>
        <thead><tr><th>${esc(tr("html.mq.lang"))}</th><th class="num">${esc(tr("html.mq.errors"))}</th><th class="num">${esc(tr("html.mq.told"))}</th><th class="num">${esc(tr("html.mq.chain"))}</th></tr></thead>
        <tbody>${Object.entries(m.speech || {}).map(([code, d]) => `<tr><td>${esc(languageName(code))}</td><td class="num">${pct(d.error_rate)} <span class="rp-small">${esc(d.unit)}</span></td><td class="num">${pct(d.language_right)}</td><td class="num strong">${num(d.auroc)}</td></tr>`).join("")}</tbody>
      </table></div>
      <div class="table-wrap"><table class="facts">
        <caption class="chart-title">${esc(tr("html.mq.ocr"))}</caption>
        <thead><tr><th>${esc(tr("html.mq.set"))}</th><th class="num">${esc(tr("html.col.answers"))}</th><th class="num">${esc(tr("html.mq.found"))}</th><th class="num">${esc(tr("html.mq.read"))}</th><th class="num">${esc(tr("html.mq.chain"))}</th></tr></thead>
        <tbody>${Object.entries(m.images || {}).map(([name, d]) => `<tr><td lang="en">${esc(name.replace("_", " · "))}</td><td class="num">${num(d.questions, 0)}</td><td class="num">${pct(d.text_found)}</td><td class="num">${pct(d.answer_read)}</td><td class="num strong">${num(d.auroc)}</td></tr>`).join("")}</tbody>
      </table></div>
      ${m.vision ? `<div class="stat-row">
        <div class="stat"><span class="stat-label">${esc(tr("html.mq.vision"))}</span><span class="stat-value">${pct(m.vision.right)}</span><span class="stat-note">${esc(tr("html.mq.right"))} · ${num(m.vision.answers, 0)}</span></div>
      </div>` : ""}`;
  }
  if (window.TG) window.TG.onLang(renderQuality);

  fetch("/api/model-card", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
    .then((data) => { card = data; render(); renderQuality(); })
    .catch(() => { body.innerHTML = `<p class="section-note">${esc(tr("html.m.failed"))}</p>`; });
  if (window.TG) window.TG.onLang(render);
})();
