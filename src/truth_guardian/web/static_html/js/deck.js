// The site's two card decks in 3D (D-219), written for this project with CSS transforms; each card's place follows
// one number, the deck's position, which eases toward the card asked for, so that every way of moving it (a drag, the
// wheel, the keys, a click) and the motion between cards are the same.
//
// 1. TGDeck.examples(element, { cards: [{ key, label, title, glow, html }], label, browse, cta, prev, next, paused(),
//    onOpen(i) }): Check an answer's ready-made examples as a ring of cards turning around the one in front, a glow in
//    its colour behind it, its title and the button that checks it below. It turns by itself every few seconds, except
//    while the pointer or the focus is on it, while paused() says a check runs or a report is shown, and for people who
//    asked for less motion. A drag, a sideways scroll, the arrow keys, a click on a side card or the two arrows turn it;
//    a click on the front card, Enter or the button checks it. Returns { set(i), destroy() }.
// 2. TGDeck.tricks(element, { cards: [{ key, label, fill, html }], active, label, tabsLabel, count(i), total,
//    onActive(i) }): Fool the Guardian's tricks as a pile, the chosen card in front and tilted back, the next ones
//    stacked behind it, the ones passed falling forward out of sight; a counter and a dot per trick beside it; under the
//    cards a foot (.tk-foot) for the page's own row. The wheel over the pile (until its first or last card, then the page
//    scrolls on), a drag, the arrow keys, the dots or a click on a card behind choose. Returns { set(i), destroy() }.

