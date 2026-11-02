import { useEffect, useRef, type RefObject } from "react";

// Over a card deck the mouse wheel turns its cards and the page stays still; anywhere else the page scrolls as usual.
// One thing keeps that from feeling like a trap: a scroll already moving the page carries on past a deck that slides
// under a resting pointer, and only a new turn of the wheel over the deck goes to the cards.

// How much scrolling makes one card (a mouse notch is about 100 px), and the pause before the next card, so a trackpad's
// long glide turns a few cards rather than dozens.
const STEP = 60;
const PAUSE = 260;
// A wheel event this soon after one that moved the page belongs to the same scroll.
const SAME_SCROLL = 250;

export function useWheelTurn(deck: RefObject<HTMLElement | null>, turn: (direction: number) => void) {
  const latest = useRef(turn);
  latest.current = turn;

  useEffect(() => {
    const el = deck.current;
    if (!el) return;
    let sum = 0;
    let lastTurn = 0;
    let lastPage = -Infinity;
    const onPage = (e: WheelEvent) => {
      if (!el.contains(e.target as Node)) lastPage = performance.now();
    };
    // A native listener, since React's wheel handler cannot stop the page from scrolling.
    const onDeck = (e: WheelEvent) => {
      const now = performance.now();
      if (e.ctrlKey) return; // the browser's zoom
      if (now - lastPage < SAME_SCROLL) {
        lastPage = now;
        return;
      }
      e.preventDefault();
      const unit = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? window.innerHeight : 1;
      sum += (Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX) * unit;
      if (Math.abs(sum) < STEP || now - lastTurn < PAUSE) return;
      latest.current(Math.sign(sum));
      sum = 0;
      lastTurn = now;
    };
    window.addEventListener("wheel", onPage, { passive: true });
    el.addEventListener("wheel", onDeck, { passive: false });
    return () => {
      window.removeEventListener("wheel", onPage);
      el.removeEventListener("wheel", onDeck);
    };
  }, [deck]);
}
