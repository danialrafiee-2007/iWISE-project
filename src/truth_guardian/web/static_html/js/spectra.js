// The examples deck of the previous site's Check an answer page (layers/SpectraDeck.tsx, from the "Slider Spectra"
// section in docs/CREDITS.md), in plain JS: a ring coverflow (the centre card faces you, the others fan out, turned,
// lowered, smaller and dimmer), a halo behind it in the centre card's colour, the centre card's title under the deck and
// a button to check it. It turns by dragging (with momentum), the arrow keys, a click on a side card, the mouse wheel
// over it (one card per notch, the page staying still) and by itself every few seconds, except while the pointer is on
// it, someone is typing, the tab is hidden or `paused()` says so. It draws only while a card moves.
// TGSpectra.mount(element, { cards: [{ key, label, c1, c2, glow, html }], onOpen(i), caption(i), cta, label, browse,
// itemLabel(i), paused() }).

(() => {
  const C = { gap: 164, rotate: 38, depth: 150, drop: 24, shrink: 0.14, fade: 0.26, dim: 0.2, visible: 3, persp: 1680, autoplayMs: 3200, ease: 0.14, sensitivity: 0.0072 };
  const STEP = 100; // the wheel: one notch (about 100 px) turns one card
  const PAUSE = 520; // and the next turn waits this long
  const SAME_SCROLL = 250; // a wheel event this soon after one that moved the page belongs to that scroll
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const stopPrevious = new WeakMap(); // element → stop() of the deck mounted there before

  function mount(root, opts) {
    stopPrevious.get(root)?.();
    const { cards } = opts;
    const N = cards.length;
    if (!N) {
      root.innerHTML = "";
      return null;
    }
    root.innerHTML = `
      <section class="spectra" aria-roledescription="carousel" aria-label="${esc(opts.label || "")}">
        <div class="spectra-halo" aria-hidden="true"></div>
        <div class="spectra-stage" role="group" aria-label="${esc(opts.browse || "")}" style="perspective:${C.persp}px">
          <div class="spectra-origin">
            ${cards.map((c, i) => `<button type="button" class="spectra-card" data-i="${i}" aria-label="${esc(opts.itemLabel ? opts.itemLabel(i) : c.label)}" style="background:linear-gradient(160deg, ${c.c1}, ${c.c2})"><span class="spectra-shade"></span><span class="spectra-content">${c.html}</span></button>`).join("")}
          </div>
        </div>
        <div class="spectra-foot" aria-live="polite">
          <h3 class="spectra-caption" dir="auto"></h3>
          <button type="button" class="btn-primary spectra-cta">${esc(opts.cta || "")}</button>
        </div>
      </section>`;
    const deck = root.querySelector(".spectra");
    const stage = root.querySelector(".spectra-stage");
    const halo = root.querySelector(".spectra-halo");
    const els = [...root.querySelectorAll(".spectra-card")];
    const caption = root.querySelector(".spectra-caption");
    const s = { pos: 0, target: 0, dragging: false, moved: false, lastX: 0, startX: 0, vel: 0, hover: false, scale: 1 };
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let active = -1;
    let raf = 0;

    const wrap = (o) => {
      o = ((o % N) + N) % N;
      return o > N / 2 ? o - N : o;
    };
    function paint() {
      const w = stage.clientWidth || 1180;
      s.scale = Math.max(0.56, Math.min(1, w / 1180));
      for (let i = 0; i < N; i++) {
        const el = els[i];
        const o = wrap(i - s.pos);
        const ao = Math.abs(o);
        if (ao > C.visible + 0.5) {
          el.style.opacity = "0";
          el.style.pointerEvents = "none";
          continue;
        }
        const sc = Math.max(0.4, 1 - ao * C.shrink);
        el.style.transform = `translateX(${o * C.gap * s.scale}px) translateY(${ao * C.drop * s.scale}px) translateZ(${-ao * C.depth * s.scale}px) rotateY(${-o * C.rotate}deg) scale(${sc})`;
        el.style.opacity = String(Math.max(0, 1 - ao * C.fade));
        el.style.filter = `brightness(${Math.max(0.3, 1 - ao * C.dim)}) saturate(${1 + (1 - Math.min(1, ao)) * 0.25})`;
        el.style.zIndex = String(Math.round(100 - ao * 10));
        el.style.pointerEvents = "auto";
      }
      const a = ((Math.round(s.pos) % N) + N) % N;
      if (a !== active) {
        active = a;
        halo.style.setProperty("--halo", cards[a].glow);
        caption.textContent = cards[a].label;
        els.forEach((el, i) => el.setAttribute("aria-current", String(i === a)));
      }
    }
    function frame() {
      raf = 0;
      if (!s.dragging) {
        s.pos = reduce ? s.target : s.pos + (s.target - s.pos) * C.ease;
        if (Math.abs(s.target - s.pos) < 0.001) s.pos = s.target;
      }
      paint();
      if (s.dragging || s.pos !== s.target) raf = requestAnimationFrame(frame);
    }
    const wake = () => { if (!raf) raf = requestAnimationFrame(frame); };
    function go(i) {
      const cur = Math.round(s.target);
      let o = (((i - cur) % N) + N) % N;
      if (o > N / 2) o -= N;
      s.target = cur + o;
      wake();
    }

    // Drag with momentum; a drag is never taken for a click.
    stage.addEventListener("pointerdown", (e) => {
      s.dragging = true;
      s.moved = false;
      s.lastX = s.startX = e.clientX;
      s.vel = 0;
      stage.setPointerCapture(e.pointerId);
      wake();
    });
    stage.addEventListener("pointermove", (e) => {
      if (!s.dragging) return;
      const dx = e.clientX - s.lastX;
      s.lastX = e.clientX;
      if (Math.abs(e.clientX - s.startX) > 5) s.moved = true;
      const d = -dx * C.sensitivity;
      s.pos += d;
      s.vel = d;
    });
    const release = () => {
      if (!s.dragging) return;
      s.dragging = false;
      s.target = Math.round(s.pos + s.vel * 8);
      s.vel = 0;
      wake();
    };
    stage.addEventListener("pointerup", release);
    stage.addEventListener("pointercancel", release);
    els.forEach((el, i) => el.addEventListener("click", () => {
      if (s.moved) return;
      if (i === active) opts.onOpen?.(i);
      else go(i);
    }));
    root.querySelector(".spectra-cta").addEventListener("click", () => opts.onOpen?.(active));
    deck.addEventListener("mouseenter", () => { s.hover = true; });
    deck.addEventListener("mouseleave", () => { s.hover = false; });
    deck.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") s.target += 1;
      else if (e.key === "ArrowLeft") s.target -= 1;
      else return;
      e.preventDefault();
      wake();
    });

    // The wheel over the deck turns it; a scroll already moving the page carries on past it.
    let sum = 0;
    let lastTurn = 0;
    let lastPage = -Infinity;
    const onPage = (e) => { if (!deck.contains(e.target)) lastPage = performance.now(); };
    window.addEventListener("wheel", onPage, { passive: true });
    deck.addEventListener("wheel", (e) => {
      const now = performance.now();
      if (e.ctrlKey) return;
      if (now - lastPage < SAME_SCROLL) { lastPage = now; return; }
      e.preventDefault();
      const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? window.innerHeight : 1;
      sum += (Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX) * unit;
      if (Math.abs(sum) < STEP || now - lastTurn < PAUSE) return;
      s.target += Math.sign(sum);
      sum = 0;
      lastTurn = now;
      wake();
    }, { passive: false });

    // Turning by itself, unless someone is looking at it, typing, or the page asks it to wait.
    const timer = setInterval(() => {
      const typing = document.activeElement?.matches?.("input, textarea, select");
      if (reduce || s.hover || s.dragging || document.hidden || typing || opts.paused?.()) return;
      s.target += 1;
      wake();
    }, C.autoplayMs);
    const resized = new ResizeObserver(wake);
    resized.observe(stage);

    paint();
    const stop = () => {
      cancelAnimationFrame(raf);
      clearInterval(timer);
      resized.disconnect();
      window.removeEventListener("wheel", onPage);
    };
    stopPrevious.set(root, stop);
    return { go, active: () => active, stop };
  }

  window.TGSpectra = { mount };
})();
