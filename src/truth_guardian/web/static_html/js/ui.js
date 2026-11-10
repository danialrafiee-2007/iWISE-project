// The site's languages, the rail's two menus (the tour and the languages) and the tour itself, after the React
// site's LanguageMenu, TourMenu and Tour. No framework: plain DOM.

(() => {
  const MESSAGES = window.TG_MESSAGES || { en: {} };
  // The previous site's seven languages, in its order; Arabic and Persian named in English (the list reads left to right).
  const LANGUAGES = [
    { code: "en", name: "English", dir: "ltr" },
    { code: "ar", name: "Arabic", dir: "rtl" },
    { code: "zh", name: "中文", dir: "ltr" },
    { code: "fr", name: "Français", dir: "ltr" },
    { code: "ru", name: "Русский", dir: "ltr" },
    { code: "es", name: "Español", dir: "ltr" },
    { code: "fa", name: "Persian", dir: "rtl" },
  ];
  const STORAGE = "tg-lang";
  const root = document.documentElement;
  const find = (code) => LANGUAGES.find((l) => l.code === String(code || "").toLowerCase().split("-")[0]);

  // As the previous site: ?lang=, then the last choice on this browser, then the browser's own language, then English.
  function detect() {
    try {
      const fromUrl = find(new URLSearchParams(location.search).get("lang"));
      if (fromUrl) return fromUrl.code;
    } catch { /* no URL */ }
    try {
      const saved = find(localStorage.getItem(STORAGE));
      if (saved) return saved.code;
    } catch { /* storage unavailable */ }
    for (const code of navigator.languages || [navigator.language]) {
      const match = find(code);
      if (match) return match.code;
    }
    return "en";
  }

  let lang = detect();
  const listeners = new Set();

  function t(key, vars) {
    const text = (MESSAGES[lang] && MESSAGES[lang][key]) || (MESSAGES.en && MESSAGES.en[key]) || key;
    return vars ? text.replace(/\{(\w+)\}/g, (all, name) => (name in vars ? String(vars[name]) : all)) : text;
  }

  // Every marked element takes its words in the chosen language: text (data-i18n), the rail's name tag and
  // accessible name (data-i18n-label) and a list's accessible name (data-i18n-aria).
  function apply() {
    const info = find(lang) || LANGUAGES[0];
    root.lang = info.code;
    root.dir = info.dir;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    // In every page title, "Guardian" takes the home page's look: italic, in the site's peach (".title-text em").
    document.querySelectorAll(".title-text[data-i18n]").forEach((el) => {
      const text = el.textContent;
      const at = text.indexOf("Guardian");
      if (at < 0) return;
      el.textContent = text.slice(0, at);
      const em = document.createElement("em");
      em.textContent = "Guardian";
      el.append(em, text.slice(at + "Guardian".length));
    });
    document.querySelectorAll("[data-i18n-label]").forEach((el) => {
      const text = t(el.dataset.i18nLabel);
      el.dataset.label = text;
      el.setAttribute("aria-label", text);
      if (el.matches(".tool-btn, .send-btn")) el.title = text; // the composer's buttons show their name under the pointer
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
    const intro = document.getElementById("intro");
    if (intro) intro.setAttribute("aria-label", `Truth Guardian. ${t("splash.enter")}`);
    renderLanguages();
    listeners.forEach((fn) => fn(lang));
  }

  function setLang(code) {
    if (!find(code) || code === lang) return;
    lang = code;
    window.TGLog?.log("language", "changed", code);
    try { localStorage.setItem(STORAGE, code); } catch { /* storage unavailable */ }
    apply();
  }

  window.TG = { t, setLang, get lang() { return lang; }, onLang: (fn) => listeners.add(fn) };

  // ---- The rail's menus: a click or tap opens one beside the rail; Esc, a click outside or a choice closes it ----

  const CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

  function renderLanguages() {
    const list = document.getElementById("lang-menu");
    if (!list) return;
    list.innerHTML = "";
    for (const l of LANGUAGES) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "pop-item";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", String(l.code === lang));
      item.lang = l.dir === "rtl" ? "en" : l.code;
      item.innerHTML = `<span></span>${l.code === lang ? CHECK : ""}`;
      item.firstChild.textContent = l.name;
      item.addEventListener("click", () => {
        close();
        setLang(l.code);
      });
      list.appendChild(item);
    }
  }

  let openMenu = null;
  function close() {
    if (!openMenu) return;
    openMenu.querySelector(".pop").hidden = true;
    openMenu.querySelector(".rail-btn").setAttribute("aria-expanded", "false");
    openMenu.classList.remove("open");
    openMenu = null;
  }
  function open(menu, focus = true) {
    close();
    const pop = menu.querySelector(".pop");
    pop.hidden = false;
    menu.querySelector(".rail-btn").setAttribute("aria-expanded", "true");
    menu.classList.add("open");
    openMenu = menu;
    if (focus) (pop.querySelector('[aria-checked="true"]') || pop.querySelector(".pop-item:not([aria-disabled])"))?.focus();
  }

  document.querySelectorAll(".rail-menu").forEach((menu) => {
    // A click closes an open menu, except one the mouse has just opened by resting on it.
    menu.querySelector(".rail-btn").addEventListener("click", (e) => {
      if (openMenu !== menu) return open(menu);
      if (!(menu.hasAttribute("data-hover") && e.pointerType === "mouse")) close();
    });
    menu.querySelector(".pop").addEventListener("keydown", (e) => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const items = [...menu.querySelectorAll(".pop-item:not([aria-disabled])")];
      const at = items.indexOf(document.activeElement);
      items[(at + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
    });
  });
  // A menu marked data-hover (the AI engine) also opens while the mouse rests on it and closes a moment after it
  // leaves, as the previous site's AI engine menu did; a click or tap still opens it on touch screens.
  document.querySelectorAll(".rail-menu[data-hover]").forEach((menu) => {
    let timer = 0;
    menu.addEventListener("pointerenter", (e) => {
      if (e.pointerType !== "mouse") return;
      clearTimeout(timer);
      if (openMenu !== menu) open(menu, false);
    });
    menu.addEventListener("pointerleave", (e) => {
      if (e.pointerType !== "mouse") return;
      timer = setTimeout(() => { if (openMenu === menu) close(); }, 260);
    });
  });
  window.TG.closeMenus = close;

  // ---- The rail comes alive under the mouse: a light follows the pointer along it (--ly), and each icon grows and
  // rises the nearer the pointer is (--mag), like a dock. Mouse only; nothing moves for those who ask for less. ----
  const rail = document.querySelector(".rail");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (rail && !reducedMotion) {
    const buttons = [...rail.querySelectorAll(".rail-btn:not(.rail-lamp)")];
    let frame = 0;
    let lastY = null;
    const RANGE = 80; // px from an icon's centre at which it starts to grow
    const GROW = 0.26; // how much larger the icon right under the pointer is
    const update = () => {
      frame = 0;
      const box = rail.getBoundingClientRect();
      rail.style.setProperty("--ly", lastY === null ? "-200px" : `${lastY - box.top}px`);
      for (const b of buttons) {
        let mag = 1;
        if (lastY !== null) {
          const r = b.getBoundingClientRect();
          const d = Math.abs(lastY - (r.top + r.height / 2));
          mag = 1 + GROW * Math.max(0, 1 - d / RANGE) ** 2;
        }
        b.style.setProperty("--mag", mag.toFixed(3));
      }
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    rail.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse") return;
      lastY = e.clientY;
      schedule();
    });
    rail.addEventListener("pointerleave", () => { lastY = null; schedule(); });
  }
  document.addEventListener("mousedown", (e) => { if (openMenu && !openMenu.contains(e.target)) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && openMenu) {
      const button = openMenu.querySelector(".rail-btn");
      close();
      button.focus();
    }
  });

  // ---- The site tour (D-209, D-211), after the previous site's, for the judges: the site as a whole, the home page,
  // Model performance, the brain (Architecture: its map, its three parts and six stages), Team, About and Contact. Each step opens its page (and tab), dims everything but the part it explains, and puts the card
  // where it covers none of that part; Back, Next, Autoplay (which counts only once the part is on screen), the arrow
  // keys and Escape, as there. The page stays usable underneath; only the card takes clicks. ----

  const STEPS = [
    { url: "/" },
    { url: "/", target: ".rail" },
    { url: "/", target: ".home-banner" },
    { url: "/", target: ".home-banner .status-stack", seconds: 10 },
    { url: "/", target: "#composer", seconds: 11 },
    { url: "/", target: "#chat-check", seconds: 10 },
    { url: "/", target: ".log-fab", seconds: 9 },
    { url: "/models", target: ".tabs" },
    { url: "/models", tab: "tab-report", target: "#panel-report", seconds: 10 },
    { url: "/models", tab: "tab-reliability", target: "#panel-reliability .stat-row", seconds: 10 },
    { url: "/models", tab: "tab-reliability", target: "#panel-reliability .calib-figure", seconds: 10 },
    { url: "/models", tab: "tab-agent", target: "#panel-agent", seconds: 10 },
    { url: "/models", tab: "tab-fool", target: "#panel-fool" },
    { url: "/architecture", graph: "guardian", target: ".ag-graph", seconds: 11 },
    { url: "/architecture", graph: "guardian", target: ".ag-graph", seconds: 14 },
    { url: "/architecture", graph: "answers", target: ".ag-graph", seconds: 12 },
    { url: "/architecture", graph: "readers", target: ".ag-graph", seconds: 11 },
    { url: "/architecture", target: ".arch-flow > li:nth-child(1)" },
    { url: "/architecture", target: ".arch-flow > li:nth-child(2)" },
    { url: "/architecture", target: ".arch-flow > li:nth-child(3)" },
    { url: "/architecture", target: ".arch-flow > li:nth-child(4)", seconds: 9 },
    { url: "/architecture", target: ".arch-flow > li:nth-child(5)" },
    { url: "/architecture", target: ".arch-flow > li:nth-child(6)" },
    { url: "/team", target: '.page[data-page="team"] .banner' },
    { url: "/about", target: 'section[aria-labelledby="about-engine"]' },
    { url: "/contact", target: '.page[data-page="contact"] .banner', seconds: 10 },
  ].map((step, i) => ({ ...step, title: `html.tour.s${i + 1}.t`, body: `html.tour.s${i + 1}.b` }));
  const SECONDS = 8;
  const PAD = 10;
  let tour = null;

  const visible = (selector) => [...document.querySelectorAll(selector)].find((el) => el.getClientRects().length > 0) || null;

  // The tour's card fades out softly, as everything else on the site.
  function stopTour() {
    if (!tour) return;
    clearInterval(tour.timer);
    const layer = tour.layer;
    tour = null;
    layer.classList.add("closing");
    setTimeout(() => layer.remove(), 320);
  }

  function words() {
    const step = STEPS[tour.index];
    const card = tour.layer.querySelector(".tour-card");
    card.querySelector(".tour-count").textContent = t("tour.count", { i: tour.index + 1, n: STEPS.length });
    card.querySelector(".tour-title").textContent = t(step.title);
    card.querySelector(".tour-body").textContent = t(step.body);
    card.querySelector('[data-act="back"]').disabled = tour.index === 0;
    card.querySelector('[data-act="back"]').textContent = t("tour.back");
    card.querySelector('[data-act="auto"]').textContent = tour.auto ? t("common.pause") : t("tour.autoplay");
    card.querySelector('[data-act="auto"]').setAttribute("aria-pressed", String(tour.auto));
    card.querySelector('[data-act="next"]').textContent = tour.index === STEPS.length - 1 ? t("tour.finish") : t("tour.next");
    card.querySelector('[data-act="close"]').setAttribute("aria-label", t("tour.close"));
    card.querySelector(".tour-bar").hidden = !tour.auto;
  }

  // Enter a step: its page, then its tab, then wait for its part and bring it into view once.
  async function showStep() {
    const step = STEPS[tour.index];
    // Only the latest step may go on after waiting: Next clicked quickly leaves earlier steps still waiting.
    const mine = tour, seq = (tour.seq = (tour.seq || 0) + 1);
    const current = () => tour === mine && tour.seq === seq;
    tour.found = false;
    tour.scrolled = false;
    tour.elapsed = 0;
    tour.layer.querySelector(".tour-bar span").style.width = "0%";
    words();
    // The new step's words may make the card taller: it takes its new place at once rather than sliding off the screen.
    const card = tour.layer.querySelector(".tour-card");
    card.style.transition = "none";
    place();
    requestAnimationFrame(() => requestAnimationFrame(() => { card.style.transition = ""; }));
    if (step.url !== location.pathname && window.TG?.go) {
      // A new page comes in with its layers rising; the part is brought into view once they have settled.
      tour.scrolled = true;
      // While a page changes (counted, as Next may be pressed again meanwhile) the spot is off and the card waits in
      // the middle; the step shown then finds its part once no page is still changing.
      tour.moves = (tour.moves || 0) + 1;
      try {
        await window.TG.go(step.url);
        await new Promise((done) => setTimeout(done, 900));
      } finally {
        tour.moves -= 1;
      }
      if (!current()) { if (!tour.moves) tour.scrolled = false; return; }
      tour.scrolled = false;
    }
    if (!current()) return;
    if (step.tab && document.getElementById(step.tab)?.getAttribute("aria-selected") !== "true") window.TG?.openTab?.(step.tab);
    // A step on the brain's map shows its part's graph (the Guardian, answers and online, the readers).
    const graphButton = step.graph && document.querySelector(`.ag-tabs [data-graph="${step.graph}"]`);
    if (graphButton && graphButton.getAttribute("aria-pressed") !== "true") graphButton.click();
    place();
  }

  // Dim around the part (or the whole page when the step has none) and set the card where it covers none of it:
  // below, above, beside, else at the bottom corner; on a narrow screen always at the bottom.
  function place() {
    if (!tour) return;
    const step = STEPS[tour.index];
    const spot = tour.layer.querySelector(".tour-spot");
    const card = tour.layer.querySelector(".tour-card");
    const el = step.target && !tour.moves ? visible(step.target) : null;
    if (el && !tour.scrolled) {
      tour.scrolled = true;
      const r = el.getBoundingClientRect();
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
      // The part is brought near the top of the screen; a taller one keeps only its top lit (below).
      window.scrollBy({ top: r.top - PAD * 3, behavior });
    }
    const vw = window.innerWidth, vh = window.innerHeight;
    const width = Math.min(400, vw - 32), height = card.offsetHeight || 240, gap = PAD + 14;
    let box = { left: (vw - width) / 2, top: Math.max(16, vh / 2 - height / 2) };
    if (el) {
      const r = el.getBoundingClientRect();
      // A part taller than the screen leaves room under it for the card: only its top is lit (D-209).
      const top = Math.max(r.top, 8), bottom = Math.min(r.bottom, vh - 8, Math.max(top + 120, vh - height - gap - PAD - 16));
      Object.assign(spot.style, { top: `${top - PAD}px`, left: `${r.left - PAD}px`, width: `${r.width + PAD * 2}px`, height: `${Math.max(0, bottom - top) + PAD * 2}px` });
      spot.classList.add("on");
      tour.found = true;
      const alongX = Math.min(Math.max(16, r.left), vw - width - 16);
      const alongY = Math.min(Math.max(16, top), vh - height - 16);
      if (vw < 640) box = { left: 16, top: vh - height - 16 };
      else if (bottom + gap + height <= vh - 8) box = { left: alongX, top: bottom + gap };
      else if (top - gap - height >= 8) box = { left: alongX, top: top - gap - height };
      else if (vw - r.right - gap >= width + 16) box = { left: r.right + gap, top: alongY };
      else if (r.left - gap >= width + 16) box = { left: r.left - gap - width, top: alongY };
      else box = { left: vw - width - 16, top: vh - height - 16 };
    } else {
      spot.classList.remove("on");
      tour.found = !step.target;
    }
    // The card always stays on the screen.
    box.top = Math.min(Math.max(16, box.top), vh - height - 16);
    Object.assign(card.style, { width: `${width}px`, left: `${box.left}px`, top: `${box.top}px` });
  }

  function go(delta) {
    const next = tour.index + delta;
    if (next >= STEPS.length) { window.TGLog?.log("tour", "finished"); return stopTour(); }
    tour.index = Math.max(0, next);
    showStep();
  }

  function startTour(auto = false) {
    stopTour();
    window.TGLog?.log("tour", auto ? "played by itself" : "started");
    const layer = document.createElement("div");
    layer.className = "tour-layer";
    layer.innerHTML = `
      <div class="tour-dim"></div>
      <div class="tour-spot"></div>
      <div class="tour-card" role="dialog" aria-modal="false" aria-labelledby="tour-title" tabindex="-1">
        <div class="tour-head"><span class="tour-count"></span>
          <button type="button" class="tour-x" data-act="close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
        </div>
        <h2 class="tour-title" id="tour-title"></h2>
        <p class="tour-body"></p>
        <div class="tour-bar" hidden><span></span></div>
        <div class="tour-actions">
          <button type="button" class="btn-ghost" data-act="back"></button>
          <button type="button" class="btn-ghost" data-act="auto"></button>
          <button type="button" class="btn-primary" data-act="next"></button>
        </div>
      </div>`;
    document.body.appendChild(layer);
    tour = { layer, index: 0, auto, elapsed: 0, timer: null, found: false, scrolled: false };
    layer.addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]")?.dataset.act;
      if (act === "close") stopTour();
      if (act === "back") go(-1);
      if (act === "next") go(1);
      if (act === "auto") { tour.auto = !tour.auto; tour.elapsed = 0; words(); }
    });
    // Every tenth of a second: follow the part as the page moves, and in Autoplay fill the bar once it is on screen.
    tour.timer = setInterval(() => {
      if (!tour) return;
      place();
      if (!tour.auto || !tour.found) return;
      const seconds = STEPS[tour.index].seconds || SECONDS;
      tour.elapsed += 0.1;
      layer.querySelector(".tour-bar span").style.width = `${Math.min(100, (tour.elapsed / seconds) * 100)}%`;
      if (tour.elapsed >= seconds) go(1);
    }, 100);
    showStep();
    layer.querySelector(".tour-card").focus({ preventScroll: true });
  }

  document.addEventListener("keydown", (e) => {
    if (!tour) return;
    if (e.target.closest?.("input, textarea, select")) return;
    if (e.key === "Escape") stopTour();
    if (e.key === "ArrowRight") go(root.dir === "rtl" ? -1 : 1);
    if (e.key === "ArrowLeft") go(root.dir === "rtl" ? 1 : -1);
  });
  window.addEventListener("resize", () => { if (tour) tour.scrolled = true; });
  // One button in the rail starts the tour; its card has Autoplay for a hands-free run (D-211).
  document.querySelector('[data-tour="site"]')?.addEventListener("click", () => { close(); startTour(false); });
  listeners.add(() => { if (tour) words(); });

  apply();
})();
