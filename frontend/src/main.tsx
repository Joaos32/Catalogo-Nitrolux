import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
} from "react-router-dom";

import App from "./App";
import RepresentativeGuard from "./components/RepresentativeGuard";
import RepresentativeLoginPage from "./components/RepresentativeLoginPage";
import "./styles.css";
import "./catalog-layout.css";
import "./product-presentation.css";

const ErpAdminPage = React.lazy(() => import("./components/ErpAdminPage"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<RepresentativeLoginPage />} />
      <Route
        path="/"
        element={
          <RepresentativeGuard>
            <App />
          </RepresentativeGuard>
        }
      />
      <Route
        path="/erp"
        element={
          <React.Suspense
            fallback={
              <main className="content-wrap">
                <p className="loading-state" role="status">
                  Carregando painel…
                </p>
              </main>
            }
          >
            <ErpAdminPage />
          </React.Suspense>
        }
      />
      <Route
        path="/produto/:productId"
        element={
          <RepresentativeGuard>
            <App />
          </RepresentativeGuard>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </>
  )
);

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
);
