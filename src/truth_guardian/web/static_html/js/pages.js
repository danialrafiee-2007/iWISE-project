// The site's pages within one document, as in the reference: choosing a page in the rail fades the page shown out
// softly and the next one in, with no page load. The address follows (/, /team), so Back, Forward and a reload come
// to the same page. The AI engine's menu leads to its sections of the home page, scrolled to smoothly. The Team page's
// cards open each person's introduction, as on the previous site.

(() => {
  const main = document.getElementById("main");
  if (!main) return;
  const pages = new Map([...main.querySelectorAll(".page")].map((el) => [el.dataset.page, el]));
  // The addresses this front end has a page for; the others (pages not built yet) show the home page.
  const ROUTES = { "/": "home", "/team": "team", "/about": "about", "/contact": "contact" };
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const OUT = 320; // ms the page shown takes to fade out, in style.css (.page.leaving)
  const tr = (key) => (window.TG ? window.TG.t(key) : key);
  let current = null;
  let busy = Promise.resolve();

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
      if (!instant && !reduced) {
        next.classList.remove("entering-page");
        void next.offsetWidth;
        next.classList.add("entering-page");
      }
      current = next;
      document.title = name === "home" ? "Truth Guardian (HTML)" : `${tr(`${name}.title`)} · Truth Guardian`;
      if (section) setTimeout(() => scrollToSection(section), reduced ? 0 : 200);
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
  if (dialog) {
    dialog.querySelector(".dialog-x").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
    if (window.TG) window.TG.onLang(fillPerson);
  }

  // The first page: the one the address names, shown at once (the opening covers it).
  pages.forEach((el) => { el.hidden = true; });
  show(location.pathname, { instant: true, section: location.hash ? location.hash.slice(1) : null });
})();