(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const calm = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const rtl = () => document.documentElement.dir === "rtl";
  const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

  // The deck's position: it eases toward its target, frame by frame, and draws the cards at each step.
  function glide(draw) {
    let pos = 0;
    let target = 0;
    let frame = 0;
    let last = 0;
    function tick(now) {
      const dt = Math.min(0.05, last ? (now - last) / 1000 : 1 / 60);
      last = now;
      pos += (target - pos) * (1 - Math.exp(-dt * 8.5));
      if (Math.abs(target - pos) < 0.0015) pos = target;
      draw(pos);
      frame = pos === target ? 0 : requestAnimationFrame(tick);
      if (!frame) last = 0;
    }
    return {
      get pos() { return pos; },
      get target() { return target; },
      to(t) {
        target = t;
        if (calm()) { pos = t; draw(pos); return; }
        if (!frame) frame = requestAnimationFrame(tick);
      },
      hold(p) { // follows a drag at once
        cancelAnimationFrame(frame);
        frame = 0;
        last = 0;
        pos = target = p;
        draw(pos);
      },
      stop() { cancelAnimationFrame(frame); frame = 0; },
    };
  }

  // A drag on the stage: on the axis it starts along, after a few pixels, so that a plain click still clicks. move(d)
  // gets the distance in pixels along that axis, end(v) the speed in pixels a second.
  function dragging(stage, { axes, start, move, end }) {
    let d = null;
    const off = () => { d = null; };
    stage.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest(".tk-foot, .ex-foot")) return;
      d = { x: e.clientX, y: e.clientY, id: e.pointerId, axis: null, t: performance.now(), at: 0, v: 0 };
    });
    stage.addEventListener("pointermove", (e) => {
      if (!d || e.pointerId !== d.id) return;
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (!d.axis) {
        if (Math.hypot(dx, dy) < 7) return;
        d.axis = Math.abs(dx) > Math.abs(dy) ? "x" : "y";
        if (!axes.includes(d.axis)) { off(); return; }
        stage.setPointerCapture(e.pointerId);
        stage.classList.add("dragging");
        start();
      }
      const along = d.axis === "x" ? dx : dy;
      const now = performance.now();
      if (now > d.t) d.v = 0.7 * d.v + 0.3 * (((along - d.at) / (now - d.t)) * 1000);
      d.t = now;
      d.at = along;
      move(along, d.axis);
    });
    const finish = (e) => {
      if (!d || e.pointerId !== d.id) return;
      const done = d.axis ? d : null;
      off();
      if (!done) return;
      stage.classList.remove("dragging");
      stage.dataset.dragged = "1"; // the click that follows the drag is not a click on a card
      setTimeout(() => delete stage.dataset.dragged, 0);
      end(done.v, done.axis);
    };
    stage.addEventListener("pointerup", finish);
    stage.addEventListener("pointercancel", finish);
  }

  // ---- 1. The examples ring ----
  function examples(root, opts) {
    root._tgDeck?.destroy();
    const cards = opts.cards;
    const n = cards.length;
    const arrow = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14.5 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    root.innerHTML = `
      <section class="ex-deck" tabindex="0" aria-roledescription="carousel" aria-label="${esc(opts.label)}" title="${esc(opts.browse)}">
        <div class="ex-glow" aria-hidden="true"></div>
        <div class="ex-stage">
          <div class="ex-ring">
            ${cards.map((c, i) => `
              <button type="button" class="ex-card" tabindex="-1" data-i="${i}" style="--glow:${esc(c.glow)}" aria-label="${esc(c.label)}">
                <span class="ex-veil" aria-hidden="true"></span><span class="ex-body">${c.html}</span>
              </button>`).join("")}
          </div>
        </div>
        <div class="ex-foot">
          <p class="ex-caption" dir="auto"></p>
          <div class="ex-nav">
            <button type="button" class="ex-arrow" data-step="-1" aria-label="${esc(opts.prev)}">${arrow}</button>
            <button type="button" class="btn-primary ex-go">${esc(opts.cta)}</button>
            <button type="button" class="ex-arrow ex-arrow-next" data-step="1" aria-label="${esc(opts.next)}">${arrow}</button>
          </div>
          <p class="ex-live" aria-live="polite"></p>
        </div>
      </section>`;
    const deck = root.querySelector(".ex-deck");
    const stage = root.querySelector(".ex-stage");
    const els = [...root.querySelectorAll(".ex-card")];
    const caption = root.querySelector(".ex-caption");
    const live = root.querySelector(".ex-live");
    let spacing = 100;
    let front = -1;
    let hover = false;
    let told = false; // the screen reader hears a change the person made, not the ones the deck makes by itself

    const around = (d) => { const o = ((d % n) + n) % n; return o > n / 2 ? o - n : o; }; // the nearer way round
    function draw(pos) {
      const side = rtl() ? -1 : 1;
      els.forEach((el, i) => {
        const d = around(i - pos);
        const a = Math.abs(d);
        const x = side * d * spacing * (1 - 0.06 * Math.min(a, 3));
        const turn = -side * clamp(d * 33, -112, 112);
        el.style.transform = `translate3d(${x.toFixed(1)}px, ${(a * 10).toFixed(1)}px, ${(-a * 95).toFixed(1)}px) rotateY(${turn.toFixed(2)}deg) scale(${(1 - 0.12 * Math.min(a, 3.5)).toFixed(3)})`;
        el.style.opacity = a > 3.6 ? "0" : clamp(1.1 - a * 0.27, 0, 1).toFixed(3);
        el.style.filter = `brightness(${(1 - 0.16 * Math.min(a, 3.5)).toFixed(3)}) saturate(${(1 + Math.max(0, 0.3 - a)).toFixed(2)})`;
        el.style.zIndex = String(100 - Math.round(a * 10));
        el.style.visibility = a > 3.6 ? "hidden" : "visible";
        el.style.pointerEvents = a < 2.6 ? "auto" : "none";
      });
      const now = ((Math.round(pos) % n) + n) % n;
      if (now !== front) show(now);
    }
    function show(i) {
      front = i;
      els.forEach((el, k) => el.setAttribute("aria-current", String(k === i)));
      deck.style.setProperty("--halo", cards[i].glow);
      caption.textContent = cards[i].title || cards[i].label;
      if (told) live.textContent = cards[i].label;
    }
    const motion = glide(draw);
    const go = (i, byPerson = true) => { told = byPerson; motion.to(motion.target + around(i - motion.target)); };
    const step = (k, byPerson = true) => { told = byPerson; motion.to(Math.round(motion.target) + k); };
    const open = () => opts.onOpen?.(front);

    // The cards as large as the stage lets them be, and spread across its width.
    function size() {
      const w = stage.clientWidth || 480;
      const h = stage.clientHeight || 340;
      const card = clamp(Math.min(w * 0.56, (h - 28) / 1.28), 168, 300);
      deck.style.setProperty("--cw", `${Math.round(card)}px`);
      spacing = clamp(w / 4.7, 58, 150);
      draw(motion.pos);
    }
    const resize = new ResizeObserver(size);
    resize.observe(stage);

    els.forEach((el, i) => el.addEventListener("click", () => {
      if (stage.dataset.dragged) return;
      if (i === front && Math.abs(around(i - motion.pos)) < 0.25) open();
      else go(i);
    }));
    root.querySelector(".ex-go").addEventListener("click", open);
    root.querySelectorAll(".ex-arrow").forEach((b) => b.addEventListener("click", () => step(+b.dataset.step)));
    deck.addEventListener("keydown", (e) => {
      if (e.target !== deck) return;
      const ahead = rtl() ? "ArrowLeft" : "ArrowRight";
      const back = rtl() ? "ArrowRight" : "ArrowLeft";
      if (e.key === ahead) step(1);
      else if (e.key === back) step(-1);
      else if (e.key === "Enter" || e.key === " ") open();
      else return;
      e.preventDefault();
    });
    let swept = 0;
    stage.addEventListener("wheel", (e) => {
      const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.shiftKey ? e.deltaY : 0;
      if (!d) return; // an up-and-down wheel scrolls the page
      e.preventDefault();
      swept += d;
      if (Math.abs(swept) >= 50) {
        step((Math.sign(swept) * (rtl() ? -1 : 1)));
        swept = 0;
      }
    }, { passive: false });
    let from = 0;
    dragging(stage, {
      axes: ["x"],
      start: () => { from = motion.pos; told = true; },
      move: (dx) => motion.hold(from - ((rtl() ? -1 : 1) * dx) / spacing),
      end: (v) => motion.to(Math.round(motion.pos + clamp((-(rtl() ? -1 : 1) * v * 0.12) / spacing, -2, 2))), // a flick adds two cards at most
    });
    deck.addEventListener("pointerenter", () => { hover = true; });
    deck.addEventListener("pointerleave", () => { hover = false; });

    // Turning by itself, while nobody is using it and it is on screen.
    const still = () => hover || deck.contains(document.activeElement) || stage.classList.contains("dragging") || opts.paused?.()
      || document.hidden || !root.isConnected || root.offsetParent === null || calm();
    const timer = setInterval(() => { if (!still()) step(1, false); }, 3400);

    size();
    show(0);
    const api = {
      set: (i) => go(i, false),
      destroy() { clearInterval(timer); resize.disconnect(); motion.stop(); },
    };
    root._tgDeck = api;
    return api;
  }

  // ---- 2. The tricks pile ----
  function tricks(root, opts) {
    root._tgDeck?.destroy();
    const cards = opts.cards;
    const n = cards.length;
    const count = opts.count || ((i) => String(i + 1).padStart(2, "0"));
    root.innerHTML = `
      <section class="tk-deck">
        <div class="tk-stage" tabindex="0" aria-roledescription="carousel" aria-label="${esc(opts.label)}">
          <div class="tk-pile">
            ${cards.map((c, i) => `
              <article class="tk-card" data-i="${i}" aria-label="${esc(c.label)}">
                <div class="tk-face" style="background:${esc(c.fill)}"><span class="tk-veil" aria-hidden="true"></span><div class="tk-body">${c.html}</div></div>
              </article>`).join("")}
          </div>
          <div class="tk-foot"></div>
        </div>
        <div class="tk-side">
          <p class="tk-count"><span data-count dir="ltr"></span><small dir="ltr">/${esc(opts.total ?? n)}</small></p>
          <div class="tk-dots" role="tablist" aria-orientation="vertical" aria-label="${esc(opts.tabsLabel || opts.label)}">
            ${cards.map((c, i) => `<button type="button" class="tk-dot" role="tab" data-i="${i}" aria-label="${esc(c.label)}"><span></span></button>`).join("")}
          </div>
          <p class="tk-live" aria-live="polite"></p>
        </div>
      </section>`;
    const stage = root.querySelector(".tk-stage");
    const pile = root.querySelector(".tk-pile");
    const els = [...root.querySelectorAll(".tk-card")];
    const dots = [...root.querySelectorAll(".tk-dot")];
    const counter = root.querySelector("[data-count]");
    const live = root.querySelector(".tk-live");
    let active = clamp(opts.active || 0, 0, n - 1);
    let lift = 280;

    function draw(pos) {
      els.forEach((el, i) => {
        const d = i - pos;
        let y; let z; let tilt; let s; let o;
        if (d >= 0) { // waiting behind, each one a little higher and further back
          const f = 1 - Math.pow(0.5, d);
          y = -lift * f;
          z = -340 * f;
          tilt = -16 - 50 * f;
          s = 1 - 0.15 * f;
          o = d > 6.5 ? 0 : 1;
        } else { // passed: falling forward and down, turning over, fading
          const b = -d;
          y = b * 310;
          z = 115 * Math.min(1, b);
          tilt = -16 + b * 118;
          s = 1 + 0.05 * Math.min(1, b);
          o = clamp(1 - b * 0.85, 0, 1);
        }
        el.style.transform = `translate3d(0, ${y.toFixed(1)}px, ${z.toFixed(1)}px) rotateX(${tilt.toFixed(2)}deg) scale(${s.toFixed(3)})`;
        el.style.opacity = o.toFixed(3);
        el.style.zIndex = String(d >= 0 ? 1000 - Math.round(d * 10) : 1001 + Math.round(-d * 10));
        el.style.pointerEvents = o > 0.4 && d > -0.5 && d < 4 ? "auto" : "none";
        el.style.visibility = o === 0 ? "hidden" : "visible";
      });
    }
    const motion = glide(draw);

    function set(i, { tell = true, person = false, instant = false } = {}) {
      const next = clamp(i, 0, n - 1);
      const changed = next !== active;
      active = next;
      dots.forEach((b, k) => {
        b.setAttribute("aria-selected", String(k === active));
        b.tabIndex = k === active ? 0 : -1;
      });
      els.forEach((el, k) => el.setAttribute("aria-current", String(k === active)));
      counter.textContent = count(active);
      if (changed && !calm()) { counter.classList.remove("tick"); void counter.offsetWidth; counter.classList.add("tick"); }
      if (person) live.textContent = cards[active].label;
      if (instant) motion.hold(active);
      else motion.to(active);
      if (tell && changed) opts.onActive?.(active);
    }

    // The cards as large as the pile lets them be: tall enough to leave the stack behind them in sight.
    function size() {
      const h = pile.clientHeight || 460;
      const w = pile.clientWidth || 420;
      const width = Math.min(clamp(h * 0.66, 330, 480) * 0.86, w * 0.84);
      root.querySelector(".tk-deck").style.setProperty("--tk-w", `${Math.round(width)}px`);
      root.querySelector(".tk-deck").style.setProperty("--tk-h", `${Math.round(width / 0.86)}px`);
      lift = clamp(h * 0.66, 180, 470);
      draw(motion.pos);
    }
    const resize = new ResizeObserver(size);
    resize.observe(pile);

    els.forEach((el, i) => el.addEventListener("click", () => { if (!stage.dataset.dragged && i !== active) set(i, { person: true }); }));
    dots.forEach((b, i) => {
      b.addEventListener("click", () => set(i, { person: true }));
      b.addEventListener("keydown", (e) => {
        const k = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1, Home: -n, End: n }[e.key];
        if (!k) return;
        e.preventDefault();
        set(active + k, { person: true });
        dots[active].focus();
      });
    });
    stage.addEventListener("keydown", (e) => {
      if (e.target !== stage) return;
      const ahead = rtl() ? "ArrowLeft" : "ArrowRight";
      const back = rtl() ? "ArrowRight" : "ArrowLeft";
      const k = { ArrowDown: 1, [ahead]: 1, ArrowUp: -1, [back]: -1, Home: -n, End: n }[e.key];
      if (!k) return;
      e.preventDefault();
      set(active + k, { person: true });
    });
    let swept = 0;
    let rest = 0;
    stage.addEventListener("wheel", (e) => {
      if (e.target.closest(".tk-foot")) return;
      const d = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX * (rtl() ? -1 : 1);
      if ((d < 0 && active === 0) || (d > 0 && active === n - 1)) return; // at an end the page scrolls on
      e.preventDefault();
      const now = performance.now();
      if (now < rest) return; // one card for each turn of a mouse wheel
      swept += d;
      if (Math.abs(swept) >= 40) {
        set(active + Math.sign(swept), { person: true });
        swept = 0;
        rest = now + 260;
      }
    }, { passive: false });
    let from = 0;
    dragging(stage, {
      axes: ["x", "y"],
      start: () => { from = motion.pos; },
      move: (d, axis) => motion.hold(clamp(from + (axis === "y" ? d : -d * (rtl() ? -1 : 1)) / 150, -0.35, n - 0.65)),
      end: (v, axis) => set(Math.round(motion.pos + clamp(((axis === "y" ? v : -v * (rtl() ? -1 : 1)) * 0.12) / 150, -2, 2)), { person: true }),
    });

    size();
    set(active, { tell: false, instant: true });
    const api = {
      set: (i) => set(i, { tell: false }),
      destroy() { resize.disconnect(); motion.stop(); },
    };
    root._tgDeck = api;
    return api;
  }

  window.TGDeck = { examples, tricks };
})();
