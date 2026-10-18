import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { REFRESH_MS } from "./api/hooks";
import { Layout } from "./components/Layout";
import { Dhw } from "./pages/Dhw";
import { Energy } from "./pages/Energy";
import { Heating } from "./pages/Heating";
import { History } from "./pages/History";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchInterval: REFRESH_MS,
        refetchOnWindowFocus: true,
        staleTime: 30_000,
        retry: 1,
      },
    },
  });
}

export const routes = [
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "ecs", element: <Dhw /> },
      { path: "chauffage", element: <Heating /> },
      { path: "historique", element: <History /> },
      { path: "energie", element: <Energy /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

const router = createBrowserRouter(routes);
const queryClient = makeQueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
