// The Guardian's report on one answer, laid out as on the previous site's "Check an answer" page (its ReportView and
// report panels): the answer with every claim coloured by its status, the chosen claim in detail (its evidence, the
// suggested action and fix, its cautions), the verdict card (grade, verdict, risk on its gauge with the decision or
// guarantee lines, the triage lane), who is to blame, sources that disagree, what was left out, which claims add most to
// the risk, the reliability dimensions and the warnings. The words are the previous site's
// (panels.*, verdict.*, status.*, action.*, lane.*, blame.*, dimension.*, stage.* in js/i18n.js).
// TGReport.render(element, answer, { compact }) fills an element; compact keeps the chat's bubble short.

(() => {
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const has = (key) => tr(key) !== key;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const lang = () => (window.TG ? window.TG.lang : "en");
  const loc = () => ({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang();
  const num = (x, d = 2) => (x == null ? "–" : new Intl.NumberFormat(loc(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(x));
  const pct = (x) => (x == null ? "–" : new Intl.NumberFormat(loc(), { style: "percent", maximumFractionDigits: 1 }).format(x));
  const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
  const label = (family, key) => (has(`${family}.${key}`) ? tr(`${family}.${key}`) : key.replace(/_/g, " "));
  const STAGES = ["lexical", "symbolic", "dense", "hhem", "polarity", "shifts", "score", "claims", "checks", "verdict", "multilingual"];

  // The answer with each claim as a coloured, clickable stretch.
  function answerHTML(text, claims, selected) {
    const spans = claims.map((c, i) => ({ ...c, i })).filter((c) => c.end > c.start).sort((a, b) => a.start - b.start);
    let html = "";
    let at = 0;
    for (const c of spans) {
      if (c.start < at) continue;
      html += esc(text.slice(at, c.start));
      html += `<button type="button" class="claim-mark ${c.status}${c.i === selected ? " on" : ""}" data-claim="${c.i}">${esc(text.slice(c.start, c.end))}</button>`;
      at = c.end;
    }
    return html + esc(text.slice(at));
  }

  function legend() {
    return `<div class="legend-row">${["supported", "contradicted", "unsupported", "insufficient_evidence", "contested"].map((s) => `<span class="legend-item ${s}"><span class="legend-dot"></span>${esc(label("status", s))}</span>`).join("")}</div>`;
  }

  function claimHTML(c) {
    if (!c) return "";
    const doc = c.evidence?.document_id?.match(/^source(\d+)$/)?.[1];
    const fixes = (c.fixes || []).filter((f) => f.replacement);
    return `
      <div class="rp-claim ${c.status}">
        <div class="rp-claim-head"><span class="pill ${c.status}">${esc(label("status", c.status))}</span>
          <span class="mono">${esc(tr("panels.claimRisk", { r: num(c.risk) }))}${c.contribution != null ? esc(tr("panels.adds", { v: `${c.contribution >= 0 ? "+" : ""}${num(c.contribution)}` })) : ""}</span></div>
        <p class="rp-text">${esc(cap(c.explanation))}.</p>
        <div class="rp-two">
          <div class="rp-well"><span class="rp-small">${esc(tr("panels.evidence"))}${doc ? esc(tr("panels.evidenceSource", { i: doc })) : c.evidence?.document_id ? ` · ${esc(c.evidence.document_id)}` : ""}</span>
            <span>${c.evidence ? esc(c.evidence.text) : esc(tr("panels.noEvidence"))}</span></div>
          <div class="rp-well"><span class="rp-small">${esc(tr("panels.suggested"))}</span><span>${esc(label("action", c.action))}</span>
            ${fixes.map((f) => `<span class="fix" dir="ltr">${esc(f.original)} → ${esc(f.replacement)}</span>`).join("")}</div>
        </div>
        ${(c.cautions || []).map((x) => `<p class="rp-warn">${esc(cap(x))}.</p>`).join("")}
      </div>`;
  }

  function verdictHTML(r) {
    const risk = r.domain?.calibrated_risk ?? r.risk;
    const marks = r.guarantee ? [["catch", r.guarantee.catch_threshold], ["alarm", r.guarantee.alarm_threshold]] : [["decision", r.domain?.decision ?? r.response_threshold]];
    const grade = r.card?.grade;
    const g = r.guarantee;
    return `
      <div class="rp-card rp-verdict ${r.verdict}">
        <div class="rp-verdict-head">
          ${grade ? `<span class="grade g${grade}" aria-label="${esc(tr("panels.grade", { g: grade }))}">${grade}</span>` : ""}
          <div><span class="rp-verdict-word">${esc(label("verdict", r.verdict))}</span>
            <span class="rp-small">${esc(tr("panels.riskModel", { r: num(risk) }))}</span></div>
        </div>
        <div class="gauge" role="meter" aria-valuemin="0" aria-valuemax="1" aria-valuenow="${risk}">
          <span class="gauge-fill" style="width:${(risk * 100).toFixed(1)}%"></span>
          ${marks.map(([n, x]) => `<span class="gauge-mark" style="inset-inline-start:${Math.min(99.5, x * 100).toFixed(1)}%" title="${esc(label("panels.mark", n))} ${num(x)}"></span>`).join("")}
        </div>
        <div class="gauge-scale mono"><span>0</span>${marks.map(([n, x]) => `<span>${esc(label("panels.mark", n))} ${num(x)}</span>`).join("")}<span>1</span></div>
        ${g ? `<p class="rp-small">${esc(g.flagged_with_alarm_guarantee ? tr("panels.alarm", { a: pct(g.alpha) }) : g.flagged_with_catch_guarantee ? tr("panels.catchAbove", { a: pct(g.alpha) }) : tr("panels.catchBelow", { a: pct(g.alpha) }))} ${esc(tr("panels.conformal", { on: g.calibrated_on }))}</p>` : ""}
        ${r.triage ? `<div class="rp-lane"><span class="pill lane-${r.triage.lane}">${esc(label("lane", r.triage.lane))}</span><span class="rp-small">${esc(r.triage.reason)}</span></div>` : ""}
      </div>`;
  }

  function sideHTML(r) {
    const parts = [];
    if (r.diagnosis) {
      parts.push(`<div class="rp-card"><h4>${esc(tr("panels.blame"))}</h4><strong>${esc(label("blame", r.diagnosis.blame))}</strong><p class="rp-small">${esc(r.diagnosis.message)}</p>${r.diagnosis.relevance != null ? `<span class="mono rp-small">${esc(tr("panels.relevance", { r: num(r.diagnosis.relevance), t: num(0.43) }))}</span>` : ""}</div>`);
    }
    if (r.conflicts?.length) {
      parts.push(`<div class="rp-card"><h4>${esc(tr("panels.conflicts"))}</h4>${r.conflicts.map((c) => `<p class="rp-small"><b>${esc(c.first_value)}</b>${esc(tr("panels.conflictIn", { doc: c.first_document, text: c.first }))}<br><b>${esc(c.second_value)}</b>${esc(tr("panels.conflictIn", { doc: c.second_document, text: c.second }))}</p>`).join("")}</div>`);
    }
    const c = r.completeness;
    if (c && (c.missing?.length || c.omitted_caveats?.length)) {
      parts.push(`<div class="rp-card"><h4>${esc(tr("panels.omissions"))}</h4>${(c.omitted_caveats || []).map((x) => `<p class="rp-warn">${esc(tr("panels.dropped", { x }))}</p>`).join("")}${(c.missing || []).map((x) => `<p class="rp-small">${esc(tr("panels.quote", { x }))}</p>`).join("")}</div>`);
    }
    const shares = r.claims.map((cl) => ({ text: cl.text, v: cl.contribution })).filter((s) => s.v != null && s.v > 0.005).sort((a, b) => b.v - a.v).slice(0, 5);
    if (shares.length) {
      parts.push(`<div class="rp-card"><h4>${esc(tr("panels.shares"))}</h4>${shares.map((s) => `<div class="share"><div class="share-row"><span>${esc(s.text)}</span><span class="mono">+${num(s.v)}</span></div><div class="bar"><span style="width:${((s.v / shares[0].v) * 100).toFixed(0)}%"></span></div></div>`).join("")}<span class="rp-small">${esc(tr("panels.sharesNote"))}</span></div>`);
    }
    if (r.card?.dimensions?.length) {
      parts.push(`<div class="rp-card"><h4>${esc(tr("panels.reliability"))}</h4>${r.card.dimensions.map((d) => {
        const tone = d.score == null ? "none" : d.score < 0.4 ? "bad" : d.score < 0.8 ? "warn" : "ok";
        return `<div class="share"><div class="share-row"><span>${esc(label("dimension", d.name))}</span><span class="mono">${num(d.score)}</span></div><div class="bar ${tone}"><span style="width:${((d.score ?? 0) * 100).toFixed(0)}%"></span></div><span class="rp-small">${esc(d.note || "")}</span></div>`;
      }).join("")}</div>`);
    }
    return parts.join("");
  }

  // Which of the engine's stages read the answer: the text engine's checks and the multilingual check.
  function stagesHTML(r) {
    const used = new Set(STAGES.filter((s) => s !== "multilingual"));
    if (r.language && r.language.check && r.language.check !== "english") used.add("multilingual");
    return `<div class="stage-row">${STAGES.map((s) => `<span class="stage-chip${used.has(s) ? " on" : ""}">${esc(label("stage", s))}</span>`).join("")}</div>`;
  }

  function render(el, a, { compact = false } = {}) {
    const r = a.report;
    if (!r) {
      el.innerHTML = `<p class="rp-text">${esc(a.text || "")}</p>${(a.notes || []).map((n) => `<p class="rp-small">${esc(n)}</p>`).join("")}`;
      return;
    }
    const first = r.claims.findIndex((c) => c.status !== "supported");
    let selected = first >= 0 ? first : 0;
    const draw = () => {
      el.innerHTML = compact
        ? `${verdictHTML(r)}
           <div class="rp-card"><h4>${esc(tr("analyze.answerTitle"))}</h4>${legend()}<p class="rp-answer">${answerHTML(a.text, r.claims, selected)}</p></div>
           ${claimHTML(r.claims[selected])}`
        : `<div class="rp-grid">
             <div class="rp-main">
               <div class="rp-card"><h4>${esc(tr("analyze.answerTitle"))}</h4>${legend()}<p class="rp-answer">${answerHTML(a.text, r.claims, selected)}</p></div>
               ${claimHTML(r.claims[selected])}
               ${(r.warnings || []).map((w) => `<p class="rp-warn">${esc(w)}</p>`).join("")}
               ${r.cited_answer ? `<div class="rp-card"><p class="rp-text">${esc(r.cited_answer)}</p></div>` : ""}
               <div class="rp-card"><h4>${esc(tr("html.r.stages"))}</h4>${stagesHTML(r)}</div>
             </div>
             <aside class="rp-side">${verdictHTML(r)}${sideHTML(r)}</aside>
           </div>`;
      el.querySelectorAll("[data-claim]").forEach((b) => b.addEventListener("click", () => {
        selected = Number(b.dataset.claim);
        draw();
      }));
    };
    draw();
  }

  // The engine's stages while a check streams, as the previous site's StageProgress: done ones ticked with the time
  // they took, the current one blinking, the rest faint. stages: [{ stage, t }] in the order they arrived.
  function progress(stages, queued) {
    const seen = new Set(stages.map((s) => s.stage));
    const current = stages[stages.length - 1]?.stage;
    const took = (stage) => {
      const i = stages.findIndex((s) => s.stage === stage);
      return i >= 0 && i + 1 < stages.length ? stages[i + 1].t - stages[i].t : null;
    };
    return `<ol class="ck-stages" aria-live="polite">
      ${queued ? `<li class="rp-warn">${esc(tr("panels.waiting"))}</li>` : ""}
      ${STAGES.map((s) => {
        const done = seen.has(s) && s !== current;
        const active = s === current;
        return `<li class="${done ? "done" : active ? "active" : ""}"><span class="ck-dot" aria-hidden="true">${done ? "✓" : ""}</span>${esc(label("stage", s))}${done ? `<span class="mono rp-small">${esc(tr("common.seconds", { s: num(took(s), 1) }))}</span>` : ""}</li>`;
      }).join("")}
    </ol>`;
  }

  window.TGReport = { render, progress };
})();
