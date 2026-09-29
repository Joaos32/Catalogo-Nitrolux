import { PHOTO_CACHE_STORAGE_KEY, UI_STATE_STORAGE_KEY } from "./catalog-core";
import type { ProductPhotos } from "../types";

export interface PersistedUiState {
  query: string;
  category: string;
  brand: "nitrolux" | "pienza";
}

const FALLBACK_STATE: PersistedUiState = {
  query: "",
  category: "Todas",
  brand: "nitrolux",
};

export type PersistedPhotosByCode = Record<string, ProductPhotos>;

const PHOTO_FIELDS: Array<keyof ProductPhotos> = ["white_background", "ambient", "measures"];
const MAX_PERSISTED_PHOTO_CODES = 500;

const TRANSIENT_URL_PARAMETERS = new Set([
  "expires",
  "signature",
  "sig",
  "token",
  "se",
  "sp",
  "sr",
  "st",
  "sv",
]);

function isPersistablePhoto(value: unknown): value is string {
  const source = String(value ?? "").trim();
  const normalized = source.toLowerCase();
  if (
    !source ||
    normalized.startsWith("data:") ||
    normalized.startsWith("blob:") ||
    (source.startsWith("//")) ||
    (!normalized.startsWith("/") && !normalized.startsWith("http://") && !normalized.startsWith("https://"))
  ) {
    return false;
  }

  if ([
    "placehold.co",
    "placeholder",
    "sem foto",
    "sem imagem",
  ].some((marker) => normalized.includes(marker))) {
    return false;
  }

  const query = source.split("?", 2)[1]?.split("#", 1)[0] || "";
  for (const key of new URLSearchParams(query).keys()) {
    const parameter = key.toLowerCase();
    if (TRANSIENT_URL_PARAMETERS.has(parameter) || parameter.startsWith("x-amz-")) {
      return false;
    }
  }
  return true;
}

function normalizePersistedPhotos(value: unknown): ProductPhotos | null {
  if (!value || typeof value !== "object") return null;

  const source = value as Record<string, unknown>;
  const normalized: ProductPhotos = {};
  for (const field of PHOTO_FIELDS) {
    const photo = source[field];
    if (isPersistablePhoto(photo)) {
      normalized[field] = photo;
    }
  }

  return Object.keys(normalized).length > 0 ? normalized : null;
}

export function readPersistedPhotos(): PersistedPhotosByCode {
  if (typeof window === "undefined" || !window.localStorage) {
    return {};
  }

  try {
    const rawValue = window.localStorage.getItem(PHOTO_CACHE_STORAGE_KEY);
    if (!rawValue) return {};

    const parsed = JSON.parse(rawValue) as unknown;
    if (!parsed || typeof parsed !== "object") return {};

    const result: PersistedPhotosByCode = {};
    const entries = Object.entries(parsed as Record<string, unknown>).slice(-MAX_PERSISTED_PHOTO_CODES);
    for (const [rawCode, value] of entries) {
      const code = rawCode.trim();
      const photos = normalizePersistedPhotos(value);
      if (code && photos) {
        result[code] = photos;
      }
    }
    return result;
  } catch (error) {
    console.warn("Não foi possível ler fotos persistidas.", error);
    return {};
  }
}

export function persistPhotosByCode(photosByCode: Record<string, ProductPhotos | null | undefined>): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    const current = readPersistedPhotos();
    let changed = false;

    for (const [rawCode, photos] of Object.entries(photosByCode)) {
      const code = rawCode.trim();
      const normalized = normalizePersistedPhotos(photos);
      if (!code || !normalized) continue;

      const merged = { ...(current[code] || {}), ...normalized };
      if (JSON.stringify(current[code] || {}) !== JSON.stringify(merged)) {
        delete current[code];
        current[code] = merged;
        changed = true;
      }
    }

    if (changed) {
      const entries = Object.entries(current).slice(-MAX_PERSISTED_PHOTO_CODES);
      const bounded = Object.fromEntries(entries);
      window.localStorage.setItem(PHOTO_CACHE_STORAGE_KEY, JSON.stringify(bounded));
    }
  } catch (error) {
    console.warn("Não foi possível persistir fotos do catálogo.", error);
  }
}

export function readPersistedUiState(): PersistedUiState {
  if (typeof window === "undefined" || !window.localStorage) {
    return FALLBACK_STATE;
  }

  try {
    const rawValue = window.localStorage.getItem(UI_STATE_STORAGE_KEY);
    if (!rawValue) return FALLBACK_STATE;

    const parsed = JSON.parse(rawValue) as Partial<PersistedUiState>;
    return {
      query: typeof parsed.query === "string" ? parsed.query : FALLBACK_STATE.query,
      category:
        typeof parsed.category === "string" && parsed.category
          ? parsed.category
          : FALLBACK_STATE.category,
      brand: parsed.brand === "pienza" ? "pienza" : FALLBACK_STATE.brand,
    };
  } catch (error) {
    console.warn("Não foi possível ler estado de UI persistido.", error);
    return FALLBACK_STATE;
  }
}

export function persistUiState(state: PersistedUiState): void {
  if (typeof window === "undefined" || !window.localStorage) {
    return;
  }

  try {
    window.localStorage.setItem(UI_STATE_STORAGE_KEY, JSON.stringify(state));
  } catch (error) {
    console.warn("Não foi possível persistir estado de UI.", error);
  }
}
