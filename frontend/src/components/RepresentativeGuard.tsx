import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useRepresentativeSession } from "../lib/use-representative-session";

function buildNextPath(pathname: string, search: string, hash: string): string {
  const next = `${pathname}${search}${hash}`.trim();
  if (!next.startsWith("/") || next.startsWith("//")) return "/";
  return next || "/";
}

export default function RepresentativeGuard({
  children,
}: PropsWithChildren): JSX.Element {
  const location = useLocation();
  const sessionQuery = useRepresentativeSession();

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
