import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import "@fontsource-variable/ibm-plex-sans/wght.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles/index.css";

import { connectRealtime } from "@/core/realtime/connectRealtime";
import { createMockSource } from "@/core/realtime/mockSource";
import { router } from "./routes";

// One market feed per app load (advanced-init-once). `?frozen` emits a single deterministic
// round and stops — used for stable screenshots.
const frozen = new URLSearchParams(window.location.search).has("frozen");
if (frozen) document.documentElement.dataset.frozen = "";
connectRealtime(createMockSource({ frozen }));

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("#root element not found");

createRoot(rootEl).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
