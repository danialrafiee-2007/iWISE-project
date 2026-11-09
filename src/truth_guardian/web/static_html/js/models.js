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
  const pct = (x) => (x == null ? "–" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 0 }).format(x));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // One candle: a rounded bar whose height is the value on a 0.5 to 1 scale (0.5 is chance for AUROC).
  function candle(value, kind, label) {
    const h = value == null ? 0 : Math.max(4, Math.min(100, ((value - 0.5) / 0.5) * 100));
    return `<span class="candle ${kind}" style="--h:${h.toFixed(1)}%" title="${esc(label)}: ${num(value)}"><span class="candle-value">${num(value, 2)}</span></span>`;
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
    const bins = (card.calibration?.ragtruth_dev?.bins || []).filter((b) => b.n > 0);

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

      <figure class="chart-box">
        <figcaption class="chart-title">${esc(tr("html.m.calib"))} <span class="chart-unit">ECE ${num(card.calibration?.ragtruth_dev?.ece)}</span></figcaption>
        <div class="candles calib">
          ${bins.map((b) => `<div class="candle-group"><div class="candle-bars"><span class="candle base" style="--h:${(b.mean_risk * 100).toFixed(1)}%" title="${esc(tr("html.m.predicted"))}"></span><span class="candle tg" style="--h:${(b.observed * 100).toFixed(1)}%" title="${esc(tr("html.m.observed"))}"></span></div><span class="candle-name">${num(b.low, 1)}–${num(b.high, 1)}</span></div>`).join("")}
        </div>
        <div class="legend"><span class="key base"></span>${esc(tr("html.m.predicted"))}<span class="key tg"></span>${esc(tr("html.m.observed"))}</div>
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

  fetch("/api/model-card", { cache: "no-store" })
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
    .then((data) => { card = data; render(); })
    .catch(() => { body.innerHTML = `<p class="section-note">${esc(tr("html.m.failed"))}</p>`; });
  if (window.TG) window.TG.onLang(render);
})();
