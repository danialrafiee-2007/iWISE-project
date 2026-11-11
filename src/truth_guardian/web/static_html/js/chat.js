// The conversation on the home page, as in a chat. The person writes a question, or speaks it (the recording is
// turned into text by the local speech reader, /api/media/read, and put in the box to read over), or adds documents,
// recordings and images (each read and added to their documents, /api/library/documents). The question then goes to
// /api/ask: the local model answers from those files and the project's documents, and the Guardian checks the answer
// before it is shown, with its verdict, risk, claims and sources (the Guardian's report).
// When the documents hold no answer, the question goes online to a free model (no Claude, nothing paid; /api/ask/free,
// rag/free.py): the Guardian reads the pages the model named, finds its own sources on Wikipedia, and the project's own
// models check every claim; each source is labelled (supports, contradicts, unrelated, could not be opened).
// "Truth Guardian check" then shows the last answer's full report under the chat, on this page.

(() => {
  const form = document.getElementById("composer");
  if (!form) return;
  const log = document.getElementById("chat-log");
  const input = document.getElementById("chat-input");
  const fileInput = document.getElementById("chat-file");
  const fileList = document.getElementById("composer-files");
  const mic = document.getElementById("chat-mic");
  const note = document.getElementById("composer-note");
  const send = document.getElementById("chat-send");
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const lang = () => (window.TG ? window.TG.lang : "en");
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const history = [];
  const uploads = new Set(); // files still being read
  const MAX_DOC = 10_000_000;
  const MAX_MEDIA = 25_000_000;
  const MEDIA = /\.(png|jpe?g|webp|bmp|tiff?|gif|wav|mp3|m4a|ogg|opus|flac|aac|wma|weba|webm)$/i;

  // ---- The server's streamed answers: one JSON event per line, the last of type "result" or "error". ----
  async function stream(url, payload, onEvent) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;
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
        if (event.type === "result") result = event;
        else onEvent(event);
      }
      if (done) break;
    }
    return result;
  }

  const base64 = (blob) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });

  function say(text) { note.textContent = text || ""; }

  // ---- Files: each is read and added to the person's documents, shown as a chip while it is read ----
  async function addFile(file) {
    const limit = MEDIA.test(file.name) ? MAX_MEDIA : MAX_DOC;
    const chip = document.createElement("li");
    chip.className = "file-chip";
    chip.innerHTML = `<span class="file-name"></span><span class="file-state"></span>`;
    chip.querySelector(".file-name").textContent = file.name;
    fileList.hidden = false;
    fileList.appendChild(chip);
    const state = chip.querySelector(".file-state");
    if (file.size > limit) {
      chip.classList.add("bad");
      state.textContent = tr("html.chat.failed", { name: "", error: `> ${Math.round(limit / 1e6)} MB` }).replace(/^\s*:?\s*/, "");
      return;
    }
    const job = (async () => {
      state.textContent = "…";
      chip.classList.add("busy");
      try {
        const data = await base64(file);
        await stream("/api/library/documents", { name: file.name, data, describe: true }, (event) => {
          if (event.stage === "embedding" && event.total) state.textContent = `${Math.round((100 * event.done) / event.total)}%`;
        });
        chip.classList.remove("busy");
        chip.classList.add("ok");
        state.textContent = "✓";
        window.TGLog?.log("chat", "file added", `${file.name} (${file.type || "file"}, ${Math.round(file.size / 1024)} KB)`);
        addNote(tr("html.chat.added", { name: file.name }));
      } catch (e) {
        chip.classList.remove("busy");
        chip.classList.add("bad");
        state.textContent = "!";
        addNote(tr("html.chat.failed", { name: file.name, error: e.message }), "bad");
      }
    })();
    uploads.add(job);
    job.finally(() => uploads.delete(job));
  }

  fileInput.addEventListener("change", () => {
    [...fileInput.files].forEach(addFile);
    fileInput.value = "";
  });

  // ---- Speaking: the microphone records, the local speech reader writes it out into the box ----
  let recorder = null;
  let chunks = [];
  mic.addEventListener("click", async () => {
    if (recorder && recorder.state === "recording") {
      recorder.stop();
      return;
    }
    try {
      const streamIn = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(streamIn);
      chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = async () => {
        streamIn.getTracks().forEach((t) => t.stop());
        mic.classList.remove("recording");
        mic.setAttribute("aria-pressed", "false");
        say(tr("html.chat.transcribing"));
        try {
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const res = await fetch("/api/media/read", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: "recording.webm", data: await base64(blob), kind: "audio" }),
          });
          const body = await res.json();
          if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
          const words = (body.reading?.segments || []).map((s) => s.text).join(" ").trim();
          input.value = [input.value.trim(), words].filter(Boolean).join(" ");
          grow();
          input.focus();
          say("");
        } catch (e) {
          say(tr("html.chat.error", { error: e.message }));
        }
      };
      recorder.start();
      mic.classList.add("recording");
      mic.setAttribute("aria-pressed", "true");
      say(tr("html.chat.listening"));
    } catch {
      say(tr("html.chat.micBlocked"));
    }
  });

  // ---- The conversation ----
  // The newest message comes into view inside the chat, which scrolls by itself; the page around it does not move (D-201).
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const toBottom = () => requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
  function bubble(role) {
    const li = document.createElement("li");
    li.className = `msg ${role}`;
    li.innerHTML = `<span class="msg-who">${esc(tr(role === "user" ? "html.chat.you" : "html.chat.guardian"))}</span><div class="msg-body"></div>`;
    log.appendChild(li);
    toBottom();
    return li.querySelector(".msg-body");
  }
  function addNote(text, kind = "") {
    const li = document.createElement("li");
    li.className = `msg note ${kind}`;
    li.textContent = text;
    log.appendChild(li);
  }

  const STATUS = { checked: "html.chat.checked", healed: "html.chat.healed", light: "html.chat.light", opinion: "html.chat.opinion", unchecked: "html.chat.unchecked", stopped: "html.chat.stopped" };

  const STANCE = (c) => (c.stance ? `<span class="stance ${c.stance}">${esc(tr(`html.free.st.${c.stance}`))}</span>` : "");
  const FOUND_BY = (c) => (c.found_by ? `<span class="rp-small">${esc(tr(`html.free.by.${c.found_by}`))}</span>` : "");
  const isFree = (a) => String(a.generator || "").startsWith("free-online");
  const freeModel = (a) => String(a.generator || "").split(":").slice(1).join(":");

  // The sources: for an online answer each carries what the check found it says (supports, contradicts, unrelated,
  // could not be opened) and who brought it (the model or the Guardian); the documents' passages as before.
  function sourcesHTML(a, open = false) {
    if (!a.citations.length) return "";
    return `<details class="sources"${open ? " open" : ""}><summary>${esc(isFree(a) ? tr("html.free.sourcesTitle") : tr("html.chat.sources"))} (${a.citations.length})</summary><ol>${a.citations.map((c) => `
      <li><strong dir="auto">[${c.n}] ${esc(c.document)}${c.page ? ` · p. ${c.page}` : ""}</strong>
        ${c.stance || c.found_by ? `<span class="source-tags">${STANCE(c)}${FOUND_BY(c)}</span>` : ""}
        ${c.text ? `<span dir="auto">${esc(c.text.slice(0, 320))}${c.text.length > 320 ? "…" : ""}</span>` : ""}
        ${c.place && /^https?:/.test(c.place) ? `<a class="rp-small mono" dir="ltr" href="${esc(c.place)}" target="_blank" rel="noopener noreferrer">${esc(c.place)}</a>` : ""}</li>`).join("")}</ol></details>`;
  }

  // The server's notes on a free online answer come in English (rag/free.py); they are shown in the page's language.
  const count = (n) => new Intl.NumberFormat(({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang()).format(Number(n));
  const NOTES = [
    [/^answered online by a free model/, () => tr("html.free.n.main")],
    [/^(\d+) page\(s\) the model named could not be opened; they may not exist: (.*)$/, (m) => tr("html.free.n.missing", { n: count(m[1]), urls: m[2] })],
    [/^(\d+) page\(s\) the model named do not exist \(the address answers not found\): (.*)$/, (m) => tr("html.free.n.gone", { n: count(m[1]), urls: m[2] })],
    [/^(\d+) page\(s\) the model named could not be read; the site may keep programs out: (.*)$/, (m) => tr("html.free.n.shut", { n: count(m[1]), urls: m[2] })],
    [/^the model named no page for its answer$/, () => tr("html.free.n.noPage")],
    [/^no source was found to check it against$/, () => tr("html.free.n.noSource")],
    [/^the free model wrote no answer$/, () => tr("html.free.n.noAnswer")],
    [/^the answer written from the documents did not pass the Guardian's check/, () => tr("html.free.n.local")],
    [/^this answer rests on what an image model says it sees/, () => tr("html.free.n.opinion")],
  ];
  function noteText(note) {
    for (const [pattern, say] of NOTES) {
      const m = String(note).match(pattern);
      if (m) return { text: say(m), own: true };
    }
    return { text: String(note), own: false };
  }
  const noteHTML = (note) => {
    const n = noteText(note);
    return `<p class="report-note"${n.own ? ' dir="auto"' : ' lang="en" dir="ltr"'}>${esc(n.text)}</p>`;
  };

  // The light check (a language no full check reads): each sentence close to the sources or doubtful, and why.
  const REASON = { "a number is not in the documents": "html.full.r.number", "a day or month is not in the documents": "html.full.r.day", "no passage is close to this sentence": "html.full.r.far" };
  // An answer about an image (D-199): what it says the image reads, checked against the separate OCR reader; a
  // green, red or grey line for the verdict, the share that could be checked, each sentence, and what was read.
  const SEEN_TONE = { grounded: "supports", hallucinated: "contradicts", disputed: "disputed", unverifiable: "unjudged" };
  const SEEN_STANCE = { supported: "supports", contradicted: "contradicts", agreed: "supports", disputed: "disputed", unverifiable: "unjudged" };
  function seenHTML(a) {
    const seen = a.seen;
    if (!seen) return "";
    const share = new Intl.NumberFormat(({ fa: "fa-IR", ar: "ar-u-nu-latn" })[lang()] || lang(), { style: "percent", maximumFractionDigits: 0 }).format(seen.checked_share);
    return `<div class="rp-card seen-card ${seen.verdict}">
      <h4>${esc(tr("html.seen.title"))}</h4>
      <p class="seen-verdict ${SEEN_TONE[seen.verdict]}">${esc(tr(`html.seen.${seen.verdict}`))}</p>
      <p class="rp-small">${esc(tr("html.seen.share", { p: share }))}</p>
      <ul class="light-list">${seen.claims.map((c) => `<li class="${c.status === "contradicted" ? "doubtful" : ""}"><span class="stance ${SEEN_STANCE[c.status]}">${esc(tr(`html.seen.st.${c.status}`))}</span><span dir="auto">${esc(c.text)}</span><span class="rp-small">${esc(tr(`html.seen.r.${c.reason}`))}</span></li>`).join("")}</ul>
      <p class="rp-small">${seen.read ? `${esc(tr("html.seen.read"))} <span class="seen-read" dir="auto">${esc(seen.read)}</span>` : esc(tr("html.seen.none"))}</p>
    </div>`;
  }

  // A second online model's opinion on the image or the recording (D-200): its verdict in green, orange or grey, each
  // sentence of the answer agreed or disputed by it, what it answered or heard, and the caution that agreeing is no proof.
  const SECOND_TONE = { agreed: "supports", disputed: "disputed", unclear: "unjudged" };
  function secondHTML(a) {
    const second = a.second;
    if (!second) return "";
    return `<div class="rp-card seen-card">
      <h4>${esc(tr(`html.second.title.${second.kind}`, { m: second.model }))}</h4>
      <p class="seen-verdict ${SECOND_TONE[second.verdict]}">${esc(tr(`html.second.${second.verdict}`))}</p>
      <ul class="light-list">${second.claims.map((c) => `<li class="${c.status === "disputed" ? "doubtful" : ""}"><span class="stance ${SECOND_TONE[c.status]}">${esc(tr(`html.second.st.${c.status}`))}</span><span dir="auto">${esc(c.text)}</span></li>`).join("")}</ul>
      <p class="rp-small">${esc(tr(`html.second.said.${second.kind}`))} <span class="seen-read" dir="auto">${esc(second.text)}</span></p>
      ${second.read ? `<p class="rp-small">${esc(tr("html.second.read"))} <span class="seen-read" dir="auto">${esc(second.read)}</span></p>` : ""}
      <p class="rp-small">${esc(tr("html.second.caution"))}</p>
    </div>`;
  }

  function lightHTML(a) {
    if (!a.light?.length) return "";
    return `<ul class="light-list">${a.light.map((l) => `<li class="${l.status}"><span class="stance ${l.status === "close" ? "supports" : "contradicts"}">${esc(tr(l.status === "close" ? "html.full.close" : "html.full.doubtful"))}</span><span dir="auto">${esc(l.text)}</span>${l.reasons.length ? `<span class="rp-small">${l.reasons.map((r) => esc(REASON[r] ? tr(REASON[r]) : r)).join(" · ")}</span>` : ""}</li>`).join("")}</ul>`;
  }

  function showAnswer(box, a, kept = null) {
    if (a.status === "not_in_documents") {
      box.innerHTML = `<p>${esc(a.text)}</p>`;
      return;
    }
    // Online, or written offline from what was learned online (D-222).
    const fromLearned = (a.citations || []).some((c) => c.collection === "learned");
    const online = isFree(a) ? `<p class="online-tag">${esc(tr("html.free.tag", { m: freeModel(a) }))}</p>`
      : fromLearned ? `<p class="online-tag learn-tag">${esc(tr("html.learn.from"))}</p>` : "";
    const keptNote = kept ? `<p class="learn-kept">${esc(tr("html.learn.kept"))}</p>` : "";
    if (!a.text) {
      box.innerHTML = `${online}<p class="msg-off">${esc((a.notes || []).map((n) => noteText(n).text).join(" · ") || tr("html.chat.error", { error: "" }))}</p>`;
      return;
    }
    // The answer alone, as in a chat (D-198): the Guardian's report, the sources and their labels open under the chat
    // with "Truth Guardian check", never inside the bubble.
    box.innerHTML = `
      ${online}
      <p class="msg-text" dir="auto">${esc(a.text)}</p>
      ${keptNote}
      <p class="msg-hint">${esc(tr("html.chat.hint"))}</p>`;
  }

  // An answer written from the documents that the Guardian's own check does not trust: a hallucination verdict, or half
  // or more of its sentences doubtful under the light check. It is not shown; the question goes online instead (D-198).
  function untrusted(a) {
    if (a.status === "light") {
      const doubtful = (a.light || []).filter((l) => l.status === "doubtful").length;
      return (a.light || []).length > 0 && doubtful * 2 >= a.light.length;
    }
    return a.status === "checked" && a.report?.verdict === "hallucinated";
  }

  // ---- "Truth Guardian check": the last answer's full report, in a window over the page (D-201) ----
  // It opens as the team's introductions do, softly, and its content scrolls inside it when it is longer than the screen.
  const checkBtn = document.getElementById("chat-check");
  const full = document.getElementById("chat-full");
  const fullBody = full?.querySelector(".report-dialog-body");
  let last = null;
  function closeFull() {
    if (!full?.open || full.classList.contains("closing")) return;
    if (reduced) return full.close();
    full.classList.add("closing");
    setTimeout(() => { full.close(); full.classList.remove("closing"); }, 320);
  }
  if (full) {
    full.querySelector(".dialog-x").addEventListener("click", closeFull);
    full.addEventListener("click", (e) => { if (e.target === full) closeFull(); });
    full.addEventListener("cancel", (e) => { e.preventDefault(); closeFull(); });
  }
  function drawFull() {
    if (!fullBody || !last) return;
    const a = last.answer;
    fullBody.innerHTML = `
      <h2 class="section-title report-dialog-title" id="chat-full-title">${esc(tr("html.full.title"))}</h2>
      <p class="section-note"><strong>${esc(tr("html.full.question"))}:</strong> <span dir="auto">${esc(last.question)}</span></p>
      ${isFree(a) ? `<p class="online-tag">${esc(tr("html.free.tag", { m: freeModel(a) }))}</p>` : ""}
      <p class="mono rp-small">${esc(tr("html.full.meta", { g: a.generator || "", s: Number(a.seconds || 0).toFixed(1) }))}</p>
      ${seenHTML(a)}
      ${secondHTML(a)}
      <div id="chat-full-report"></div>
      ${a.light?.length ? `<div class="rp-card"><h4>${esc(tr("html.full.light"))}</h4>${lightHTML(a)}</div>` : ""}
      ${a.citations.length ? `<div class="rp-card full-sources">${sourcesHTML(a, true)}</div>` : ""}
      ${(a.notes || []).length ? `<div class="rp-card"><h4>${esc(tr("html.full.notes"))}</h4>${a.notes.map(noteHTML).join("")}</div>` : ""}`;
    const body = fullBody.querySelector("#chat-full-report");
    if (a.report && window.TGReport) window.TGReport.render(body, a);
    else body.innerHTML = `<p class="msg-text" dir="auto">${esc(a.text)}</p>`;
  }
  function remember(question, a) {
    if (!a.text || a.status === "not_in_documents") return;
    last = { question, answer: a };
    checkBtn.disabled = false;
    if (full?.open) drawFull();
  }
  checkBtn?.addEventListener("click", () => {
    if (!last) return;
    window.TGLog?.log("chat", "Truth Guardian check", last.question);
    drawFull();
    if (full && !full.open) full.showModal();
    if (fullBody) fullBody.scrollTop = 0;
  });
  if (window.TG) window.TG.onLang(() => { if (full?.open) drawFull(); });

  // ---- What it learned online (D-222): the online answers the Guardian verified, kept to be answered offline ----
  // A window lists them newest first, each one shown in full on request and removable; a switch turns the keeping off.
  const learnBtn = document.getElementById("chat-learned");
  const learnDialog = document.getElementById("learn-dialog");
  const learnBody = learnDialog?.querySelector(".learn-body");
  let learned = null; // { on, items: [{ id, question, added_at, seed }] }
  const shownText = new Map(); // id -> the kept text, once shown
  const learnCount = (n) => new Intl.NumberFormat(lang() === "fa" ? "fa-IR" : lang() === "ar" ? "ar-u-nu-latn" : lang()).format(n);
  async function loadLearned() {
    try {
      const res = await fetch("/api/learned");
      if (res.ok) learned = await res.json();
    } catch { /* the library is not ready yet */ }
    const n = learnBtn?.querySelector("[data-n]");
    if (n && learned) { n.textContent = learnCount(learned.items.length); n.hidden = false; }
    if (learnDialog?.open) drawLearned();
  }
  function drawLearned() {
    if (!learnBody) return;
    const items = learned?.items || [];
    learnBody.innerHTML = `
      <h2 class="section-title" id="learn-title">${esc(tr("html.learn.title"))}</h2>
      <p class="section-note">${esc(tr("html.learn.lead"))}</p>
      <label class="learn-switch"><input type="checkbox" id="learn-on" ${learned?.on === false ? "" : "checked"}><span>${esc(tr("html.learn.on"))}</span></label>
      ${learned?.on === false ? `<p class="rp-small">${esc(tr("html.learn.off"))}</p>` : ""}
      ${items.length ? `<ol class="learn-list">${items.map((it) => `
        <li class="learn-item">
          <div class="learn-row">
            <span class="learn-q" dir="auto">${esc(it.question)}</span>
            <span class="learn-meta mono">${esc((it.added_at || "").slice(0, 10))}${it.seed ? ` · <span class="learn-seed">${esc(tr("html.learn.seed"))}</span>` : ""}</span>
            <span class="learn-acts">
              <button type="button" class="btn-ghost" data-show="${it.id}">${esc(tr(shownText.has(it.id) ? "html.learn.hide" : "html.learn.show"))}</button>
              <button type="button" class="btn-ghost" data-forget="${it.id}">${esc(tr("html.learn.remove"))}</button>
            </span>
          </div>
          ${shownText.has(it.id) ? `<pre class="learn-text" dir="auto">${esc(shownText.get(it.id))}</pre>` : ""}
        </li>`).join("")}</ol>` : `<p class="rp-small">${esc(tr("html.learn.empty"))}</p>`}`;
    learnBody.querySelector("#learn-on")?.addEventListener("change", async (e) => {
      const on = e.target.checked;
      await fetch("/api/learned/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }) });
      window.TGLog?.log("chat", "learning online", on ? "on" : "off");
      await loadLearned();
    });
    learnBody.querySelectorAll("[data-show]").forEach((b) => b.addEventListener("click", async () => {
      const id = +b.dataset.show;
      if (shownText.has(id)) shownText.delete(id);
      else {
        const res = await fetch(`/api/library/documents/${id}/passages`);
        const { passages = [] } = res.ok ? await res.json() : {};
        shownText.set(id, passages.map((p) => p.text).join("\n"));
      }
      drawLearned();
    }));
    learnBody.querySelectorAll("[data-forget]").forEach((b) => b.addEventListener("click", async () => {
      const id = +b.dataset.forget;
      await fetch(`/api/learned/${id}`, { method: "DELETE" });
      shownText.delete(id);
      window.TGLog?.log("chat", "forgot what was learned", String(id));
      await loadLearned();
    }));
  }
  function closeLearned() {
    if (!learnDialog?.open || learnDialog.classList.contains("closing")) return;
    if (reduced) return learnDialog.close();
    learnDialog.classList.add("closing");
    setTimeout(() => { learnDialog.close(); learnDialog.classList.remove("closing"); }, 320);
  }
  if (learnDialog) {
    learnDialog.querySelector(".dialog-x").addEventListener("click", closeLearned);
    learnDialog.addEventListener("click", (e) => { if (e.target === learnDialog) closeLearned(); });
    learnDialog.addEventListener("cancel", (e) => { e.preventDefault(); closeLearned(); });
  }
  learnBtn?.addEventListener("click", async () => {
    drawLearned();
    if (learnDialog && !learnDialog.open) learnDialog.showModal();
    await loadLearned();
  });
  if (window.TG) window.TG.onLang(() => { if (learnDialog?.open) drawLearned(); });
  // The count on the button once the models are up (the library opens with them), and after each answer kept.
  setTimeout(loadLearned, 4000);

  let busy = false;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (busy || !question) return;
    busy = true;
    send.disabled = true;
    input.value = "";
    grow();
    // The files added with the question are read and in the documents before it is asked, so it is answered from them.
    if (uploads.size) {
      say(tr("html.chat.thinking"));
      await Promise.allSettled([...uploads]);
      say("");
    }
    bubble("user").textContent = question;
    window.TGLog?.log("chat", "ask", question);
    const box = bubble("assistant");
    box.innerHTML = `<p class="thinking">${esc(tr("html.chat.thinking"))}</p>`;
    try {
      let written = "";
      const result = await stream("/api/ask", { question, history: history.slice(-8), language: lang() }, (event) => {
        if (event.type === "text") written = event.text; // kept back until the Guardian has checked it
      });
      let a = result.answer;
      let kept = null; // what was kept of an online answer, to be answered offline next time (D-222)
      // Not in the documents: the question goes to a free online model, and its answer comes back checked by the
      // project's own models against the pages it named and sources the Guardian found (/api/ask/free). Each step is told.
      const rejected = untrusted(a);
      if (a.status === "not_in_documents" || rejected) {
        // The model's answer is shown the moment it comes; the Guardian's steps go on under it until its report is ready.
        let said = "";
        const status = (text) => { box.innerHTML = `${said ? `<p class="msg-text" dir="auto">${esc(said)}</p>` : ""}<p class="thinking">${esc(text)}</p>`; };
        let countdown = 0;
        status(tr("html.chat.online"));
        window.TGLog?.log("chat", "went online", rejected ? "the documents' answer did not pass the check" : "not in the documents");
        try {
          const online = await stream("/api/ask/free", { question }, (event) => {
            if (event.type === "text") { said = event.text; return; }
            if (event.type !== "stage") return;
            clearInterval(countdown);
            if (event.stage === "online") status(tr("html.free.asking", { p: `${event.provider} · ${event.model}` }));
            if (event.stage === "waiting") {
              let left = event.seconds;
              status(tr("html.free.waiting", { s: left }));
              countdown = setInterval(() => { left = Math.max(0, left - 1); status(tr("html.free.waiting", { s: left })); }, 1000);
            }
            if (event.stage === "sources") status(tr("html.free.sources"));
            if (event.stage === "check") status(tr("html.free.checking"));
          });
          a = online.answer;
          kept = online.learned || null;
          if (rejected) a = { ...a, notes: ["the answer written from the documents did not pass the Guardian's check, so the question was asked online", ...(a.notes || [])] };
        } finally {
          clearInterval(countdown);
        }
      }
      showAnswer(box, a, kept);
      if (kept) {
        window.TGLog?.log("chat", "learned online", kept.question);
        loadLearned();
      }
      remember(question, a);
      window.TGLog?.log("chat", "answer", [a.generator, a.status, a.report?.verdict, a.report ? `risk ${(+a.report.risk).toFixed(2)}` : ""].filter(Boolean).join(" · "));
      history.push({ role: "user", content: question.slice(0, 5000) }, { role: "assistant", content: String(a.text).slice(0, 5000) });
      fileList.innerHTML = "";
      fileList.hidden = true;
    } catch (err) {
      // A free service that asks for a longer wait than the server waits says so in the page's language.
      const busy = /free service .* (is|still) busy/.test(err.message);
      box.innerHTML = `<p class="msg-off">${esc(busy ? tr("html.free.busy") : tr("html.chat.error", { error: err.message }))}</p>`;
      window.TGLog?.log("chat", "failed", err.message, "error");
    } finally {
      busy = false;
      send.disabled = false;
      toBottom();
    }
  });

  // The box grows with what is written, up to a few lines; Enter sends, Shift+Enter starts a new line.
  function grow() {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  }
  input.addEventListener("input", grow);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
})();
