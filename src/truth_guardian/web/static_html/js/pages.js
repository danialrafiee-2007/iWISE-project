// The site's pages within one document, as in the reference: choosing a page in the rail fades the page shown out
// softly and the next one in, with no page load. The address follows (/, /team), so Back, Forward and a reload come
// to the same page. The AI engine's menu leads to its sections of the home page, scrolled to smoothly. The Team page's
// cards open each person's introduction, as on the previous site.

(() => {
  const main = document.getElementById("main");
  if (!main) return;
  const pages = new Map([...main.querySelectorAll(".page")].map((el) => [el.dataset.page, el]));
  // The addresses this front end has a page for; the others (pages not built yet) show the home page.
  const ROUTES = { "/": "home", "/models": "models", "/architecture": "architecture", "/team": "team", "/about": "about", "/contact": "contact" };
  // A reload, wherever it is done, opens the site again from the home page (D-205): the address goes back to "/" before
  // the page is chosen, so the opening plays and the home page comes after it, as on a first visit.
  const reloaded = performance.getEntriesByType("navigation")[0]?.type === "reload";
  if (reloaded) { history.scrollRestoration = "manual"; if (location.pathname !== "/" || location.hash) history.replaceState(null, "", "/"); }
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tr = (key) => (window.TG ? window.TG.t(key) : key);
  // The change's timings, read from style.css (:root), so the one standard is set in one place.
  const css = getComputedStyle(document.documentElement);
  const ms = (name, fallback) => parseFloat(css.getPropertyValue(name)) || fallback;
  const OUT = ms("--fade-out", 520);
  const LAYER = ms("--layer-in", 700);
  const STAGGER = ms("--stagger", 110);
  const CONTENT = ms("--content-delay", 240);
  let current = null;
  let busy = Promise.resolve();

  // A page's layers, in the order they come in: each box on it, and each card of a row of cards.
  function layersOf(page) {
    const found = [];
    for (const child of page.children) {
      if (child.tagName === "DIALOG") continue;
      if (child.matches("ul, ol")) child.querySelectorAll(":scope > li > *").forEach((el) => found.push(el));
      else found.push(child);
    }
    return found;
  }

  // Plays the entrance on `page`: its layers one after another, after `start` ms.
  let entranceTimer = 0;
  function enter(page, start = 0) {
    if (reduced) return;
    const layers = layersOf(page);
    page.querySelectorAll(".layer").forEach((el) => el.classList.remove("layer"));
    layers.forEach((el, i) => {
      el.classList.add("layer");
      el.style.setProperty("--i", String(i));
    });
    page.style.setProperty("--start", `${start}ms`);
    page.classList.remove("entering-page");
    void page.offsetWidth;
    page.classList.add("entering-page");
    clearTimeout(entranceTimer);
    // Once everything is in, the classes go, so nothing is left holding an animation.
    entranceTimer = setTimeout(() => page.classList.remove("entering-page"), start + layers.length * STAGGER + CONTENT + LAYER + 900);
  }

  // The site's first entrance plays behind the opening's circle (intro.js sends tg:entering as it starts).
  document.addEventListener("tg:entering", () => { if (current) enter(current, 700); });

  const pageFor = (path) => ROUTES[path.replace(/\/+$/, "") || "/"] || "home";

  // Only the page's own link is marked; the engine's two section links share the home page's address and are not.
  function markRail(path) {
    document.querySelectorAll(".rail a.rail-btn[data-page]").forEach((link) => {
      const here = new URL(link.href, location.href).pathname === path;
      if (here) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function scrollToSection(id) {
    const target = document.getElementById(id);
    if (!target) return;
    target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    target.classList.remove("flash");
    void target.offsetWidth;
    target.classList.add("flash");
  }

  // Shows the page for `path`: the one shown fades out, then the next fades in from a little below.
  function show(path, { section = null, instant = false } = {}) {
    busy = busy.then(async () => {
      const name = pageFor(path);
      const next = pages.get(name);
      markRail(path);
      if (next === current) {
        if (section) scrollToSection(section);
        return;
      }
      if (current && !instant && !reduced) {
        current.classList.add("leaving");
        await new Promise((done) => setTimeout(done, OUT));
      }
      if (current) {
        current.hidden = true;
        current.classList.remove("leaving");
      }
      // While nothing is shown the page is scrolled back to its top, so the next one arrives in place, not with a jump.
      window.scrollTo({ top: 0, behavior: "auto" });
      next.hidden = false;
      if (!instant) enter(next, 60);
      current = next;
      window.TGLog?.log("page", "open", path);
      const TITLES = { models: "html.models", architecture: "html.arch", team: "team.title", about: "about.title", contact: "contact.title" };
      document.title = name === "home" ? "Truth Guardian (HTML)" : `${tr(TITLES[name] || `${name}.title`)} · Truth Guardian`;
      if (section) setTimeout(() => scrollToSection(section), reduced ? 0 : 300);
    });
    return busy;
  }

  // The rail's page links: no page load, the address changes and the page fades over.
  document.querySelectorAll(".rail a.rail-btn[data-page]").forEach((link) => {
    link.addEventListener("click", (e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      link.blur(); // so the clicked button does not stay lit once the mouse moves on
      const path = new URL(link.href, location.href).pathname;
      if (path === location.pathname && current === pages.get(pageFor(path))) return; // already there: nothing moves
      if (path !== location.pathname) history.pushState({}, "", path);
      show(path);
    });
  });

  // The AI engine's parts: to their section of the home page, from whichever page is shown.
  document.querySelectorAll("[data-section]").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      link.blur();
      if (window.TG && window.TG.closeMenus) window.TG.closeMenus();
      if (location.pathname !== "/") history.pushState({}, "", "/");
      show("/", { section: link.dataset.section });
    });
  });

  window.addEventListener("popstate", () => show(location.pathname));

  // Other parts of the page go to a page the same way the rail does (the chat's "Truth Guardian check").
  if (window.TG) {
    window.TG.go = (path) => {
      if (path !== location.pathname) history.pushState({}, "", path);
      return show(path);
    };
  }

  // ---- The Model performance page's row of tabs: one opens at a time, softly, below the row ----
  const tabs = [...document.querySelectorAll('.tabs [role="tab"]')];
  const panelOf = (t) => document.getElementById(t.getAttribute("aria-controls"));
  const TAB_OUT = 200;
  const TAB_HEIGHT = 420;
  const tabRow = document.querySelector(".tabs");
  let tabTimer = 0;
  // A long panel (Reliability) changed for a short one made the page shorter at once, and the window, scrolled down,
  // fell to the top in one jump. Now (D-204): if the row of tabs has gone up out of view, the window first slides
  // back to it; the panel shown fades out while the page keeps its height; the next one fades in; and the page then
  // eases to its new height, so the window never falls.
  function openTab(tab, focus = false) {
    const next = panelOf(tab);
    const shown = tabs.map(panelOf).find((p) => p && !p.hidden && p !== next);
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
    });
    if (focus) tab.focus({ preventScroll: true });
    if (!next) return;
    window.TGLog?.log("tab", "open", tab.textContent.trim());
    clearTimeout(tabTimer);
    const page = next.closest(".page");
    if (reduced || !shown || !page) {
      tabs.map(panelOf).forEach((p) => { if (p) p.hidden = p !== next; });
      return;
    }
    page.getAnimations().forEach((a) => a.cancel());
    const from = page.offsetHeight;
    page.style.minHeight = `${from}px`;
    const rowTop = tabRow ? tabRow.getBoundingClientRect().top : 0;
    if (rowTop < 0) window.scrollTo({ top: Math.max(0, window.scrollY + rowTop - 16), behavior: "smooth" });
    shown.classList.remove("tab-in");
    shown.classList.add("tab-out");
    const shownHeight = shown.offsetHeight;
    tabTimer = setTimeout(() => {
      tabs.map(panelOf).forEach((p) => { if (p) { p.hidden = p !== next; p.classList.remove("tab-out", "tab-in"); } });
      void next.offsetWidth;
      next.classList.add("tab-in");
      // The new height, worked out from the two panels while the page keeps its old one: letting the page go short even
      // for a moment, to measure it, is what dropped the window to the top.
      const to = from - shownHeight + next.offsetHeight;
      if (to >= from) { page.style.minHeight = ""; return; }
      page.style.minHeight = `${to}px`;
      const shrink = page.animate([{ minHeight: `${from}px` }, { minHeight: `${to}px` }], { duration: TAB_HEIGHT, easing: "cubic-bezier(0.22, 0.61, 0.36, 1)" });
      shrink.onfinish = () => { page.style.minHeight = ""; };
    }, TAB_OUT);
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => openTab(tab));
    tab.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const dir = document.documentElement.dir === "rtl" ? -step : step;
      openTab(tabs[(i + dir + tabs.length) % tabs.length], true);
    });
  });
  if (window.TG) window.TG.openTab = (id) => { const t = document.getElementById(id); if (t) openTab(t); };

  // ---- The Team page's introductions ----

  const PEOPLE = {
    hamed: { name: "Hamed Khalilavi", photo: "/people/hamed-khalilavi.jpg", rank: "team.supervisor", role: "team.role.hamed", bio: "team.bio.hamed" },
    danial: { name: "Danial Rafiee", photo: "/people/danial-rafiee.jpg", rank: "team.member", role: "team.role.models", bio: "team.bio.models" },
    mojdeh: { name: "Mojdeh Ghazvinian", rank: "team.member", role: "team.role.models", bio: "team.bio.models" },
    sepehr: { name: "Sepehr Kakoli", rank: "team.member", role: "team.role.sepehr", bio: "team.bio.sepehr" },
    majid: { name: "Majid Rafiee", rank: "team.member", role: "team.role.majid", bio: "team.bio.majid" },
  };
  const dialog = document.getElementById("person-dialog");
  let shownPerson = null;

  function fillPerson() {
    if (!dialog || !shownPerson) return;
    const p = PEOPLE[shownPerson];
    const photo = dialog.querySelector(".person-dialog-photo");
    photo.innerHTML = p.photo
      ? `<img src="${p.photo}" alt="" width="900" height="1125" decoding="async">`
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="8.5" r="4"/><path d="M4.5 20c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5"/></svg>';
    photo.classList.toggle("empty", !p.photo);
    dialog.querySelector("#person-dialog-rank").textContent = tr(p.rank);
    dialog.querySelector("#person-dialog-name").textContent = p.name;
    dialog.querySelector("#person-dialog-role").textContent = tr(p.role);
    dialog.querySelector("#person-dialog-bio").textContent = tr(p.bio);
  }

  document.querySelectorAll("[data-person]").forEach((card) => {
    card.addEventListener("click", () => {
      if (!dialog) return;
      shownPerson = card.dataset.person;
      fillPerson();
      dialog.showModal();
    });
  });
  // Closing fades it out softly first, as everything else on the site (Esc too).
  function closeDialog() {
    if (!dialog.open || dialog.classList.contains("closing")) return;
    if (reduced) return dialog.close();
    dialog.classList.add("closing");
    setTimeout(() => {
      dialog.close();
      dialog.classList.remove("closing");
    }, 320);
  }
  if (dialog) {
    dialog.querySelector(".dialog-x").addEventListener("click", closeDialog);
    dialog.addEventListener("click", (e) => { if (e.target === dialog) closeDialog(); });
    dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeDialog(); });
    if (window.TG) window.TG.onLang(fillPerson);
  }

  // The first page: the one the address names, shown at once (the opening covers it).
  pages.forEach((el) => { el.hidden = true; });
  show(location.pathname, { instant: true, section: location.hash ? location.hash.slice(1) : null });
})();
