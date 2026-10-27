import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from "react";
import { useRouter } from "./router";

const CLOSE_DELAY = 180;
const EDGE = 12;

/** A menu in the top bar that opens as soon as the pointer rests on it (no click needed). A click or a tap opens it
 *  too, for touch screens, and keeps it open when the pointer leaves; a second click, a click outside, Escape or a
 *  change of page closes it. `shift` keeps the open list inside the screen on a narrow window. */
export function useHoverMenu() {
  const { path } = useRouter();
  const [open, setOpen] = useState(false);
  const [shift, setShift] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const timer = useRef(0);
  // Opened by a click or tap rather than by resting the pointer: then leaving with the pointer does not close it.
  const pinned = useRef(false);

  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  // A short delay lets the pointer cross the gap between the label and the list.
  const hide = () => {
    window.clearTimeout(timer.current);
    if (!pinned.current) timer.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY);
  };
  const close = () => {
    pinned.current = false;
    setOpen(false);
  };
  // The pointer has usually opened the list on its way to a click, so a click keeps it open; a second click closes it.
  const toggle = () => {
    window.clearTimeout(timer.current);
    if (open && pinned.current) close();
    else {
      pinned.current = true;
      setOpen(true);
    }
  };
  const pin = () => {
    pinned.current = true;
    setOpen(true);
  };

  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(close, [path]);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: globalThis.PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        root.current?.querySelector<HTMLButtonElement>("button")?.focus();
      }
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  useLayoutEffect(() => {
    const el = list.current;
    if (!open || !el) return setShift(0);
    el.style.translate = "0";
    const box = el.getBoundingClientRect();
    const over = box.right - (window.innerWidth - EDGE);
    const under = EDGE - box.left;
    setShift(over > 0 ? -over : under > 0 ? under : 0);
  }, [open]);

  const mouse = (act: () => void) => (e: PointerEvent) => e.pointerType === "mouse" && act();
  return { open, root, list, shift, show, hide, close, toggle, pin, hover: { onPointerEnter: mouse(show), onPointerLeave: mouse(hide) } };
}

/** Up and down arrows move between the open list's items. */
export function moveFocus(e: React.KeyboardEvent, root: HTMLElement | null) {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  e.preventDefault();
  const items = [...(root?.querySelectorAll<HTMLElement>("[role=menuitem]:not([aria-disabled=true])") ?? [])];
  const at = items.indexOf(document.activeElement as HTMLElement);
  items[(at + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus();
}
