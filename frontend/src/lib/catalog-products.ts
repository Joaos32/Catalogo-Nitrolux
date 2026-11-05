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

export function normalizeProductCode(value: unknown): string {
  if (
    value === null ||
    value === undefined ||
    typeof value === "boolean" ||
    (typeof value === "number" && !Number.isFinite(value))
  )
    return "";
  const code = String(value).trim();
  return /^\d+\.0+$/.test(code) ? code.replace(/\.0+$/, "") : code;
}

export function deduplicateProducts(products: ProductRecord[]): ProductRecord[] {
  const result: ProductRecord[] = [];
  const byCode = new Map<string, ProductRecord>();
  const photoFields = new Set([
    "urlfoto",
    "fotobranco",
    "fotoambient",
    "fotomedidas",
    "image",
    "imagem",
    "foto",
    "url",
  ]);
  const missing = (value: unknown, key: string): boolean =>
    value === undefined ||
    value === null ||
    (typeof value === "string" &&
      (!value.trim() ||
        (photoFields.has(key.toLowerCase().replace(/_/g, "")) &&
          /placehold\.co|^data:image\/svg\+xml/i.test(value)))) ||
    (Array.isArray(value) && value.length === 0) ||
    (typeof value === "object" &&
      value !== null &&
      !Array.isArray(value) &&
      Object.keys(value).length === 0);
  for (const product of products) {
    const fields = Object.fromEntries(
      Object.entries(product).map(([key, value]) => [key.toLowerCase().replace(/_/g, ""), value])
    );
    const code =
      ["codigo", "code", "codprod", "sku", "id"]
        .map((key) => normalizeProductCode(fields[key]))
        .find(Boolean) || "";
    const existing = code ? byCode.get(code) : undefined;
    if (!existing) {
      const kept = code ? { ...product, Codigo: code } : { ...product };
      result.push(kept);
      if (code) byCode.set(code, kept);
      continue;
    }
    for (const [key, value] of Object.entries(product)) {
      if (missing(existing[key], key) && !missing(value, key)) existing[key] = value;
    }
  }
  return result;
}

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

export function isPromotionalImage(value: string): boolean {
  let reference = String(value || "");
  try {
    reference = decodeURIComponent(reference);
  } catch {
    /* Keep malformed URL references readable without rejecting other photos. */
  }
  return /(?:^|[\s/\\?=&_-])(?:flayer|flyer|banner|promocional|divulgacao|divulgação)(?=$|[\s/\\?=&_.-])/i.test(
    reference
  );
}

export function getPrimaryProductImage(
  photos: ProductPhotos | null | undefined,
  cover = ""
): string {
  return getProductImageCandidates(photos, cover)[0] || "";
}

export function getProductImageCandidates(
  photos: ProductPhotos | null | undefined,
  cover = ""
): string[] {
  const candidates = Array.from(
    new Set(
      [photos?.white_background, cover, photos?.ambient, photos?.measures]
        .map(normalizePhotoReference)
        .filter(Boolean)
    )
  );
  return [
    ...candidates.filter((url) => !isPromotionalImage(url)),
    ...candidates.filter(isPromotionalImage),
  ];
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
    url.toLowerCase().startsWith("data:image/svg+xml") ||
    marker.includes("placehold.co") ||
    marker.includes("placeholder") ||
    marker.includes("sem foto") ||
    marker.includes("sem imagem")
  ) {
    return "";
  }

  return url;
}

export function getRandomShowcaseProducts(
  products: CatalogProduct[],
  limit: number
): CatalogProduct[] {
  const safeLimit = Math.max(limit, 0);
  const randomized = products.slice();

  for (let index = randomized.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [randomized[index], randomized[randomIndex]] = [randomized[randomIndex], randomized[index]];
  }

  return randomized.slice(0, safeLimit);
}

const EMPTY_PRODUCT_VALUES = new Set([
  "n/a",
  "n/d",
  "null",
  "undefined",
  "[]",
  "{}",
  "nao informado",
  "nao informada",
  "nao preenchido",
  "nao preenchida",
  "sem informacao",
  "sem categoria",
]);

/** Keep real values such as zero and false; hide empty catalog markers. */
export function hasProductValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  const text = String(value).trim();
  return (
    text !== "" &&
    !/^[-‐‑‒–—−*_./\\\s]+$/.test(text) &&
    !EMPTY_PRODUCT_VALUES.has(normalizeText(text))
  );
}

