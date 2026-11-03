import { lazy, Suspense } from "react";
import { createHashRouter, RouterProvider } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";

// Hash routes (/#/matchup) work on any static host without server rewrites.
const page = (load: () => Promise<{ default: React.ComponentType }>) => {
  const C = lazy(load);
  return <Suspense fallback={<Loading label="Loading page…" />}><C /></Suspense>;
};

const router = createHashRouter([{
  path: "/", element: <Layout />, children: [
    { index: true, element: page(() => import("./pages/Dashboard")) },
    { path: "matchup", element: page(() => import("./pages/Matchup")) },
    { path: "matchup/:gameId", element: page(() => import("./pages/Matchup")) },
    { path: "schedule", element: page(() => import("./pages/Schedule")) },
    { path: "team", element: page(() => import("./pages/TeamStats")) },
    { path: "players", element: page(() => import("./pages/Players")) },
    { path: "players/:playerId", element: page(() => import("./pages/PlayerDetail")) },
    { path: "depth", element: page(() => import("./pages/DepthChart")) },
    { path: "injuries", element: page(() => import("./pages/Injuries")) },
    { path: "tendencies", element: page(() => import("./pages/Tendencies")) },
    { path: "model", element: page(() => import("./pages/ModelPage")) },
    { path: "data", element: page(() => import("./pages/DataPage")) },
    { path: "*", element: page(() => import("./pages/NotFound")) },
  ],
}]);

export function App() {
  return <RouterProvider router={router} />;
}
