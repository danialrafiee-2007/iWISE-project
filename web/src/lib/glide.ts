/** Scroll softly to what has just been asked for, just under the top bar if it stays on screen (at once under reduced motion). */
export function glide(el: HTMLElement | null) {
  if (!el) return;
  const bar = document.querySelector("header");
  const covered = bar && getComputedStyle(bar).position === "sticky" ? bar.offsetHeight : 0;
  window.scrollTo({
    top: el.getBoundingClientRect().top + window.scrollY - covered - 16,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });
}