function getField(
  item: ProductRecord | null | undefined,
  aliases: string[],
  fallback: unknown = ""
): unknown {
  if (!item || typeof item !== "object") return fallback;

  const lookup: Record<string, unknown> = {};
  Object.keys(item).forEach((key) => {
    lookup[normalizeText(key)] = item[key];
  });

  for (const alias of aliases) {
    const value = lookup[normalizeText(alias)];
    if (hasProductValue(value)) {
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
    if (key && hasProductValue(value)) {
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

    // Short labels such as "cor" and "IP" must not match another field's name.
    const partialKey =
      aliasKey.length > 3
        ? keys.find((key) => key.includes(aliasKey) || aliasKey.includes(key))
        : undefined;
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
  if (hasProductValue(direct)) return direct;

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
    ) || getRegexValue(specsText, [/\b\d+(?:[.,]\d+)?\s*lm\/w\b/i, /\b\d+(?:[.,]\d+)?\s*lm\b/i]);
  const indiceProtecao =
    resolveTemplateValue(
      item,
      specMap,
      ["Indice de Protecao", "IP", "Grau de Protecao"],
      ["indice de protecao", "ip", "grau de protecao"]
    ) || getRegexValue(specsText, [/\bip\s*\d{2}\b/i]).toUpperCase();
  const cor = resolveTemplateValue(
    item,
    specMap,
    ["Cor", "Color", "Acabamento"],
    ["cor", "acabamento"]
  );
  const formato = resolveTemplateValue(
    item,
    specMap,
    ["Formato", "Shape", "Modelo"],
    ["formato", "modelo"]
  );
  const material = resolveTemplateValue(
    item,
    specMap,
    ["Material", "Materia Prima"],
    ["material", "materia prima"]
  );

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
  ]
    .map((value) => String(value || "").trim())
    .filter(
      (value, index, values) =>
        hasProductValue(value) &&
        values.findIndex(
          (candidate) =>
            normalizeText(candidate).replace(/\s/g, "") === normalizeText(value).replace(/\s/g, "")
        ) === index
    );

  if (parts.length < 2) {
    return hasProductValue(fallbackDescription) ? fallbackDescription.trim() : "";
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
    "codprod",
    "codigo produto",
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
    "informacoestecnicas",
    "informacoes tecnicas",
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
  ].map(normalizeFieldKey)
);

function normalizeFieldKey(value: string): string {
  return normalizeText(value).replace(/[^a-z0-9]/g, "");
}

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
    if (BASE_PRODUCT_FIELD_KEYS.has(normalizeFieldKey(key))) {
      continue;
    }
    const rendered = renderAttributeValue(rawValue);
    if (!hasProductValue(rendered)) {
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
  const code = normalizeProductCode(
    getField(item, ["Codigo", "Code", "CODPROD", "SKU", "id"], index + 1)
  );
  const brandCode = resolveProductBrandCode(item);
  const brand = resolveProductBrand(brandCode);
  const category = String(getField(item, ["Categoria", "Category", "Tipo"], "Sem categoria"));
  const fallbackDescription = String(getField(item, ["Descricao", "Description", "Resumo"], ""));
  const specs = String(
    getField(
      item,
      [
        "Especificacoes",
        "Especificacao",
        "Specs",
        "Detalhes",
        "INFORMACOESTECNICAS",
        "Informações técnicas",
      ],
      ""
    )
  );
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
  const rawCover = normalizePhotoReference(
    getField(item, ["URLFoto", "Imagem", "Image", "Foto", "URL"], "")
  );
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

export function findPreferredGalleryIndex(entries: GalleryEntry[], preferredUrl = ""): number {
  const preferred = normalizePhotoReference(preferredUrl);
  const matchingIndex = preferred
    ? entries.findIndex((entry) => normalizePhotoReference(entry.url) === preferred)
    : -1;
  const hasProductPhoto = entries.some((entry) => !isPromotionalImage(entry.url));
  if (matchingIndex >= 0 && (!hasProductPhoto || !isPromotionalImage(entries[matchingIndex].url)))
    return matchingIndex;
  let bestIndex = 0;
  let bestRank = Number.MAX_SAFE_INTEGER;

  entries.forEach((entry, index) => {
    if (hasProductPhoto && isPromotionalImage(entry.url)) return;
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
  const ordered = (apiImages || [])
    .filter((image) => typeof image?.url === "string" && image.url.length > 0)
    .slice()
    .sort((left, right) => {
      const a = imageOrderKey(left.name || "");
      const b = imageOrderKey(right.name || "");
      for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
        if (a[index] === undefined) return -1;
        if (b[index] === undefined) return 1;
        if (a[index] < b[index]) return -1;
        if (a[index] > b[index]) return 1;
      }
      return 0;
    });
  const candidates = [
    ...ordered.map((image) => image.url),
    photos?.white_background,
    photos?.measures,
    photos?.ambient,
    item.cover,
  ];
  const seen = new Set<string>();
  const entries: GalleryEntry[] = [];
  for (const candidate of candidates) {
    const url = normalizePhotoReference(candidate);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    const label = isPromotionalImage(url)
      ? `Divulgação ${entries.length + 1}`
      : `Foto ${entries.length + 1}`;
    entries.push({ key: url, label, url });
  }
  return entries.length
    ? entries
    : [{ key: "sem-imagem", label: "Sem imagem", url: DETAIL_FALLBACK_IMAGE }];
}

const TECHNICAL_LABELS: Record<string, string> = {
  codigo: "Código",
  referencia: "Referência",
  dimensoes: "Dimensões",
  potencia: "Potência",
  tensao: "Tensão",
  fluxoluminoso: "Fluxo luminoso",
  tempdecork: "Temperatura de cor",
  temperaturadecor: "Temperatura de cor",
  temperaturadecork: "Temperatura de cor",
  irc: "IRC",
  material: "Material",
  garantia: "Garantia",
  bateria: "Bateria",
  interruptor: "Interruptor",
  ip: "Proteção IP",
  cor: "Cor",
  acabamento: "Acabamento",
};

export function getTechnicalPresentation(
  specs: string,
  code: string
): { attributes: ProductAttribute[]; notes: string[] } {
  const attributes: ProductAttribute[] = [];
  const notes: string[] = [];
  const seen = new Set<string>();
  for (const segment of String(specs || "").split(/[|;\\\r\n]+/)) {
    const text = segment.trim();
    if (!hasProductValue(text)) continue;
    const match = text.match(/^([^:]{1,80}):\s*(.*)$/);
    if (!match) {
      if (!notes.includes(text)) notes.push(text);
      continue;
    }
    const field = normalizeFieldKey(match[1]);
    const value = match[2].trim();
    if (!hasProductValue(value)) continue;
    if (["codigo", "codprod", "referencia"].includes(field) && value === code) continue;
    const label = TECHNICAL_LABELS[field] || match[1].trim();
    const key = `${normalizeText(label)}:${normalizeText(value)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    attributes.push({ label, value });
  }
  return { attributes, notes };
}
