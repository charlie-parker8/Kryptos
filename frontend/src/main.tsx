import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { mutate, SWRConfig } from "swr";

import "@fontsource-variable/ibm-plex-sans/wght.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "./styles/index.css";

import { ApiError, apiGet } from "@/core/api/client";
import { SESSION_KEY } from "@/core/auth/useSession";
import { IS_FROZEN } from "@/core/realtime/mode";
import { router } from "./routes";

// `?frozen` holds looping animations on their first frame — see styles/index.css.
if (IS_FROZEN) document.documentElement.dataset.frozen = "";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("#root element not found");

createRoot(rootEl).render(
  <StrictMode>
    <SWRConfig
      value={{
        fetcher: (key: string) => apiGet(key),
        onError: (error, key) => {
          // A 401 anywhere means the cookie is gone/expired — re-check the session so the
          // route guard redirects to /login. Skip the session key itself (its own fetcher
          // already maps 401 → logged-out).
          if (
            error instanceof ApiError &&
            error.status === 401 &&
            key !== SESSION_KEY
          ) {
            void mutate(SESSION_KEY, null, { revalidate: false });
          }
        },
      }}
    >
      <RouterProvider router={router} />
    </SWRConfig>
  </StrictMode>,
);
