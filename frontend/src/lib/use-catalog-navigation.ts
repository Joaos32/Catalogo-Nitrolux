import { useEffect } from "react";

const RETURN_POSITION_KEY = "catalog.return.v1";
export function rememberCatalogPosition(search: string, routeId: string): void {
  try {
    sessionStorage.setItem(
      RETURN_POSITION_KEY,
      JSON.stringify({ search, routeId, scroll: window.scrollY })
    );
  } catch {
    /* Navigation also works when browser storage is restricted. */
  }
}
export function useCatalogNavigation(
  productId: string | undefined,
  ready: boolean,
  search: string
): void {
  useEffect(() => {
    if (productId || !ready) return;
    let saved: { search?: string; routeId?: string; scroll?: number } | null = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(RETURN_POSITION_KEY) || "null");
    } catch {
      return;
    }
    if (
      !saved ||
      saved.search !== search ||
      typeof saved.routeId !== "string" ||
      !Number.isFinite(saved.scroll)
    )
      return;
    const { routeId, scroll } = saved;
    const frame = requestAnimationFrame(() => {
      document.getElementById(`product-link-${routeId}`)?.focus({ preventScroll: true });
      window.scrollTo(0, Math.max(0, scroll || 0));
      try {
        sessionStorage.removeItem(RETURN_POSITION_KEY);
      } catch {
        /* Storage may be restricted. */
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [productId, ready, search]);
}
