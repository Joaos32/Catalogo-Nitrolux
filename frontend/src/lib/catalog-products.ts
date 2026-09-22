import { createPlaceholderDataUrl, DETAIL_FALLBACK_IMAGE } from "./catalog-core";
import { absolutizeApiUrl } from "./catalog-api";
import type {
  CatalogBrand,
  CatalogProduct,
  GalleryApiImage,
  GalleryEntry,
  ProductAttribute,
  ProductPhotos,
  ProductRecord,
} from "../types";

export const DEMO_PRODUCTS: ProductRecord[] = [];

export function normalizeText(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function parseNumericValue(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return fallback;

    let normalized = trimmed.replace(/\s+/g, "");
    if (normalized.includes(",") && normalized.includes(".")) {
      normalized =
        normalized.lastIndexOf(",") > normalized.lastIndexOf(".")
          ? normalized.replace(/\./g, "").replace(",", ".")
          : normalized.replace(/,/g, "");
    } else if (normalized.includes(",")) {
      normalized = normalized.replace(/\./g, "").replace(",", ".");
    }

    const parsed = Number(normalized);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function hasVariantMarker(value: string, variant: number): boolean {
  return new RegExp(`(?:^|[\\s_\\-(])${variant}(?=[)\\s_.-]|$)`).test(value);
}

function getVisualPreferenceRank(value: string): number {
  const normalized = String(value || "").toLowerCase();
  if (!normalized) return 4;

  // A numeracao do Drive define a ordem principal da apresentacao:
  // _1 e a capa, seguido por _2 e _3.
  if (hasVariantMarker(normalized, 1)) {
    return 0;
  }
  if (hasVariantMarker(normalized, 2)) {
    return 1;
  }
  if (hasVariantMarker(normalized, 3)) {
    return 2;
  }
  if (normalized.includes("branco") || normalized.includes("white")) {
    return 3;
  }
  if (normalized.includes("medid")) {
    return 4;
  }
  if (normalized.includes("ambient") || normalized.includes("ambiente")) {
    return 5;
  }
  if (normalized.includes("descri") || normalized.includes("description")) {
    return 6;
  }
  return 7;
}

export function getPrimaryProductImage(photos: ProductPhotos | null | undefined, cover = ""): string {
  return photos?.white_background || photos?.measures || photos?.ambient || cover || "";
}

function normalizePhotoReference(value: unknown): string {
  const url = absolutizeApiUrl(String(value ?? "").trim());
  if (!url) return "";

  let marker = url.toLowerCase().replace(/\+/g, " ");
  try {
    marker = decodeURIComponent(marker);
  } catch {
    // Mantém a referência original quando a URL não possui encoding válido.
  }

  if (
    marker.includes("placehold.co") ||
    marker.includes("placeholder") ||
    marker.includes("sem foto") ||
    marker.includes("sem imagem")
  ) {
    return "";
  }

  return url;
}

export function getRandomShowcaseProducts(products: CatalogProduct[], limit: number): CatalogProduct[] {
  const safeLimit = Math.max(limit, 0);
  const randomized = products.slice();

  for (let index = randomized.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [randomized[index], randomized[randomIndex]] = [randomized[randomIndex], randomized[index]];
  }

  return randomized.slice(0, safeLimit);
}

function getField(item: ProductRecord | null | undefined, aliases: string[], fallback: unknown = ""): unknown {
  if (!item || typeof item !== "object") return fallback;

  const lookup: Record<string, unknown> = {};
  Object.keys(item).forEach((key) => {
    lookup[normalizeText(key)] = item[key];
  });

  for (const alias of aliases) {
    const value = lookup[normalizeText(alias)];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return value;
    }
  }

  return fallback;
}

function parseSpecsMap(specs: string): Record<string, string> {
  const map: Record<string, string> = {};
  const parts = String(specs || "").split(/[|\n;]+/);

  parts.forEach((part) => {
    const clean = String(part || "").trim();
    if (!clean) return;

    const match = clean.match(/^([^:=-]+)\s*[:=-]\s*(.+)$/);
    if (!match) return;

    const key = normalizeText(match[1]);
    const value = String(match[2] || "").trim();
    if (key && value) {
      map[key] = value;
    }
  });

  return map;
}

function getSpecValue(specMap: Record<string, string>, aliases: string[]): string {
  const keys = Object.keys(specMap || {});
  for (const alias of aliases) {
    const aliasKey = normalizeText(alias);
    if (!aliasKey) continue;

    if (specMap[aliasKey]) {
      return String(specMap[aliasKey]).trim();
    }

    const partialKey = keys.find((key) => key.includes(aliasKey) || aliasKey.includes(key));
    if (partialKey && specMap[partialKey]) {
      return String(specMap[partialKey]).trim();
    }
  }
  return "";
}

function getRegexValue(text: string, patterns: RegExp[]): string {
  const source = String(text || "");
  for (const pattern of patterns) {
    const match = source.match(pattern);
    if (match && match[0]) {
      return String(match[0]).replace(/\s+/g, " ").trim();
    }
  }
  return "";
}

function resolveTemplateValue(
  item: ProductRecord,
  specMap: Record<string, string>,
  itemAliases: string[],
  specAliases: string[] = []
): string {
  const direct = String(getField(item, itemAliases, "")).trim();
  if (direct) return direct;

  const fromSpecs = getSpecValue(specMap, specAliases);
  if (fromSpecs) return fromSpecs;

  return "";
}

function buildSiteDescription(
  item: ProductRecord,
  category: string,
  specs: string,
  fallbackDescription: string
): string {
  const specMap = parseSpecsMap(specs);
  const specsText = String(specs || "");

  const tecnologia = resolveTemplateValue(
    item,
    specMap,
    ["Tecnologia", "Technology", "Tecnologia LED", "Tipo de Lampada"],
    ["tecnologia", "tecnologia led", "tipo de lampada", "tipo de led"]
  );
  const caracteristica = resolveTemplateValue(
    item,
    specMap,
    ["Caracteristica", "Caracteristica Principal", "Feature"],
    ["caracteristica", "caracteristica principal"]
  );
  const potencia =
    resolveTemplateValue(
      item,
      specMap,
      ["Potência", "Potência (W)", "Power", "Watt", "Watts"],
      ["potencia", "potencia (w)", "power", "watt", "watts"]
    ) || getRegexValue(specsText, [/\b\d+(?:[.,]\d+)?\s*w\b/i]);
  const temperatura =
    resolveTemplateValue(
      item,
      specMap,
      ["Temperatura", "Temperatura de Cor", "CCT", "Kelvin"],
      ["temperatura", "temperatura de cor", "cct", "kelvin"]
    ) || getRegexValue(specsText, [/\b\d{3,5}\s*k\b/i]);
  const fluxoOuEficiencia =
    resolveTemplateValue(
      item,
      specMap,
      ["Fluxo Luminoso", "Eficiencia Luminosa", "Lumen", "Lumens", "lm/W"],
      ["fluxo luminoso", "eficiencia luminosa", "lumen", "lumens", "lm/w"]
    ) ||
    getRegexValue(specsText, [/\b\d+(?:[.,]\d+)?\s*lm\/w\b/i, /\b\d+(?:[.,]\d+)?\s*lm\b/i]);
  const indiceProtecao =
    resolveTemplateValue(
      item,
      specMap,
      ["Indice de Protecao", "IP", "Grau de Protecao"],
      ["indice de protecao", "ip", "grau de protecao"]
    ) || getRegexValue(specsText, [/\bip\s*\d{2}\b/i]).toUpperCase();
  const cor = resolveTemplateValue(item, specMap, ["Cor", "Color", "Acabamento"], ["cor", "acabamento"]);
  const formato = resolveTemplateValue(item, specMap, ["Formato", "Shape", "Modelo"], ["formato", "modelo"]);
  const material = resolveTemplateValue(item, specMap, ["Material", "Materia Prima"], ["material", "materia prima"]);

  const parts = [
    String(category || "").trim(),
    tecnologia,
    caracteristica,
    potencia,
    temperatura,
    fluxoOuEficiencia,
    indiceProtecao,
    cor,
    formato,
    material,
  ].filter((value) => String(value || "").trim() !== "");

  if (parts.length < 2) {
    return String(fallbackDescription || "").trim();
  }
  return parts.join(" + ");
}

function toRouteSlug(value: string, fallback: string): string {
  const normalized = normalizeText(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return normalized || fallback;
}

function resolveProductBrandCode(item: ProductRecord): string {
  return String(getField(item, ["CODMARCA", "CodMarca", "codmarca"], "1")).trim() || "1";
}

function resolveProductBrand(code: string): CatalogBrand {
  const normalizedCode = String(code || "").trim();
  return normalizedCode === "2" || normalizedCode === "2.0" ? "pienza" : "nitrolux";
}

function resolveProductBrandLabel(brand: CatalogBrand): string {
  return brand === "pienza" ? "Pienza" : "Nitrolux";
}

const BASE_PRODUCT_FIELD_KEYS = new Set(
  [
    "codigo",
    "code",
    "sku",
    "id",
    "nome",
    "produto",
    "name",
    "descricao",
    "description",
    "resumo",
    "categoria",
    "category",
    "tipo",
    "especificacoes",
    "especificacao",
    "specs",
    "detalhes",
    "fotobranco",
    "white_background",
    "whitebackground",
    "fotoambient",
    "ambient",
    "fotomedidas",
    "measures",
    "urlfoto",
    "imagem",
    "image",
    "foto",
    "url",
    "codmarca",
    "vendames",
    "venda mes",
    "vendames1",
    "venda mes 1",
    "vendames2",
    "venda mes 2",
    "vendames3",
    "venda mes 3",
  ].map((value) => normalizeText(value))
);

function renderAttributeValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function collectExtraAttributes(item: ProductRecord): ProductAttribute[] {
  const attributes: ProductAttribute[] = [];

  for (const [key, rawValue] of Object.entries(item || {})) {
    if (BASE_PRODUCT_FIELD_KEYS.has(normalizeText(key))) {
      continue;
    }
    const rendered = renderAttributeValue(rawValue);
    if (!rendered) {
      continue;
    }
    attributes.push({
      label: key,
      value: rendered,
    });
  }

  return attributes;
}

export function normalizeProduct(item: ProductRecord, index: number): CatalogProduct {
  const code = String(getField(item, ["Codigo", "Code", "SKU", "id"], index + 1));
  const brandCode = resolveProductBrandCode(item);
  const brand = resolveProductBrand(brandCode);
  const category = String(getField(item, ["Categoria", "Category", "Tipo"], "Sem categoria"));
  const fallbackDescription = String(getField(item, ["Descricao", "Description", "Resumo"], ""));
  const specs = String(getField(item, ["Especificacoes", "Especificacao", "Specs", "Detalhes"], ""));
  const monthlySales = parseNumericValue(getField(item, ["VendaMes", "VENDA MÊS", "Venda Mes"], 0));

  const composedDescription = buildSiteDescription(item, category, specs, fallbackDescription);

  const embeddedPhotos: ProductPhotos = {
    white_background: normalizePhotoReference(
      getField(item, ["FotoBranco", "white_background", "WhiteBackground"], "")
    ),
    ambient: normalizePhotoReference(getField(item, ["FotoAmbient", "ambient", "Ambient"], "")),
    measures: normalizePhotoReference(getField(item, ["FotoMedidas", "measures", "Measures"], "")),
  };

  const hasEmbeddedPhotos = hasAnyPhoto(embeddedPhotos);
  const rawCover = normalizePhotoReference(getField(item, ["URLFoto", "Imagem", "Image", "Foto", "URL"], ""));
  const id = `item-${index + 1}`;

  return {
    id,
    routeId: toRouteSlug(code, id),
    code,
    name: String(getField(item, ["Nome", "Produto", "Name"], `Produto ${index + 1}`)),
    brand,
    brandCode,
    brandLabel: resolveProductBrandLabel(brand),
    description: composedDescription,
    category,
    cover: getPrimaryProductImage(embeddedPhotos, rawCover),
    specs,
    photos: hasEmbeddedPhotos ? embeddedPhotos : null,
    monthlySales,
    attributes: collectExtraAttributes(item),
  };
}

export function hasAnyPhoto(photos: ProductPhotos | null | undefined): photos is ProductPhotos {
  return Boolean(photos && (photos.white_background || photos.ambient || photos.measures));
}

export function fallbackPhotos(code: string): ProductPhotos {
  return {
    white_background: createPlaceholderDataUrl(`Branco ${code}`, 240, 240),
    ambient: createPlaceholderDataUrl(`Ambient ${code}`, 240, 240),
    measures: createPlaceholderDataUrl(`Medidas ${code}`, 240, 240),
  };
}

function imageOrderKey(name: string): Array<number | string> {
  const value = String(name || "").toLowerCase();
  const visualRank = getVisualPreferenceRank(value);
  if (visualRank < 7) {
    return [visualRank, value];
  }
  if (/^\d+\s*-\s*[^\d]/.test(value)) {
    return [4, value];
  }

  const variantMatch = value.match(/^(\d+)(?:\s*[-_]\s*([1-4]))?\./);
  if (variantMatch) {
    const variant = variantMatch[2] ? Number(variantMatch[2]) : 0;
    return [5, variant, value];
  }

  return [6, value];
}

export function findPreferredGalleryIndex(entries: GalleryEntry[]): number {
  let bestIndex = 0;
  let bestRank = Number.MAX_SAFE_INTEGER;

  entries.forEach((entry, index) => {
    const rank = getVisualPreferenceRank(`${entry.label} ${entry.key} ${entry.url}`);
    if (rank < bestRank) {
      bestRank = rank;
      bestIndex = index;
    }
  });

  return bestIndex;
}

export function buildGalleryEntries(
  item: CatalogProduct,
  photos: ProductPhotos | null | undefined,
  apiImages: GalleryApiImage[]
): GalleryEntry[] {
  if (Array.isArray(apiImages) && apiImages.length > 0) {
    const ordered = apiImages.slice().sort((left, right) => {
      const a = imageOrderKey(left?.name || "");
      const b = imageOrderKey(right?.name || "");

      for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
        const av = a[i];
        const bv = b[i];
        if (av === undefined) return -1;
        if (bv === undefined) return 1;
        if (av < bv) return -1;
        if (av > bv) return 1;
      }
      return 0;
    });

    return ordered
      .filter((image) => typeof image?.url === "string" && image.url.length > 0)
      .map((image, index) => ({
        key: `${image.name || "img"}-${index}`,
        label: image.name || `Imagem ${index + 1}`,
        url: absolutizeApiUrl(String(image.url || "")),
      }));
  }

  const candidates = [
    { label: "Fundo branco", url: photos?.white_background || "" },
    { label: "Medidas", url: photos?.measures || "" },
    { label: "Ambientada", url: photos?.ambient || "" },
    { label: "Capa", url: item.cover },
  ];

  const seen = new Set<string>();
  const entries: GalleryEntry[] = [];

  for (const candidate of candidates) {
    const url = candidate.url || "";
    if (!url || seen.has(url)) continue;
    seen.add(url);
    entries.push({
      key: `${candidate.label}-${entries.length}`,
      label: candidate.label,
      url,
    });
  }

  if (entries.length === 0) {
    entries.push({
      key: "sem-imagem",
      label: "Sem imagem",
      url: DETAIL_FALLBACK_IMAGE,
    });
  }

  return entries;
}
