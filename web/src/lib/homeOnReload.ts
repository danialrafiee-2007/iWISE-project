const KEEP = "tg-keep-page-on-reload";
const TOUCHED = ["pointerdown", "keydown", "wheel", "touchstart"] as const;

/** Reloads and stays on this page: the site's own reloads, which go back to what failed to load. */
export function reloadHere() {
  try {
    sessionStorage.setItem(KEEP, "1");
  } catch {
    /* storage unavailable */
  }
  window.location.reload();
}

/** A reload by the visitor starts the site over, on the home page at its top. A link opened directly keeps its page. */
export function homeOnReload() {
  let keep = false;
  try {
    keep = sessionStorage.getItem(KEEP) === "1";
    sessionStorage.removeItem(KEEP);
  } catch {
    /* storage unavailable */
  }
  const entry = performance.getEntriesByType?.("navigation")[0] as PerformanceNavigationTiming | undefined;
  if (keep || entry?.type !== "reload") return;
  const { pathname, search, hash } = window.location;
  if (pathname + search + hash !== "/") window.history.replaceState(null, "", "/");
  // The browser would put back the scroll of the page left behind. Hold it off until the visitor first acts, then hand
  // it back so Back and Forward keep their places.
  window.history.scrollRestoration = "manual";
  window.scrollTo(0, 0);
  const handBack = () => {
    window.history.scrollRestoration = "auto";
    for (const type of TOUCHED) window.removeEventListener(type, handBack, true);
  };
  for (const type of TOUCHED) window.addEventListener(type, handBack, { capture: true, passive: true });
}
