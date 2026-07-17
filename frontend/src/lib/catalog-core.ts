import type { SyntheticEvent } from "react";

const DEFAULT_API_BASES = import.meta.env.DEV ? ["", "http://127.0.0.1:8000", "http://127.0.0.1:5000"] : [""];

function parseApiBases(rawValue: string | undefined): string[] {
  if (!rawValue) return [];
  return rawValue
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

const configuredTimeout = Number(import.meta.env.VITE_REQUEST_TIMEOUT_MS ?? "");
const configuredBases = parseApiBases(import.meta.env.VITE_API_BASES);

export const API_BASES = configuredBases.length > 0 ? configuredBases : DEFAULT_API_BASES;
export const REQUEST_TIMEOUT_MS =
  Number.isFinite(configuredTimeout) && configuredTimeout > 0 ? configuredTimeout : 12000;
export const UI_STATE_STORAGE_KEY = "catalog.ui.v2";

function escapeSvgText(value: string): string {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function createPlaceholderDataUrl(label: string, width = 240, height = 240): string {
  const safeLabel = escapeSvgText(label).slice(0, 60) || "Imagem";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${safeLabel}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#eef4ff" /><stop offset="100%" stop-color="#d7e7ff" /></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)" /><rect x="1" y="1" width="${width - 2}" height="${height - 2}" fill="none" stroke="#9dbcf2" stroke-width="2" stroke-dasharray="8 7" /><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="Manrope, Segoe UI, sans-serif" font-size="${Math.max(13, Math.round(width / 13))}" fill="#2f5aa8">${safeLabel}</text></svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

export function setFallbackImage(
  event: SyntheticEvent<HTMLImageElement, Event>,
  fallbackUrl: string
): void {
  const image = event.currentTarget;
  if (!image || image.dataset.fallbackApplied === "true") return;
  image.dataset.fallbackApplied = "true";
  image.src = fallbackUrl;
}

export const CARD_FALLBACK_IMAGE = createPlaceholderDataUrl("Sem imagem", 900, 700);
export const DETAIL_FALLBACK_IMAGE = createPlaceholderDataUrl("Sem imagem", 1200, 900);
export const THUMB_FALLBACK_IMAGE = createPlaceholderDataUrl("Sem foto", 240, 240);
