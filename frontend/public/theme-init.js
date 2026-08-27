// Apply the stored / system theme before first paint so there is no flash.
// External (not inline in index.html) so the production CSP can stay `script-src 'self'`
// with no per-build hash to maintain. Render-blocking in <head>; a few hundred edge-cached
// bytes, so the no-flash guarantee holds.
try {
  var stored = localStorage.getItem("kryptos:theme:v1");
  var theme =
    stored === "light" || stored === "dark"
      ? stored
      : window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
} catch {
  document.documentElement.dataset.theme = "dark";
}
