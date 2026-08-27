/**
 * Light/dark theme state. The value is a single attribute on <html> (`data-theme`); the
 * inline script in index.html applies the stored/system choice before first paint so there
 * is no flash. This module keeps React in sync and persists an explicit choice.
 */

import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const STORAGE_KEY = "kryptos:theme:v1";

const media =
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

function readStored(): Theme | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return media?.matches ? "dark" : "light";
}

export function currentTheme(): Theme {
  const attr = document.documentElement.dataset.theme;
  return attr === "light" || attr === "dark"
    ? attr
    : (readStored() ?? systemTheme());
}

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

const listeners = new Set<() => void>();
function emit(): void {
  for (const listener of listeners) listener();
}

export function setTheme(theme: Theme): void {
  apply(theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // private mode / disabled — the choice just won't persist
  }
  emit();
}

export function toggleTheme(): void {
  setTheme(currentTheme() === "dark" ? "light" : "dark");
}

// Follow the system until the user makes an explicit choice.
media?.addEventListener("change", () => {
  if (readStored() === null) {
    apply(systemTheme());
    emit();
  }
});

function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme, () => "dark");
}
