import type { PropsWithChildren } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate, useLocation } from "react-router-dom";

import { fetchRepresentativeSession } from "../lib/catalog-api";

function buildNextPath(pathname: string, search: string, hash: string): string {
  const next = `${pathname}${search}${hash}`.trim();
  if (!next.startsWith("/") || next.startsWith("//")) return "/";
  return next || "/";
}

export default function RepresentativeGuard({
  children,
}: PropsWithChildren): JSX.Element {
  const location = useLocation();
  const sessionQuery = useQuery({
    queryKey: ["representative-session"],
    queryFn: fetchRepresentativeSession,
    retry: false,
    refetchInterval: 2 * 60_000,
    refetchIntervalInBackground: false,
  });

  if (sessionQuery.isLoading) {
    return (
      <div className="page-shell">
        <main className="content-wrap">
          <section className="loading-state" role="status" aria-live="polite">
            Validando acesso do representante...
          </section>
        </main>
      </div>
    );
  }

  if (sessionQuery.isError) {
    return (
      <div className="page-shell">
        <main className="content-wrap">
          <div className="banner banner-warning">
            Não foi possível validar o acesso agora. Atualize a página e tente novamente.
          </div>
        </main>
      </div>
    );
  }

  if (!sessionQuery.data?.protection_enabled || sessionQuery.data?.authenticated) {
    return <>{children}</>;
  }

  const nextPath = buildNextPath(location.pathname, location.search, location.hash);
  return <Navigate to={`/login?next=${encodeURIComponent(nextPath)}`} replace />;
}
