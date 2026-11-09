// The opening's way in: the first click, scroll (wheel), touch or key opens the site. Only one of them counts; the
// opening stops listening at once, so the same gesture never reaches the site underneath.
// As in the reference: the shield flies to the top left, a pale disc lights under it, and the site opens from that
// spot as a growing circle. The timings match intro.css and style.css.

(() => {
  const intro = document.getElementById("intro");
  const logo = intro && intro.querySelector(".intro-logo-box");
  const root = document.documentElement;
  const body = document.body;
  if (!intro || !logo) return;

  const KEYS = new Set(["Enter", " ", "Spacebar", "ArrowDown", "PageDown", "Escape"]);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DOCK = 44; // without the rail: the centre of the spot the shield flies to, from the top left
  const DOCK_SIZE = 34; // and its height there
  const OPENED = 1900; // the shield's flight (0.7 s), then the circle from 0.65 s for 1.1 s, in ms
  let gone = false;

  function enter(event) {
    if (gone) return;
    if (event.type === "keydown" && !KEYS.has(event.key)) return;
    if (event.cancelable) event.preventDefault();
    gone = true;
    stop();

    // Where the shield stands now, and where and how small it lands: on the rail's own shield, so when the opening
    // fades the rail's shield is already there in its place. Without the rail, the top left corner.
    const box = logo.getBoundingClientRect();
    const target = document.querySelector(".rail-logo svg");
    const spot = target ? target.getBoundingClientRect() : null;
    const dockX = spot ? spot.left + spot.width / 2 : DOCK;
    const dockY = spot ? spot.top + spot.height / 2 : DOCK;
    const size = spot ? spot.height : DOCK_SIZE;
    root.style.setProperty("--dock-x", `${dockX}px`);
    root.style.setProperty("--dock-y", `${dockY}px`);
    logo.style.setProperty("--fly-x", `${dockX - (box.left + box.width / 2)}px`);
    logo.style.setProperty("--fly-y", `${dockY - (box.top + box.height / 2)}px`);
    logo.style.setProperty("--fly-s", `${size / box.height}`);

    body.classList.add("entering");
    document.dispatchEvent(new Event("tg:entering")); // the page's layers come in behind the circle (pages.js)
    const finish = () => {
      body.classList.remove("intro-on", "entering");
      body.classList.add("entered");
    };
    if (reduced) finish();
    else setTimeout(finish, OPENED);
  }

  const options = { passive: false };
  function stop() {
    intro.removeEventListener("click", enter);
    window.removeEventListener("wheel", enter, options);
    window.removeEventListener("touchstart", enter, options);
    window.removeEventListener("keydown", enter);
  }

  intro.addEventListener("click", enter);
  window.addEventListener("wheel", enter, options);
  window.addEventListener("touchstart", enter, options);
  window.addEventListener("keydown", enter);
  intro.tabIndex = 0;
  intro.focus({ preventScroll: true });
})();
