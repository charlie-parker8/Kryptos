/**
 * One shared `prefers-reduced-motion` source. `AnimatedNumber`, the ticker, and the
 * arcade DramaticMoment all consult this instead of each spinning up their own
 * matchMedia listener (`client-event-listeners`).
 */

import { useSyncExternalStore } from "react";

const query =
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

function subscribe(onChange: () => void): () => void {
  if (!query) return () => {};
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  return query?.matches ?? false;
}

/** Non-reactive read for imperative code (rAF loops, event handlers). */
export function prefersReducedMotion(): boolean {
  return getSnapshot();
}

/** Reactive read for components that render differently under reduced motion. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
