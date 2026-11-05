import { useQuery } from "@tanstack/react-query";

import { fetchRepresentativeSession } from "./catalog-api";
import type { RepresentativeSessionStatus } from "../types";

export function sessionRefreshInterval(session: RepresentativeSessionStatus | undefined): number | false {
  if (!session?.authenticated) return false;
  if (session.activity_tracking_available) return 60_000;
  const expiresAt = Date.parse(session.expires_at || "");
  if (!Number.isFinite(expiresAt)) return false;
  // Check at expiry; the minimum also prevents tight polling with a skewed client clock.
  return Math.min(2_147_483_647, Math.max(30_000, expiresAt - Date.now() + 250));
}

export function useRepresentativeSession() {
  return useQuery({
    queryKey: ["representative-session"],
    queryFn: fetchRepresentativeSession,
    retry: false,
    staleTime: 60_000,
    refetchInterval: (query) => sessionRefreshInterval(query.state.data),
    refetchIntervalInBackground: false,
  });
}
