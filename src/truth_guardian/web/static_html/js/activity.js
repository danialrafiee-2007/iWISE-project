// The activity log (D-210), after the earlier project's: a button at the bottom right opens a window with three tabs.
// 1. On this page: what the person does on the site (pages, tabs, questions, files, reports, code opened, the tour,
//    the language, the lamps), kept in this browser.
// 2. The engine: what the server did, stage by stage, with times and failures (/api/activity, followed live).
// 3. Project history: the project's decisions and commits (/api/activity/history).
// Each can be downloaded as CSV or JSON. Only the first words of a question are kept, never a file's content.

(() => {
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const STORE = "tg-activity-site";
  const KEEP = 1000;
  const short = (text, size = 120) => { const t = String(text ?? "").replace(/\s+/g, " ").trim(); return t.length > size ? `${t.slice(0, size - 1)}…` : t; };

  // ---- 1. The site's rows, in this browser ----
  let site = [];
  try { site = JSON.parse(localStorage.getItem(STORE) || "[]"); if (!Array.isArray(site)) site = []; } catch { site = []; }
  const save = () => { try { localStorage.setItem(STORE, JSON.stringify(site.slice(-KEEP))); } catch { /* storage unavailable */ } };
  let seen = 0; // rows (site and engine) added since the window was last opened, for the button's count

  function log(category, action, detail = "", status = "ok") {
    const row = { time: new Date().toISOString(), category, action, detail: short(detail, 300), status };
    site.push(row);
    if (site.length > KEEP) site = site.slice(-KEEP);
    save();
    seen += 1;
    badge();
    if (dialog?.open && tab === "site") render();
    return row;
  }
  window.TGLog = { log, short };

  // ---- 2. The engine's rows, from the server ----
  let engine = [];
  let lastId = 0;
  let engineDown = false;
  async function pull() {
    try {
      const res = await fetch(`/api/activity?after=${lastId}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const rows = (await res.json()).rows || [];
      engineDown = false;
      if (!rows.length) return;
      lastId = rows[rows.length - 1].id;
      engine = engine.concat(rows).slice(-3000);
      seen += rows.length;
      badge();
      if (dialog?.open && tab === "engine") render();
    } catch {
      engineDown = true;
    }
  }
  // Every 2 seconds while the window shows the engine, else every 15 for the button's count.
  (function loop() { pull().finally(() => setTimeout(loop, dialog?.open && tab === "engine" ? 2000 : 15000)); })();

  // ---- 3. The project's history ----
  let history = null;
  async function loadHistory() {
    if (history) return;
    try {
      const res = await fetch("/api/activity/history", { cache: "no-store" });
      history = res.ok ? await res.json() : { decisions: [], commits: [] };
    } catch {
      history = { decisions: [], commits: [] };
    }
  }

  // ---- The button and the window ----
  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = "log-fab";
  fab.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19.5h16"/><path d="M6.5 16l3.5-4.5 3 2.5 4.5-6.5"/><circle cx="17.5" cy="7.5" r="0.6"/></svg><span class="log-fab-n" hidden></span>`;
  document.body.appendChild(fab);
  const count = fab.querySelector(".log-fab-n");
  function badge() {
    count.hidden = !seen;
    count.textContent = seen > 999 ? "999+" : String(seen);
  }

  const dialog = document.createElement("dialog");
  dialog.className = "person-dialog log-dialog";
  dialog.setAttribute("aria-labelledby", "log-title");
  dialog.innerHTML = `
    <button type="button" class="dialog-x"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
    <div class="log-body">
      <h2 class="log-title" id="log-title"></h2>
      <p class="log-sub"></p>
      <div class="log-tabs" role="group">
        <button type="button" class="chip" data-tab="site"></button>
        <button type="button" class="chip" data-tab="engine"></button>
        <button type="button" class="chip" data-tab="history"></button>
      </div>
      <div class="log-tools">
        <label class="log-errors"><input type="checkbox"> <span></span></label>
        <span class="log-live"></span>
        <span class="log-gap"></span>
        <button type="button" class="btn-ghost" data-act="csv"></button>
        <button type="button" class="btn-ghost" data-act="json"></button>
        <button type="button" class="btn-ghost" data-act="clear"></button>
      </div>
      <div class="log-table-wrap"></div>
    </div>`;
  document.body.appendChild(dialog);
  const q = (s) => dialog.querySelector(s);
  let tab = "site";
  let onlyErrors = false;

  const locale = () => ({ fa: "fa-IR", ar: "ar-u-nu-latn" })[window.TG?.lang] || window.TG?.lang || "en";
  const when = (iso) => { try { return new Date(iso).toLocaleString(locale(), { dateStyle: "short", timeStyle: "medium" }); } catch { return iso; } };

  function words() {
    fab.title = tr("html.log.button");
    fab.setAttribute("aria-label", tr("html.log.button"));
    q(".dialog-x").setAttribute("aria-label", tr("team.close"));
    q(".log-title").textContent = tr("html.log.title");
    q(".log-sub").textContent = tr("html.log.sub");
    for (const b of dialog.querySelectorAll("[data-tab]")) {
      b.textContent = tr(`html.log.tab.${b.dataset.tab}`);
      b.setAttribute("aria-pressed", String(b.dataset.tab === tab));
    }
    q(".log-errors span").textContent = tr("html.log.errors");
    q('[data-act="csv"]').textContent = tr("html.log.csv");
    q('[data-act="json"]').textContent = tr("html.log.json");
    q('[data-act="clear"]').textContent = tr("html.log.clear");
    q('[data-act="clear"]').hidden = tab !== "site";
    q(".log-errors").hidden = tab === "history";
    q(".log-live").textContent = tab === "engine" ? (engineDown ? tr("html.log.down") : tr("html.log.live")) : "";
    q(".log-live").classList.toggle("down", engineDown);
  }

  function table(rows) {
    const shown = (onlyErrors ? rows.filter((r) => r.status === "error") : rows).slice().reverse();
    if (!shown.length) return `<p class="log-empty">${esc(tr(`html.log.empty.${tab}`))}</p>`;
    const head = ["time", "category", "action", "detail", "ms"].map((c) => `<th>${esc(tr(`html.log.col.${c}`))}</th>`).join("");
    const body = shown.map((r) => `<tr class="${r.status === "error" ? "bad" : ""}">
      <td class="lt-time">${esc(when(r.time))}</td>
      <td><span class="lt-cat lt-${esc(String(r.category).replace(/[^a-z]/gi, ""))}" dir="ltr">${esc(r.category)}</span></td>
      <td class="lt-act" dir="auto">${esc(r.action)}</td>
      <td class="lt-detail" dir="auto">${esc(r.detail)}</td>
      <td class="lt-ms">${r.ms == null ? "" : esc(r.ms >= 1000 ? `${(r.ms / 1000).toFixed(1)} s` : `${r.ms} ms`)}</td></tr>`).join("");
    return `<table class="log-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function historyView() {
    if (!history) return `<p class="log-empty">…</p>`;
    const d = history.decisions.slice().reverse().map((r) => `<tr><td class="lt-time" dir="ltr">${esc(r.id)}</td><td class="lt-time">${esc(r.date)}</td><td class="lt-detail" dir="ltr">${esc(r.decision)}</td></tr>`).join("");
    const c = history.commits.map((r) => `<tr><td class="lt-time" dir="ltr"><code>${esc(r.hash)}</code></td><td class="lt-time">${esc(r.date)}</td><td class="lt-detail" dir="ltr">${esc(r.subject)}</td></tr>`).join("");
    return `<h3 class="log-h">${esc(tr("html.log.decisions"))} <span>${history.decisions.length}</span></h3>
      <table class="log-table"><tbody>${d || `<tr><td>${esc(tr("html.log.none"))}</td></tr>`}</tbody></table>
      <h3 class="log-h">${esc(tr("html.log.commits"))} <span>${history.commits.length}</span></h3>
      <table class="log-table"><tbody>${c || `<tr><td>${esc(tr("html.log.none"))}</td></tr>`}</tbody></table>`;
  }

  function render() {
    words();
    const wrap = q(".log-table-wrap");
    wrap.innerHTML = tab === "site" ? table(site) : tab === "engine" ? table(engine) : historyView();
  }

  // Downloads: the site's rows and the history are written here; the engine's come whole from the server.
  function save_file(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }
  const csvOf = (rows, cols) => "﻿" + [cols.join(","), ...rows.map((r) => cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))].join("\r\n") + "\r\n";
  const stamp = () => new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
  function download(format) {
    if (tab === "engine") {
      const a = Object.assign(document.createElement("a"), { href: `/api/activity/download?format=${format}` });
      document.body.appendChild(a);
      a.click();
      a.remove();
    } else if (tab === "site") {
      if (format === "json") save_file(`truth-guardian-site-${stamp()}.json`, JSON.stringify(site, null, 1), "application/json");
      else save_file(`truth-guardian-site-${stamp()}.csv`, csvOf(site, ["time", "category", "action", "detail", "status"]), "text/csv;charset=utf-8");
    } else if (history) {
      if (format === "json") save_file(`truth-guardian-history-${stamp()}.json`, JSON.stringify(history, null, 1), "application/json");
      else {
        const rows = [...history.decisions.map((r) => ({ kind: "decision", id: r.id, date: r.date, text: r.decision, why: r.why })),
          ...history.commits.map((r) => ({ kind: "commit", id: r.hash, date: r.date, text: r.subject, why: "" }))];
        save_file(`truth-guardian-history-${stamp()}.csv`, csvOf(rows, ["kind", "id", "date", "text", "why"]), "text/csv;charset=utf-8");
      }
    }
    log("activity log", "download", `${tab} ${format}`);
  }

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function close() {
    if (!dialog.open || dialog.classList.contains("closing")) return;
    if (reduced) return dialog.close();
    dialog.classList.add("closing");
    setTimeout(() => { dialog.close(); dialog.classList.remove("closing"); }, 320);
  }
  async function show(which) {
    tab = which;
    render();
    if (which === "engine") pull();
    if (which === "history") { await loadHistory(); if (tab === "history") render(); }
  }
  fab.addEventListener("click", () => {
    seen = 0;
    badge();
    render();
    if (!dialog.open) dialog.showModal();
    show(tab);
  });
  dialog.querySelector(".dialog-x").addEventListener("click", close);
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) return close();
    const which = e.target.closest("[data-tab]")?.dataset.tab;
    if (which) return show(which);
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "csv" || act === "json") download(act);
    if (act === "clear") { site = []; save(); render(); }
  });
  dialog.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
  q(".log-errors input").addEventListener("change", (e) => { onlyErrors = e.target.checked; render(); });
  if (window.TG) window.TG.onLang(() => { words(); if (dialog.open) render(); });
  words();
  badge();
  log("system", "page loaded", location.pathname);
})();
