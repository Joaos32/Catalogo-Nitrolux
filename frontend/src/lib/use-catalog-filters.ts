import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { persistUiState, readPersistedUiState } from "./catalog-storage";
import type { CatalogBrand } from "../types";

export function useCatalogFilters(batchSize: number) {
  const [initialParams] = useState((): Record<string, string> => {
    const current = new URLSearchParams(window.location.search);
    if (["q", "category", "brand", "limit"].some((key) => current.has(key))) return {};
    const saved = readPersistedUiState();
    return { brand: saved.brand, q: saved.query, category: saved.category };
  });
  const [params, setParams] = useSearchParams(initialParams);
  const initialized = useRef(false);
  const query = params.get("q") || "";
  const category = params.get("category") || "Todas";
  const brand: CatalogBrand = params.get("brand") === "pienza" ? "pienza" : "nitrolux";
  const requestedLimit = Number(params.get("limit"));
  const limit =
    Number.isSafeInteger(requestedLimit) && requestedLimit > 0 ? requestedLimit : batchSize;
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    const next = new URLSearchParams(params);
    if (!next.has("brand")) next.set("brand", brand);
    setParams(next, { replace: true });
  }, [brand, params, setParams]);
  useEffect(() => {
    const timer = window.setTimeout(() => persistUiState({ query, category, brand }), 250);
    return () => window.clearTimeout(timer);
  }, [brand, category, query]);
  const update = (
    changes: { q?: string; category?: string; brand?: CatalogBrand },
    replace = false
  ) => {
    const next = new URLSearchParams(params);
    next.set("brand", changes.brand ?? brand);
    for (const [key, value] of Object.entries(changes)) {
      if (!value || (key === "category" && value === "Todas")) next.delete(key);
      else next.set(key, value);
    }
    next.delete("limit");
    setParams(next, { replace });
  };
  const loadMore = (total: number) => {
    const next = new URLSearchParams(params);
    next.set("limit", String(Math.min(limit + batchSize, total)));
    setParams(next, { replace: true });
  };
  return { query, category, brand, limit, update, loadMore };
}
