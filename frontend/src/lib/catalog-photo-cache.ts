import { getProductImageCandidates } from "./catalog-products";
import type { ProductPhotos } from "../types";

export type PhotosByCode = Record<string, ProductPhotos>;

const PHOTO_FIELDS = ["white_background", "ambient", "measures"] as const;

export function mergePhotoSources(
  ...sources: Array<ProductPhotos | null | undefined>
): ProductPhotos | null {
  const merged: ProductPhotos = {};
  for (const source of sources) {
    if (!source) continue;
    for (const field of PHOTO_FIELDS) {
      const value = source[field];
      if (!merged[field] && getProductImageCandidates({ [field]: value }).length > 0) {
        merged[field] = value;
      }
    }
  }
  return Object.keys(merged).length > 0 ? merged : null;
}

/** Retain real session photos even when storage rejects or evicts their URLs. */
export function mergePhotosByCode(current: PhotosByCode, incoming: PhotosByCode): PhotosByCode {
  let result = current;
  for (const [code, photos] of Object.entries(incoming)) {
    const merged = mergePhotoSources(photos, current[code]);
    if (!merged || PHOTO_FIELDS.every((field) => merged[field] === current[code]?.[field]))
      continue;
    if (result === current) result = { ...current };
    result[code] = merged;
  }
  return result;
}
