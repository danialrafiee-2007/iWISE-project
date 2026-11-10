// The Architecture page's live map of the code (D-206), after the AI Engine section of the owner's earlier project:
// a force-directed graph per part of Truth Guardian (js/arch-data.js). Scroll to zoom, drag the background to pan, drag
// a node to move it; hovering a node names it, clicking it opens a window over the page with what it does (in the
// page's language), its inputs and outputs and its whole real code (js/arch-src.js, D-208). A double-click on the
// background opens, under it, the
// graph that explains this graph; on that one a double-click resets the zoom. In the site's colours: modules in deep
// green, functions in peach, on the warm panel.

(() => {
  const stack = document.getElementById("arch-graphs");
  const DATA = window.TG_ARCH;
  if (!stack || !DATA) return;
  // SVG's namespace, read from an SVG element the page makes (the front end names no internet address).
  const probe = document.createElement("div");
  probe.innerHTML = "<svg></svg>";
  const SVGNS = probe.firstChild.namespaceURI;
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };
  const sv = (tag) => document.createElementNS(SVGNS, tag);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Hub-to-leaf links, then the flow between modules.
  function buildLinks(nodes, flow) {
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const links = nodes.filter((n) => n.type === "leaf" && byId[n.group]).map((n) => [n.group, n.id]);
    for (const f of flow) if (byId[f[0]] && byId[f[1]]) links.push(f);
    return { byId, links };
  }

  // The real code of a node, as the build script read it from the source files; a module without a file of its own
  // says to open its functions.
  function codeOf(n) {
    const src = window.TG_SRC || {};
    if (n.src && src[n.src]) return src[n.src];
    return tr("html.ag.noCode");
  }

  let gid = 0;
  function makeGraph(mount, key, opts = {}) {
    const { nodes, flow } = DATA[key];
    const id = ++gid;
    const { byId, links } = buildLinks(nodes, flow);

    // ---- The page: the graph's box (title, tooltip, legend); a node's code opens in the window over the page ----
    const wrap = el("div", "ag-wrap");
    const graph = el("div", "ag-graph");
    graph.dir = "ltr";
    const svg = sv("svg");
    svg.setAttribute("class", "ag-svg");
    svg.setAttribute("role", "img");
    const mid = `ag-arrow-${id}`;
    svg.innerHTML = `<defs><marker id="${mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="ag-arrow"/></marker></defs>`;
    const gRoot = sv("g");
    svg.appendChild(gRoot);
    graph.appendChild(svg);
    const head = el("div", "ag-title");
    graph.appendChild(head);
    if (opts.closable) {
      const close = el("button", "ag-close");
      close.type = "button";
      close.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
      close.addEventListener("click", () => { stop(); wrap.remove(); opts.onClose?.(); });
      graph.appendChild(close);
    }
    const tip = el("div", "ag-tip");
    tip.hidden = true;
    graph.appendChild(tip);
    const legend = el("div", "ag-legend");
    graph.appendChild(legend);
    wrap.appendChild(graph);

    mount.appendChild(wrap);

    // The words in the page's language; called again when the language changes.
    function words() {
      head.innerHTML = `<b>${esc(tr(opts.title))}</b><span>${esc(tr(opts.subtitle))}</span>`;
      legend.innerHTML = `<span><i class="ag-dot hub"></i>${esc(tr("html.ag.module"))}</span><span><i class="ag-dot leaf"></i>${esc(tr("html.ag.function"))}</span><span class="ag-hint">${esc(tr(opts.closable ? "html.ag.hintMeta" : "html.ag.hint"))}</span>`;
      svg.setAttribute("aria-label", tr(opts.title));
      if (hovered) hover(hovered);
    }

    // ---- Physics: every node pushes the others away, every link pulls like a spring toward its length, and a weak
    // pull keeps all near the centre; the root stays at the centre. ----
    const R = { root: 24, hub: 14 };
    function radius(n) {
      return n.type === "leaf" ? 5 + n.w * 6 : R[n.type];
    }
    function restLen(a, b) {
      const s = byId[a], t = byId[b];
      if (s.type === "root") return 130;
      if (s.type === "hub" && t.type === "leaf") return 52 + (1 - t.w) * 120;
      return s.type === "hub" ? 165 : 95;
    }
    let W = 0, H = 0, cx = 0, cy = 0;
    function measure() {
      W = graph.clientWidth || 800;
      H = graph.clientHeight || 540;
      cx = W / 2;
      cy = H / 2 + 14;
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    }
    function seed() {
      nodes.forEach((n, i) => {
        if (n.type === "root") { n.x = cx; n.y = cy; } else {
          const a = (i / nodes.length) * Math.PI * 2, r = n.type === "hub" ? 120 : 200;
          n.x = cx + Math.cos(a) * r + (Math.random() - 0.5) * 30;
          n.y = cy + Math.sin(a) * r + (Math.random() - 0.5) * 30;
        }
        n.vx = 0; n.vy = 0;
      });
    }
    const K_REP = 2800, K_SPRING = 0.02, K_GRAV = 0.008, DAMP = 0.86, MAXV = 22;
    function tick() {
      for (const n of nodes) { n.fx = 0; n.fy = 0; }
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy || 0.01;
          const f = K_REP / d2, d = Math.sqrt(d2), ux = dx / d, uy = dy / d;
          a.fx += ux * f; a.fy += uy * f; b.fx -= ux * f; b.fy -= uy * f;
        }
      }
      for (const [s, t] of links) {
        const a = byId[s], b = byId[t];
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = K_SPRING * (d - restLen(s, t)), ux = dx / d, uy = dy / d;
        a.fx += ux * f; a.fy += uy * f; b.fx -= ux * f; b.fy -= uy * f;
      }
      for (const n of nodes) {
        if (n === dragged) continue;
        if (n.type === "root") { n.x = cx; n.y = cy; n.vx = n.vy = 0; continue; }
        n.fx += (cx - n.x) * K_GRAV; n.fy += (cy - n.y) * K_GRAV;
        n.vx = Math.max(-MAXV, Math.min(MAXV, (n.vx + n.fx) * DAMP + (Math.random() - 0.5) * 0.06));
        n.vy = Math.max(-MAXV, Math.min(MAXV, (n.vy + n.fy) * DAMP + (Math.random() - 0.5) * 0.06));
        n.x += n.vx; n.y += n.vy;
        const r = radius(n) + 3;
        n.x = Math.max(r, Math.min(W - r, n.x));
        n.y = Math.max(r + 40, Math.min(H - r - 28, n.y));
      }
    }

    // ---- Drawing: a line with an arrow per link (input to output), a circle per node, under the zoom ----
    let k = 1, tx = 0, ty = 0;
    const applyTransform = () => gRoot.setAttribute("transform", `translate(${tx},${ty}) scale(${k})`);
    const edges = links.map(([s, t]) => {
      const line = sv("line");
      line.setAttribute("class", "ag-edge");
      line.setAttribute("marker-end", `url(#${mid})`);
      line.dataset.s = s; line.dataset.t = t;
      gRoot.appendChild(line);
      return line;
    });
    const circles = {};
    for (const n of nodes) {
      const c = sv("circle");
      c.setAttribute("class", `ag-node ${n.type}`);
      c.setAttribute("r", radius(n));
      c.setAttribute("tabindex", "0");
      c.dataset.id = n.id;
      gRoot.appendChild(c);
      circles[n.id] = c;
      c.addEventListener("mouseenter", () => hover(n));
      c.addEventListener("mouseleave", () => hover(null));
      c.addEventListener("focus", () => hover(n));
      c.addEventListener("blur", () => hover(null));
      c.addEventListener("click", (e) => { e.stopPropagation(); select(n); });
      c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(n); } });
      c.addEventListener("pointerdown", (e) => startDrag(e, n));
    }
    function paint() {
      for (const line of edges) {
        const s = byId[line.dataset.s], t = byId[line.dataset.t];
        const dx = t.x - s.x, dy = t.y - s.y, d = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / d, uy = dy / d;
        line.setAttribute("x1", s.x + ux * radius(s));
        line.setAttribute("y1", s.y + uy * radius(s));
        line.setAttribute("x2", t.x - ux * (radius(t) + 5));
        line.setAttribute("y2", t.y - uy * (radius(t) + 5));
      }
      for (const n of nodes) { circles[n.id].setAttribute("cx", n.x); circles[n.id].setAttribute("cy", n.y); }
      applyTransform();
      if (hovered) placeTip(hovered);
    }
    // The hovered or chosen node and its neighbours stay lit, the rest dim.
    function applyClasses() {
      const focus = hovered || selected;
      const near = new Set(focus ? [focus.id] : []);
      if (focus) for (const [s, t] of links) { if (s === focus.id) near.add(t); if (t === focus.id) near.add(s); }
      for (const n of nodes) {
        const hot = n === hovered || n === selected;
        circles[n.id].classList.toggle("hot", hot);
        circles[n.id].classList.toggle("dim", !!focus && !near.has(n.id));
      }
      for (const line of edges) {
        const on = !!focus && (line.dataset.s === focus.id || line.dataset.t === focus.id);
        line.classList.toggle("hot", on);
        line.classList.toggle("dim", !!focus && !on);
      }
    }

    // ---- Interaction ----
    let hovered = null, selected = null, dragged = null;
    const roleOf = (n) => tr(n.type === "root" ? "html.ag.core" : n.type === "hub" ? "html.ag.module" : "html.ag.function");
    function placeTip(n) { tip.style.left = `${n.x * k + tx}px`; tip.style.top = `${n.y * k + ty}px`; }
    function hover(n) {
      hovered = n;
      if (n) {
        const sub = n.type === "leaf" ? `${roleOf(n)} · ${byId[n.group]?.title || ""}` : roleOf(n);
        tip.innerHTML = `${esc(n.title)}<small>${esc(sub)}</small>`;
        tip.hidden = false;
        placeTip(n);
      } else tip.hidden = true;
      applyClasses();
    }
    // A click opens the node in the window over the page, as the stages' buttons do; the node stays lit until it closes.
    function select(n) {
      selected = n;
      applyClasses();
      showNode(n, () => { selected = null; applyClasses(); });
    }
    function deselect() { selected = null; applyClasses(); }

    function svgPoint(e) {
      const r = svg.getBoundingClientRect();
      return { x: (e.clientX - r.left) * (W / (r.width || W || 1)), y: (e.clientY - r.top) * (H / (r.height || H || 1)) };
    }
    function graphPoint(e) { const p = svgPoint(e); return { x: (p.x - tx) / k, y: (p.y - ty) / k }; }
    function startDrag(e, n) {
      if (n.type === "root") return;
      e.preventDefault();
      e.stopPropagation();
      dragged = n;
      svg.classList.add("dragging");
      if (!running) { running = true; still = 0; frame = requestAnimationFrame(loop); }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    }
    let panning = null, moved = false;
    svg.addEventListener("pointerdown", (e) => {
      if (dragged) return;
      panning = { x: e.clientX, y: e.clientY, tx, ty };
      moved = false;
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
    function onMove(e) {
      if (dragged) {
        const p = graphPoint(e);
        Object.assign(dragged, { x: p.x, y: p.y, vx: 0, vy: 0 });
        if (!running) paint();
        return;
      }
      if (!panning) return;
      const r = svg.getBoundingClientRect();
      const dx = (e.clientX - panning.x) * (W / (r.width || W)), dy = (e.clientY - panning.y) * (H / (r.height || H));
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      tx = panning.tx + dx; ty = panning.ty + dy;
      applyTransform();
      if (hovered) placeTip(hovered);
    }
    function onUp() {
      if (dragged) { dragged = null; svg.classList.remove("dragging"); }
      panning = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    svg.addEventListener("click", (e) => {
      if (e.target.classList?.contains("ag-node")) return;
      if (moved) { moved = false; return; }
      deselect();
    });
    // Zoom toward the pointer: the point under it stays where it is.
    function onWheel(e) {
      e.preventDefault();
      const p = svgPoint(e), gx = (p.x - tx) / k, gy = (p.y - ty) / k;
      const nk = Math.max(0.4, Math.min(4, k * Math.exp(-e.deltaY * 0.0015)));
      tx = p.x - gx * nk; ty = p.y - gy * nk; k = nk;
      applyTransform();
      if (hovered) placeTip(hovered);
    }
    svg.addEventListener("wheel", onWheel, { passive: false });
    svg.addEventListener("dblclick", (e) => {
      if (e.target.classList?.contains("ag-node")) return;
      if (opts.onDouble) opts.onDouble();
      else { k = 1; tx = 0; ty = 0; applyTransform(); }
    });

    // ---- Running: the physics runs while the graph settles and while a node is dragged ----
    let running = false, frame = 0, started = false, still = 0;
    function loop() {
      tick();
      paint();
      const energy = nodes.reduce((sum, n) => sum + Math.abs(n.vx) + Math.abs(n.vy), 0) / nodes.length;
      still = energy < 0.05 && !dragged ? still + 1 : 0;
      if (still > 90) running = false; // settled: the physics rests until a node is dragged
      if (running) frame = requestAnimationFrame(loop);
    }
    let waiting = false;
    function start() {
      if (started) { if (!running) { running = true; frame = requestAnimationFrame(loop); } return; }
      // Not laid out yet (its page still coming in): the size observer starts it once the box has its real width.
      if (!graph.clientWidth) { waiting = true; return; }
      waiting = false;
      started = true;
      measure();
      seed();
      if (reduced) for (let i = 0; i < 300; i++) tick();
      paint();
      running = true;
      frame = requestAnimationFrame(loop);
    }
    function stop() { running = false; cancelAnimationFrame(frame); }
    // When the box changes size (the window is resized, the page's layout settles), the physics takes the new
    // size and settles the nodes into it again.
    // The whole layout moves with the centre, so the nodes never stay bunched where the old centre was (D-207).
    new ResizeObserver(() => {
      if (waiting) { start(); return; }
      if (!started || !graph.clientWidth) return;
      const [ox, oy] = [cx, cy];
      measure();
      for (const n of nodes) { n.x += cx - ox; n.y += cy - oy; }
      still = 0;
      if (!running) { running = true; frame = requestAnimationFrame(loop); }
    }).observe(graph);

    words();
    return { start, stop, wrap, words };
  }

  // ---- The page: one main graph at a time, chosen by its button, and the meta graph under it on a double-click ----
  const TITLES = {
    guardian: ["html.ag.t.guardian", "html.ag.s.guardian"],
    answers: ["html.ag.t.answers", "html.ag.s.answers"],
    readers: ["html.ag.t.readers", "html.ag.s.readers"],
  };
  let main = null, kind = null, meta = null;
  function openMeta() {
    if (meta) { meta.wrap.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest" }); return; }
    meta = makeGraph(stack, "meta", { title: "html.ag.t.meta", subtitle: "html.ag.s.meta", closable: true, onClose: () => { meta = null; } });
    meta.start();
    meta.wrap.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest" });
  }
  function show(which) {
    if (which === kind && main) return;
    if (main) { main.stop(); main.wrap.remove(); }
    kind = which;
    main = makeGraph(stack, which, { title: TITLES[which][0], subtitle: TITLES[which][1], onDouble: openMeta });
    stack.prepend(main.wrap);
    main.start();
    document.querySelectorAll(".ag-tabs [data-graph]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.graph === which)));
  }
  document.querySelectorAll(".ag-tabs [data-graph]").forEach((b) => b.addEventListener("click", () => show(b.dataset.graph)));

  // The graph starts when its page is first shown (its size is known only then).
  const page = stack.closest(".page");
  const begin = () => { if (page && !page.hidden && !main) requestAnimationFrame(() => show("guardian")); };
  if (page) new MutationObserver(begin).observe(page, { attributes: true, attributeFilter: ["hidden"] });
  begin();
  if (window.TG) window.TG.onLang(() => { main?.words(); meta?.words(); });

  // ---- The window over the page (D-207, D-208): a graph node or a stage's function button opens it with the node's
  // role, what it does, its inputs and outputs and its whole code. While it is open the page behind it is locked (see
  // style.css): the wheel and the scroll bar move only what is in the window. ----
  const dialog = document.getElementById("code-dialog");
  const nodeBySrc = {};
  for (const graph of Object.values(DATA)) for (const n of graph.nodes) if (n.src && !nodeBySrc[n.src]) nodeBySrc[n.src] = n;
  let onClosed = null;
  function closeCode() {
    if (!dialog?.open || dialog.classList.contains("closing")) return;
    const done = () => { dialog.close(); dialog.classList.remove("closing"); onClosed?.(); onClosed = null; };
    if (reduced) return done();
    dialog.classList.add("closing");
    setTimeout(done, 320);
  }
  const fileOf = (src) => `src/truth_guardian/${src.split(":")[0]}`.replace("src/truth_guardian/js/", "src/truth_guardian/web/static_html/js/");
  const roleName = (n) => tr(n.type === "root" ? "html.ag.core" : n.type === "hub" ? "html.ag.module" : "html.ag.function");
  function showNode(n, closed) {
    if (!dialog) return;
    const q = (s) => dialog.querySelector(s);
    q(".code-dialog-title").textContent = n.title;
    q(".code-dialog-role").textContent = roleName(n);
    q(".code-dialog-desc").textContent = tr(`html.ag.${n.id}`);
    q(".code-io-h.in").textContent = tr("html.ag.in");
    q(".code-io-h.out").textContent = tr("html.ag.out");
    q("[data-in]").innerHTML = (n.in || ["—"]).map((x) => `<li>${esc(x)}</li>`).join("");
    q("[data-out]").innerHTML = (n.out || ["—"]).map((x) => `<li>${esc(x)}</li>`).join("");
    q(".code-dialog-io").hidden = false;
    q(".code-dialog-desc").hidden = false;
    q(".code-dialog-h").textContent = tr("html.ag.code");
    q(".ag-file").textContent = n.src ? fileOf(n.src) : "";
    q("code").textContent = codeOf(n);
    onClosed = closed || null;
    window.TGLog?.log("architecture", "code opened", n.src || n.title);
    if (!dialog.open) dialog.showModal();
    q(".code-dialog-body").scrollTop = 0;
    q(".ag-code").scrollTop = 0;
  }
  function openCode(key) {
    const known = nodeBySrc[key];
    if (known) return showNode(known);
    const name = key.split(":")[1];
    showNode({ id: "", type: "leaf", title: /^[A-Z]/.test(name) ? name : `${name}()`, src: key });
    dialog.querySelector(".code-dialog-desc").hidden = true;
    dialog.querySelector(".code-dialog-io").hidden = true;
  }
  if (dialog) {
    dialog.querySelector(".dialog-x").addEventListener("click", closeCode);
    dialog.addEventListener("click", (e) => { if (e.target === dialog) closeCode(); });
    dialog.addEventListener("cancel", (e) => { e.preventDefault(); closeCode(); });
  }
  document.querySelectorAll(".arch-fn[data-src]").forEach((b) => b.addEventListener("click", () => openCode(b.dataset.src)));
})();
