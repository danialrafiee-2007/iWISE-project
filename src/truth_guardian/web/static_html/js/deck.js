// Two simple choosers of the site's own design (D-214), in place of the decks first taken from bought layers:
// 1. TGDeck.examples(element, { cards: [{ key, label, glow, html }], onOpen(i), label }): Check an answer's ready-made
//    examples as a grid of warm cards, each with a stripe in its colour; a click (or Enter) opens one.
// 2. TGDeck.tricks(element, { cards: [{ key, label, fill, html }], active, onActive(i), label }): Fool the Guardian's
//    tricks as a row of cards to choose from, one chosen at a time (arrow keys move the choice); under them a foot
//    (.tk-foot) for the page's own row. Returns { set(i) }.

(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function examples(root, opts) {
    const { cards } = opts;
    root.innerHTML = `<div class="ex-grid" role="list" aria-label="${esc(opts.label || "")}">
      ${cards.map((c, i) => `<button type="button" class="ex-tile" role="listitem" data-i="${i}" style="--accent:${esc(c.glow || "#2fb36a")}" aria-label="${esc(c.label)}">${c.html}</button>`).join("")}
    </div>`;
    root.querySelectorAll(".ex-tile").forEach((b) => b.addEventListener("click", () => opts.onOpen?.(+b.dataset.i)));
    return {};
  }

  function tricks(root, opts) {
    const { cards } = opts;
    let active = Math.max(0, Math.min(cards.length - 1, opts.active || 0));
    root.innerHTML = `<div class="tk">
      <div class="tk-grid" role="radiogroup" aria-label="${esc(opts.label || "")}">
        ${cards.map((c, i) => `<button type="button" class="tk-card" role="radio" data-i="${i}" style="--fill:${esc(c.fill || "#2fb36a")}" aria-label="${esc(c.label)}">${c.html}</button>`).join("")}
      </div>
      <div class="tk-foot"></div>
    </div>`;
    const buttons = [...root.querySelectorAll(".tk-card")];
    function set(i, tell = true, focus = false) {
      active = (i + cards.length) % cards.length;
      buttons.forEach((b, k) => {
        b.setAttribute("aria-checked", String(k === active));
        b.tabIndex = k === active ? 0 : -1;
      });
      if (focus) buttons[active].focus();
      if (tell) opts.onActive?.(active);
    }
    buttons.forEach((b, i) => {
      b.addEventListener("click", () => set(i));
      b.addEventListener("keydown", (e) => {
        const rtl = document.documentElement.dir === "rtl";
        const step = { ArrowRight: rtl ? -1 : 1, ArrowLeft: rtl ? 1 : -1, ArrowDown: 1, ArrowUp: -1 }[e.key];
        if (!step) return;
        e.preventDefault();
        set(active + step, true, true);
      });
    });
    set(active, false);
    return { set: (i) => set(i, false) };
  }

  window.TGDeck = { examples, tricks };
})();
