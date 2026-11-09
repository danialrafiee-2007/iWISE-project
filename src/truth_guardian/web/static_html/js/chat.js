// The conversation on the home page, as in a chat. The person writes a question, or speaks it (the recording is
// turned into text by the local speech reader, /api/media/read, and put in the box to read over), or adds documents,
// recordings and images (each read and added to their documents, /api/library/documents). The question then goes to
// /api/ask: the local model answers from those files and the project's documents, and the Guardian checks the answer
// before it is shown, with its verdict, risk, claims and sources (the Guardian's report).
// When the documents hold no answer and the online model's key is set, the question goes online: Claude answers from
// the web and the local Guardian checks that answer against the pages it cited before it is shown (/api/ask/web,
// rag/web.py). Without the key the page says the online answer is off.

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
  function bubble(role) {
    const li = document.createElement("li");
    li.className = `msg ${role}`;
    li.innerHTML = `<span class="msg-who">${esc(tr(role === "user" ? "html.chat.you" : "html.chat.guardian"))}</span><div class="msg-body"></div>`;
    log.appendChild(li);
    li.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return li.querySelector(".msg-body");
  }
  function addNote(text, kind = "") {
    const li = document.createElement("li");
    li.className = `msg note ${kind}`;
    li.textContent = text;
    log.appendChild(li);
  }

  const STATUS = { checked: "html.chat.checked", healed: "html.chat.healed", light: "html.chat.light", opinion: "html.chat.opinion", unchecked: "html.chat.unchecked", stopped: "html.chat.stopped" };

  function showAnswer(box, a) {
    if (a.status === "not_in_documents") {
      box.innerHTML = `<p>${esc(a.text)}</p><p class="msg-off">${esc(tr("html.chat.notFound"))}</p>`;
      return;
    }
    const online = a.generator === "online-web" ? `<p class="online-tag">${esc(tr("html.chat.onlineTag"))}</p>` : "";
    if (!a.text) {
      box.innerHTML = `${online}<p class="msg-off">${esc((a.notes || []).join(" · ") || tr("html.chat.error", { error: "" }))}</p>`;
      return;
    }
    // The answer and, under it, the Guardian's report in full, as on the previous site's check page: the verdict card,
    // the answer with each claim coloured (a click on a claim shows its evidence, action and fix), then the notes and
    // the sources. Its whole report, with how the models read it, opens with "Truth Guardian check".
    const sources = a.citations.length
      ? `<details class="sources"><summary>${esc(tr("html.chat.sources"))} (${a.citations.length})</summary><ol>${a.citations.map((c) => `<li><strong>[${c.n}] ${esc(c.document)}${c.page ? ` · p. ${c.page}` : ""}</strong><span>${esc(c.text.slice(0, 320))}${c.text.length > 320 ? "…" : ""}</span>${c.place && /^https?:/.test(c.place) ? `<span class="rp-small mono" dir="ltr">${esc(c.place)}</span>` : ""}</li>`).join("")}</ol></details>`
      : "";
    box.innerHTML = `
      ${online}
      <div class="report-head"><span class="report-title">${esc(tr("html.chat.report"))}</span><span class="status-tag ${a.status}">${esc(tr(STATUS[a.status] || a.status))}</span></div>
      ${a.report ? "" : `<p class="msg-text">${esc(a.text)}</p>`}
      <div class="chat-report"></div>
      ${(a.notes || []).map((n) => `<p class="report-note" lang="en">${esc(n)}</p>`).join("")}
      ${sources}`;
    if (a.report && window.TGReport) window.TGReport.render(box.querySelector(".chat-report"), a, { compact: true });
  }

  // ---- "Truth Guardian check": the last checked answer's whole report on the Model performance page ----
  const checkBtn = document.getElementById("chat-check");
  let last = null;
  function fillReportPage() {
    const body = document.getElementById("report-body");
    const asked = document.getElementById("report-question");
    if (!body || !last || !window.TGReport) return;
    asked.textContent = `${tr("html.r.question")}: ${last.question}`;
    window.TGReport.render(body, last.answer);
  }
  function remember(question, a) {
    if (!a.report) return;
    last = { question, answer: a };
    checkBtn.disabled = false;
    fillReportPage();
  }
  checkBtn?.addEventListener("click", () => {
    if (!last) return;
    fillReportPage();
    if (window.TG?.openTab) window.TG.openTab("tab-report");
    if (window.TG?.go) window.TG.go("/models");
  });
  if (window.TG) window.TG.onLang(fillReportPage);

  // Whether the online model can answer here: its key is set (/api/ask/generators, "online").
  async function onlineOn() {
    try {
      const res = await fetch("/api/ask/generators", { cache: "no-store" });
      return res.ok && (await res.json()).online === true;
    } catch {
      return false;
    }
  }

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
    const box = bubble("assistant");
    box.innerHTML = `<p class="thinking">${esc(tr("html.chat.thinking"))}</p>`;
    try {
      let written = "";
      const result = await stream("/api/ask", { question, history: history.slice(-8), language: lang() }, (event) => {
        if (event.type === "text") {
          written = event.text;
          box.innerHTML = `<p class="msg-text streaming">${esc(written)}</p>`;
        }
      });
      let a = result.answer;
      // Not in the documents: when the online model is on (its key is set), the question goes online, and its answer
      // comes back checked by the local Guardian against the pages it cited (/api/ask/web). Otherwise it says so.
      if (a.status === "not_in_documents" && (await onlineOn())) {
        box.innerHTML = `<p class="thinking">${esc(tr("html.chat.online"))}</p>`;
        const web = await stream("/api/ask/web", { question }, () => {});
        a = web.answer;
      }
      showAnswer(box, a);
      remember(question, a);
      history.push({ role: "user", content: question.slice(0, 5000) }, { role: "assistant", content: String(a.text).slice(0, 5000) });
      fileList.innerHTML = "";
      fileList.hidden = true;
    } catch (err) {
      box.innerHTML = `<p class="msg-off">${esc(tr("html.chat.error", { error: err.message }))}</p>`;
    } finally {
      busy = false;
      send.disabled = false;
      box.closest(".msg").scrollIntoView({ behavior: "smooth", block: "nearest" });
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
