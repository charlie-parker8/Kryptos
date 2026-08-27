import { createBrowserRouter } from "react-router";

import { AppShell } from "@/dashboard/AppShell";
import { Dashboard } from "@/dashboard/Dashboard";

export const router = createBrowserRouter([
  {
    path: "/",
    element: (
      <AppShell>
        <Dashboard />
      </AppShell>
    ),
  },
  {
    path: "*",
    element: (
      <AppShell>
        <Dashboard />
      </AppShell>
    ),
  },
]);
