// The cards cascade of the previous site's Fool the Guardian page (layers/CardsCascade.tsx, from the "Cards Cascade"
// section in docs/CREDITS.md), in plain JS: the chosen card stands on the crest, the cards after it lie back in a
// stack behind, the cards before it fold forward over the lip and fade. The wheel over the deck turns the cards round
// and round (the page stays still, unless a scroll already moving the page passes over it), the arrow keys and the
// dots beside it choose one, a click on a card brings it to the crest. It draws only while the cards move.
// TGCascade.mount(element, { cards: [{ key, label, fill, html }], active, onActive, height, label, tabsLabel, announce })
// returns { set(i) }.

(() => {
  const G = { crestTilt: -18, crestY: 0.2, crestZ: 0.02, backDecay: 0.8, backTilt: 50, backRise: 1.02, backDepth: 1.05, backShrink: 0.16, frontDrop: 0.86, frontFold: 120, frontFwd: 0.3, fadeStart: 1.3, fadeEnd: 2.2, backFade: 9 };
  const EASE = 0.09; // how far the cards close on the chosen one each frame: a slow, even glide
  const STEP = 100; // scrolling that makes one card: one mouse notch (about 100 px) turns one card
  const PAUSE = 520; // before the next card, so each card can be seen and a trackpad's long glide turns only a few
  const SAME_SCROLL = 250; // a wheel event this soon after one that moved the page belongs to that scroll
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function place(el, p, H) {
    let tilt, ty, tz, scale, opacity, sheen, z;
    if (p >= 0) {
      const a = 1 - Math.exp(-p * G.backDecay);
      tilt = G.crestTilt - G.backTilt * a;
      ty = H * (G.crestY - G.backRise * a);
      tz = H * (G.crestZ - G.backDepth * a);
      scale = 1 - G.backShrink * a;
      sheen = 0.5 + 0.4 * a;
      opacity = clamp(1 - (p - G.backFade) * 0.5, 0, 1);
      z = 1000 - Math.round(p * 10);
    } else {
      const q = -p;
      tilt = G.crestTilt + G.frontFold * q;
      ty = H * (G.crestY + G.frontDrop * q);
      const fwd = Math.sin(clamp(q, 0, 1) * Math.PI * 0.5);
      tz = H * (G.crestZ + G.frontFwd * fwd);
      scale = 1 + 0.05 * fwd;
      sheen = 0.5 - 0.3 * clamp(q, 0, 1);
      opacity = 1 - clamp((q - G.fadeStart) / (G.fadeEnd - G.fadeStart), 0, 1);
      z = 2000 + Math.round(q * 10);
    }
    el.style.opacity = String(opacity);
    el.style.zIndex = String(z);
    el.style.visibility = opacity < 0.01 ? "hidden" : "visible";
    el.style.setProperty("--sheen", sheen.toFixed(3));
    el.style.transform = `translateY(${ty.toFixed(1)}px) translateZ(${tz.toFixed(1)}px) rotateX(${tilt.toFixed(2)}deg) scale(${scale.toFixed(3)})`;
  }

  function mount(root, opts) {
    const { cards, onActive, height = 440 } = opts;
    let active = opts.active ?? 0;
    let progress = active;
    let raf = 0;
    const cardH = Math.round(height * 0.6);
    const cardW = Math.round(cardH / 1.16);
    const pad = (n) => String(n).padStart(2, "0");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    root.innerHTML = `
      <div class="cascade" style="height:${height}px">
        <div class="cascade-stage" tabindex="0" aria-roledescription="carousel" aria-label="${esc(opts.label || "")}" style="perspective:${Math.max(1200, height * 2.8)}px">
          <div class="cascade-origin">
            ${cards.map((c, i) => `<article class="cascade-card" data-i="${i}" style="width:${cardW}px;height:${cardH}px;left:${-cardW / 2}px;top:${-cardH / 2}px">
              <div class="cascade-face" style="background:${c.fill}"><div class="cascade-shade"></div><div class="cascade-content">${c.html}</div></div></article>`).join("")}
          </div>
          <div class="sr-only" aria-live="polite" data-announce></div>
        </div>
        <div class="cascade-rail" role="tablist" aria-label="${esc(opts.tabsLabel || "")}">
          <span class="cascade-count" dir="ltr"><span data-count>${pad(active + 1)}</span><small>/${pad(cards.length)}</small></span>
          ${cards.map((c, i) => `<button type="button" class="cascade-dot" role="tab" data-dot="${i}" aria-label="${esc(c.label)}" title="${esc(c.label)}"><span></span></button>`).join("")}
        </div>
      </div>`;
    const stage = root.querySelector(".cascade-stage");
    const els = [...root.querySelectorAll(".cascade-card")];
    const dots = [...root.querySelectorAll("[data-dot]")];
    const count = root.querySelector("[data-count]");
    const announce = root.querySelector("[data-announce]");

    function frame() {
      progress += (active - progress) * (reduce ? 1 : EASE);
      if (Math.abs(active - progress) < 0.0005) progress = active;
      els.forEach((el, i) => place(el, i - progress, cardH));
      raf = progress !== active ? requestAnimationFrame(frame) : 0;
    }
    function show() {
      els.forEach((el, i) => el.setAttribute("aria-hidden", String(i !== active)));
      dots.forEach((d, i) => d.setAttribute("aria-selected", String(i === active)));
      count.textContent = pad(active + 1);
      count.classList.remove("tick");
      void count.offsetWidth; // restart the number's little rise
      count.classList.add("tick");
      if (opts.announce) announce.textContent = opts.announce(active);
      if (!raf) raf = requestAnimationFrame(frame);
    }
    function set(i, tell = true) {
      const next = ((i % cards.length) + cards.length) % cards.length;
      if (next === active) return;
      active = next;
      show();
      if (tell) onActive?.(active);
    }

    els.forEach((el, i) => el.addEventListener("click", () => set(i)));
    dots.forEach((d, i) => d.addEventListener("click", () => set(i)));
    stage.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") set(Math.min(cards.length - 1, active + 1));
      else if (e.key === "ArrowLeft" || e.key === "ArrowUp") set(Math.max(0, active - 1));
      else return;
      e.preventDefault();
    });

    // The wheel over the deck turns its cards; anywhere else the page scrolls as usual.
    let sum = 0;
    let lastTurn = 0;
    let lastPage = -Infinity;
    const deck = root.querySelector(".cascade");
    window.addEventListener("wheel", (e) => { if (!deck.contains(e.target)) lastPage = performance.now(); }, { passive: true });
    deck.addEventListener("wheel", (e) => {
      const now = performance.now();
      if (e.ctrlKey) return;
      if (now - lastPage < SAME_SCROLL) { lastPage = now; return; }
      e.preventDefault();
      const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? window.innerHeight : 1;
      sum += (Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX) * unit;
      if (Math.abs(sum) < STEP || now - lastTurn < PAUSE) return;
      set(active + Math.sign(sum));
      sum = 0;
      lastTurn = now;
    }, { passive: false });

    els.forEach((el, i) => place(el, i - progress, cardH));
    show();
    return { set: (i) => set(i, false) };
  }

  window.TGCascade = { mount };
})();
