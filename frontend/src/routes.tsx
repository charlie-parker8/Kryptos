import { createBrowserRouter, Navigate } from "react-router";

import { RequireAuth } from "@/app/RequireAuth";
import { AuthLayout } from "@/auth/AuthLayout";
import { LoginScreen } from "@/auth/LoginScreen";
import { RegisterScreen } from "@/auth/RegisterScreen";
import { AppShell } from "@/dashboard/AppShell";
import { Dashboard } from "@/dashboard/Dashboard";
import { LeaderboardScreen } from "@/leaderboard/LeaderboardScreen";
import { TradeScreen } from "@/trade/TradeScreen";

export const router = createBrowserRouter([
  {
    path: "/login",
    element: (
      <AuthLayout>
        <LoginScreen />
      </AuthLayout>
    ),
  },
  {
    path: "/register",
    element: (
      <AuthLayout>
        <RegisterScreen />
      </AuthLayout>
    ),
  },
  {
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { path: "/", element: <Dashboard /> },
      { path: "/trade", element: <TradeScreen /> },
      { path: "/leaderboard", element: <LeaderboardScreen /> },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
