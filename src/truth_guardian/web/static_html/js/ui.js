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
    document.querySelectorAll("[data-i18n-label]").forEach((el) => {
      const text = t(el.dataset.i18nLabel);
      el.dataset.label = text;
      el.setAttribute("aria-label", text);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAria)));
    const intro = document.getElementById("intro");
    if (intro) intro.setAttribute("aria-label", `Truth Guardian. ${t("splash.enter")}`);
    renderLanguages();
    listeners.forEach((fn) => fn(lang));
  }

  function setLang(code) {
    if (!find(code) || code === lang) return;
    lang = code;
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
  document.addEventListener("mousedown", (e) => { if (openMenu && !openMenu.contains(e.target)) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && openMenu) {
      const button = openMenu.querySelector(".rail-btn");
      close();
      button.focus();
    }
  });

  // ---- The tour: the page dims and a card explains, with Back, Autoplay and Next, as on the previous site. Only its
  // first step belongs on this page so far; the others come with the pages they show. ----

  const STEPS = [{ title: "tour.s1.title", body: "tour.s1.body", seconds: 8 }];
  let tour = null;

  function stopTour() {
    if (!tour) return;
    clearInterval(tour.timer);
    tour.layer.remove();
    tour = null;
  }

  function showStep() {
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
    tour.elapsed = 0;
    card.querySelector(".tour-bar span").style.width = "0%";
  }

  function go(delta) {
    const next = tour.index + delta;
    if (next >= STEPS.length) return stopTour();
    tour.index = Math.max(0, next);
    showStep();
  }

  function startTour() {
    stopTour();
    const layer = document.createElement("div");
    layer.className = "tour-layer";
    layer.innerHTML = `
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
    tour = { layer, index: 0, auto: false, elapsed: 0, timer: null };
    layer.addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]")?.dataset.act;
      if (act === "close") stopTour();
      if (act === "back") go(-1);
      if (act === "next") go(1);
      if (act === "auto") { tour.auto = !tour.auto; showStep(); }
    });
    // Autoplay: a bar fills over the step's seconds, then the tour moves on by itself.
    tour.timer = setInterval(() => {
      if (!tour || !tour.auto) return;
      const seconds = STEPS[tour.index].seconds || 8;
      tour.elapsed += 0.1;
      layer.querySelector(".tour-bar span").style.width = `${Math.min(100, (tour.elapsed / seconds) * 100)}%`;
      if (tour.elapsed >= seconds) go(1);
    }, 100);
    showStep();
    layer.querySelector(".tour-card").focus();
  }

  document.addEventListener("keydown", (e) => {
    if (!tour) return;
    if (e.key === "Escape") stopTour();
    if (e.key === "ArrowRight") go(root.dir === "rtl" ? -1 : 1);
    if (e.key === "ArrowLeft") go(root.dir === "rtl" ? 1 : -1);
  });
  document.querySelector('[data-tour="text"]')?.addEventListener("click", () => {
    close();
    startTour();
  });
  listeners.add(() => { if (tour) showStep(); });

  apply();
})();
