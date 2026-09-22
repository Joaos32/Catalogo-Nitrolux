import { API_BASES, REQUEST_TIMEOUT_MS } from "./catalog-core";
import type {
  CatalogExportOptions,
  ErpFileRecord,
  ErpFilePreview,
  ErpImportSummary,
  ErpProductsResponse,
  ErpProductSaveSummary,
  ErpStageFileSummary,
  ErpStatusResponse,
  AdminSessionStatus,
  RepresentativeAuthResponse,
  RepresentativeAdminDeleteResponse,
  RepresentativeAdminListResponse,
  RepresentativeAdminSavePayload,
  RepresentativeAdminSaveResponse,
  RepresentativePasswordResetCompleteResponse,
  RepresentativePasswordResetResponse,
  RepresentativeSessionStatus,
  ProductImagesResponse,
  ProductPhotos,
  ProductRecord,
} from "../types";

let activeApiOrigin: string | null = null;

export class ApiRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function resolveBaseOrigin(base: string): string {
  if (!base) return window.location.origin;
  return new URL(base, window.location.origin).origin;
}

export function getActiveApiOrigin(): string {
  return activeApiOrigin || window.location.origin;
}

export function absolutizeApiUrl(value: string): string {
  const url = String(value || "").trim();
  if (!url) return "";
  if (/^(https?:)?\/\//i.test(url) || url.startsWith("data:") || url.startsWith("blob:")) {
    return url;
  }
  if (url.startsWith("/")) {
    return new URL(url, getActiveApiOrigin()).toString();
  }
  return url;
}

export type CatalogImageSize = "thumb" | "card" | "detail";

export function optimizeCatalogImageUrl(value: string | null | undefined, size: CatalogImageSize): string {
  const url = absolutizeApiUrl(String(value || ""));
  if (!url) return "";

  try {
    const parsed = new URL(url, window.location.origin);
    const sizeWidths: Record<CatalogImageSize, number> = { thumb: 320, card: 640, detail: 1000 };
    const isCatalogProxy = parsed.pathname.includes("/catalog/media/google-drive/");
    const isDriveThumbnail =
      parsed.hostname.toLowerCase() === "drive.google.com" && parsed.pathname === "/thumbnail";

    if (!isCatalogProxy && !isDriveThumbnail) {
      return url;
    }
    parsed.searchParams.set(isCatalogProxy ? "size" : "sz", isCatalogProxy ? size : `w${sizeWidths[size]}`);
    return parsed.toString();
  } catch {
    return url;
  }
}

export function buildCatalogExportUrl(options: CatalogExportOptions): string {
  return buildCatalogExportUrlForBase(getActiveApiOrigin(), options);
}

function buildCatalogExportUrlForBase(baseOrigin: string, options: CatalogExportOptions): string {
  const url = new URL("/catalog/export", baseOrigin);
  url.searchParams.set("format", options.format);

  const query = String(options.query || "").trim();
  const category = String(options.category || "").trim();
  const code = String(options.code || "").trim();
  const brand = String(options.brand || "").trim();

  if (query) url.searchParams.set("query", query);
  if (category) url.searchParams.set("category", category);
  if (code) url.searchParams.set("code", code);
  if (brand) url.searchParams.set("brand", brand);

  return url.toString();
}

function parseDownloadFilename(response: Response, fallbackName: string): string {
  const header = response.headers.get("content-disposition") || "";
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }

  const plainMatch = header.match(/filename="([^"]+)"/i) || header.match(/filename=([^;]+)/i);
  if (plainMatch?.[1]) {
    return plainMatch[1].trim().replace(/^"|"$/g, "");
  }

  return fallbackName;
}

function fallbackExportFilename(options: CatalogExportOptions): string {
  const suffix = options.format;
  if (options.code) return `produto-${options.code}.${suffix}`;
  return `catalogo-produtos.${suffix}`;
}

function sanitizeDownloadName(value: string, fallback: string): string {
  const normalized = String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || fallback;
}

function inferExtensionFromUrl(url: string, blobType = ""): string {
  try {
    const parsed = new URL(url, window.location.origin);
    const pathname = parsed.pathname || "";
    const match = pathname.match(/\.([a-zA-Z0-9]{2,5})$/);
    if (match?.[1]) {
      return `.${match[1].toLowerCase()}`;
    }
  } catch {
    // ignora URL invalida e aplica fallback por tipo MIME
  }

  const mimeMap: Record<string, string> = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tif",
  };
  return mimeMap[blobType] || ".jpg";
}

function triggerBrowserDownload(url: string, filename: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export async function downloadCatalogExport(options: CatalogExportOptions): Promise<void> {
  let lastError: unknown = null;

  for (const base of API_BASES) {
    const targetUrl = buildCatalogExportUrlForBase(resolveBaseOrigin(base), options);

    try {
      const response = await fetchWithTimeout(targetUrl, { credentials: "include" });
      if (!response.ok) {
        lastError = new Error(`Resposta não-ok para ${targetUrl}: ${response.status}`);
        continue;
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = parseDownloadFilename(response, fallbackExportFilename(options));
      link.rel = "noopener";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      activeApiOrigin = resolveBaseOrigin(base);
      return;
    } catch (error) {
      lastError = error;
      console.warn(`Falha ao baixar exportação em ${targetUrl}. Tentando próxima base.`);
    }
  }

  console.error("Todas as bases falharam na exportação do catálogo.", lastError);
  throw lastError instanceof Error ? lastError : new Error("Não foi possível exportar o catálogo.");
}

export async function downloadImageFile(url: string, filenameBase: string): Promise<void> {
  const targetUrl = absolutizeApiUrl(url);
  const safeBase = sanitizeDownloadName(filenameBase, "imagem-produto");

  try {
    const response = await fetchWithTimeout(targetUrl);
    if (!response.ok) {
      throw new Error(`Resposta não-ok para ${targetUrl}: ${response.status}`);
    }

    const blob = await response.blob();
    const extension = inferExtensionFromUrl(targetUrl, blob.type);
    const objectUrl = URL.createObjectURL(blob);
    triggerBrowserDownload(objectUrl, `${safeBase}${extension}`);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (error) {
    console.warn(`Falha ao baixar imagem em ${targetUrl}. Abrindo fallback do navegador.`, error);
    const extension = inferExtensionFromUrl(targetUrl);
    triggerBrowserDownload(targetUrl, `${safeBase}${extension}`);
  }
}

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    return await fetch(url, { ...(init || {}), signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  const fallback = `Resposta não-ok: ${response.status}`;

  try {
    const payload = (await response.json()) as unknown;
    if (!isRecord(payload)) return fallback;

    if (typeof payload.error === "string" && payload.error.trim()) {
      return payload.error.trim();
    }
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
    return fallback;
  } catch {
    try {
      const text = await response.text();
      return text.trim() || fallback;
    } catch {
      return fallback;
    }
  }
}

function withAdminHeaders(headers?: HeadersInit, adminToken?: string): Headers {
  const merged = new Headers(headers || {});
  const token = String(adminToken || "").trim();
  if (token) {
    merged.set("X-Catalog-Admin-Token", token);
  }
  return merged;
}

async function requestJsonFromBases<T>(buildUrl: (base: string) => string, init?: RequestInit): Promise<T> {
  let lastError: unknown = null;

  for (const base of API_BASES) {
    const targetUrl = buildUrl(base);
    try {
      const response = await fetchWithTimeout(targetUrl, init);
      if (!response.ok) {
        const message = await parseErrorMessage(response);
        const error = new ApiRequestError(response.status, message);
        if (response.status !== 404 && response.status < 500) {
          throw error;
        }
        lastError = error;
        console.warn(`Resposta não-ok para ${targetUrl}: ${response.status} ${message}`);
        continue;
      }

      const payload = (await response.json()) as T;
      activeApiOrigin = resolveBaseOrigin(base);
      return payload;
    } catch (error) {
      if (error instanceof ApiRequestError) {
        if (error.status !== 404 && error.status < 500) {
          throw error;
        }
      }
      lastError = error;
      console.warn(`Falha ao consultar ${targetUrl}. Tentando próxima base.`);
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Não foi possível concluir a requisição.");
}

export async function fetchFromBases<T>(
  buildUrl: (base: string) => string,
  init?: RequestInit
): Promise<T | null> {
  let lastError: unknown = null;

  for (const base of API_BASES) {
    const targetUrl = buildUrl(base);
    try {
      const response = await fetchWithTimeout(targetUrl, init);
      if (!response.ok) {
        if (response.status !== 404) {
          console.warn(`Resposta não-ok para ${targetUrl}: ${response.status}`);
        }
        continue;
      }
      const payload = (await response.json()) as T;
      activeApiOrigin = resolveBaseOrigin(base);
      return payload;
    } catch (error) {
      lastError = error;
      console.warn(`Falha ao consultar ${targetUrl}. Tentando próxima base.`);
    }
  }

  if (lastError) {
    console.error("Todas as bases falharam na consulta da API.", lastError);
  }
  return null;
}

export async function postJsonToBases<T>(
  buildUrl: (base: string) => string,
  payload: unknown
): Promise<T | null> {
  let lastError: unknown = null;

  for (const base of API_BASES) {
    const targetUrl = buildUrl(base);
    try {
      const response = await fetchWithTimeout(targetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const details = await response.text();
        console.warn(`Resposta não-ok para ${targetUrl}: ${response.status} ${details}`);
        continue;
      }
      const parsed = (await response.json()) as T;
      activeApiOrigin = resolveBaseOrigin(base);
      return parsed;
    } catch (error) {
      lastError = error;
      console.warn(`Falha ao enviar dados para ${targetUrl}. Tentando próxima base.`);
    }
  }

  if (lastError) {
    console.error("Todas as bases falharam no envio para a API.", lastError);
  }
  return null;
}

function normalizePhotos(payload: unknown): ProductPhotos | null {
  if (!isRecord(payload)) return null;
  const whiteBackground = payload.white_background;
  const ambient = payload.ambient;
  const measures = payload.measures;

  if (
    typeof whiteBackground !== "string" &&
    typeof ambient !== "string" &&
    typeof measures !== "string"
  ) {
    return null;
  }

  return {
    white_background: typeof whiteBackground === "string" ? whiteBackground : null,
    ambient: typeof ambient === "string" ? ambient : null,
    measures: typeof measures === "string" ? measures : null,
  };
}

export async function fetchProducts(): Promise<ProductRecord[]> {
  const payload = await fetchFromBases<unknown>((base) => `${base}/catalog/local/produtos`, {
    credentials: "include",
  });
  return Array.isArray(payload) ? (payload as ProductRecord[]) : [];
}

export async function fetchPhotosByCode(code: string): Promise<ProductPhotos | null> {
  const payload = await fetchFromBases<unknown>(
    (base) => `${base}/catalog/photos?code=${encodeURIComponent(code)}`,
    {
      credentials: "include",
    }
  );
  return normalizePhotos(payload);
}

export async function fetchPhotosByCodes(codes: string[]): Promise<Record<string, ProductPhotos | null>> {
  const normalizedCodes = Array.from(new Set(codes.map((code) => String(code || "").trim()).filter(Boolean)));
  if (normalizedCodes.length === 0) return {};

  const payload = await fetchFromBases<unknown>(
    (base) => `${base}/catalog/photos/batch?codes=${encodeURIComponent(normalizedCodes.join(","))}`,
    { credentials: "include" }
  );
  if (!isRecord(payload)) return {};

  return Object.fromEntries(
    Object.entries(payload).map(([code, value]) => [code, normalizePhotos(value)] as const)
  );
}

export async function fetchImagesByCode(code: string): Promise<ProductImagesResponse | null> {
  const payload = await fetchFromBases<unknown>(
    (base) => `${base}/catalog/produtos/${encodeURIComponent(code)}/imagens`,
    {
      credentials: "include",
    }
  );

  if (!isRecord(payload)) return null;
  const codigo = payload.codigo;
  const imagens = payload.imagens;
  if (typeof codigo !== "string" || !Array.isArray(imagens)) {
    return null;
  }

  return {
    codigo,
    imagens: imagens.filter((image) => isRecord(image)) as ProductImagesResponse["imagens"],
  };
}

export async function importErpCatalog(payload: unknown): Promise<ErpImportSummary | null> {
  return postJsonToBases<ErpImportSummary>((base) => `${base}/catalog/erp/import`, payload);
}

export async function fetchErpStatus(adminToken?: string): Promise<ErpStatusResponse> {
  return requestJsonFromBases<ErpStatusResponse>((base) => `${base}/catalog/erp/status`, {
    headers: withAdminHeaders(undefined, adminToken),
    credentials: "include",
  });
}

export async function fetchErpFiles(adminToken?: string): Promise<ErpFileRecord[]> {
  const payload = await requestJsonFromBases<{ files?: ErpFileRecord[] }>(
    (base) => `${base}/catalog/erp/files`,
    {
      headers: withAdminHeaders(undefined, adminToken),
      credentials: "include",
    }
  );
  return Array.isArray(payload.files) ? payload.files : [];
}

export async function fetchErpFilePreview(filePath: string, adminToken?: string): Promise<ErpFilePreview> {
  return requestJsonFromBases<ErpFilePreview>(
    (base) => `${base}/catalog/erp/files/preview?file_path=${encodeURIComponent(filePath)}`,
    {
      headers: withAdminHeaders(undefined, adminToken),
      credentials: "include",
    }
  );
}

export async function fetchErpProducts(adminToken?: string): Promise<ErpProductsResponse> {
  return requestJsonFromBases<ErpProductsResponse>((base) => `${base}/catalog/erp/products`, {
    headers: withAdminHeaders(undefined, adminToken),
    credentials: "include",
  });
}

export async function importErpFileFromPath(filePath: string, adminToken?: string): Promise<ErpImportSummary> {
  return requestJsonFromBases<ErpImportSummary>((base) => `${base}/catalog/erp/import-file`, {
    method: "POST",
    headers: withAdminHeaders({ "Content-Type": "application/json" }, adminToken),
    credentials: "include",
    body: JSON.stringify({ file_path: filePath }),
  });
}

export async function uploadErpJsonFile(file: File, adminToken?: string): Promise<ErpImportSummary> {
  const content = await file.arrayBuffer();
  return requestJsonFromBases<ErpImportSummary>(
    (base) => `${base}/catalog/erp/upload?filename=${encodeURIComponent(file.name || "erp_upload.json")}`,
    {
      method: "POST",
      headers: withAdminHeaders({ "Content-Type": file.type || "application/json" }, adminToken),
      credentials: "include",
      body: content,
    }
  );
}

export async function stageErpJsonFile(file: File, adminToken?: string): Promise<ErpStageFileSummary> {
  const content = await file.arrayBuffer();
  return requestJsonFromBases<ErpStageFileSummary>(
    (base) => `${base}/catalog/erp/stage-file?filename=${encodeURIComponent(file.name || "erp_upload.json")}`,
    {
      method: "POST",
      headers: withAdminHeaders({ "Content-Type": file.type || "application/json" }, adminToken),
      credentials: "include",
      body: content,
    }
  );
}

export async function saveErpProduct(
  code: string,
  payload: ProductRecord,
  adminToken?: string
): Promise<ErpProductSaveSummary> {
  return requestJsonFromBases<ErpProductSaveSummary>(
    (base) => `${base}/catalog/erp/products/${encodeURIComponent(code)}`,
    {
      method: "PUT",
      headers: withAdminHeaders({ "Content-Type": "application/json" }, adminToken),
      credentials: "include",
      body: JSON.stringify(payload),
    }
  );
}

export async function fetchAdminSession(): Promise<AdminSessionStatus> {
  return requestJsonFromBases<AdminSessionStatus>((base) => `${base}/auth/session`, {
    credentials: "include",
  });
}

export async function loginAdminWithPassword(email: string, password: string): Promise<AdminSessionStatus> {
  return requestJsonFromBases<AdminSessionStatus>((base) => `${base}/auth/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
}

export async function logoutAdminSession(): Promise<{ success: boolean; authenticated: boolean }> {
  return requestJsonFromBases<{ success: boolean; authenticated: boolean }>((base) => `${base}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function fetchRepresentativeUsers(adminToken?: string): Promise<RepresentativeAdminListResponse> {
  return requestJsonFromBases<RepresentativeAdminListResponse>((base) => `${base}/catalog/representatives`, {
    headers: withAdminHeaders(undefined, adminToken),
    credentials: "include",
  });
}

export async function saveRepresentativeUser(
  payload: RepresentativeAdminSavePayload,
  adminToken?: string
): Promise<RepresentativeAdminSaveResponse> {
  return requestJsonFromBases<RepresentativeAdminSaveResponse>(
    (base) => `${base}/catalog/representatives/${encodeURIComponent(payload.email)}`,
    {
      method: "PUT",
      headers: withAdminHeaders({ "Content-Type": "application/json" }, adminToken),
      credentials: "include",
      body: JSON.stringify(payload),
    }
  );
}

export async function deleteRepresentativeUser(
  email: string,
  adminToken?: string
): Promise<RepresentativeAdminDeleteResponse> {
  return requestJsonFromBases<RepresentativeAdminDeleteResponse>(
    (base) => `${base}/catalog/representatives/${encodeURIComponent(email)}`,
    {
      method: "DELETE",
      headers: withAdminHeaders(undefined, adminToken),
      credentials: "include",
    }
  );
}

export async function createRepresentativePasswordReset(
  email: string,
  adminToken?: string
): Promise<RepresentativePasswordResetResponse> {
  return requestJsonFromBases<RepresentativePasswordResetResponse>(
    (base) => `${base}/catalog/representatives/${encodeURIComponent(email)}/password-reset`,
    {
      method: "POST",
      headers: withAdminHeaders(undefined, adminToken),
      credentials: "include",
    }
  );
}

export async function fetchRepresentativeSession(): Promise<RepresentativeSessionStatus> {
  return requestJsonFromBases<RepresentativeSessionStatus>((base) => `${base}/auth/representative/session`, {
    credentials: "include",
  });
}

export async function loginRepresentative(
  email: string,
  password: string
): Promise<RepresentativeAuthResponse> {
  return requestJsonFromBases<RepresentativeAuthResponse>(
    (base) => `${base}/auth/representative/login`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    }
  );
}

export async function resetRepresentativePassword(
  email: string,
  resetCode: string,
  newPassword: string
): Promise<RepresentativePasswordResetCompleteResponse> {
  return requestJsonFromBases<RepresentativePasswordResetCompleteResponse>(
    (base) => `${base}/auth/representative/reset-password`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, reset_code: resetCode, new_password: newPassword }),
    }
  );
}

export async function logoutRepresentative(): Promise<{ success: boolean; authenticated: boolean }> {
  return requestJsonFromBases<{ success: boolean; authenticated: boolean }>(
    (base) => `${base}/auth/representative/logout`,
    {
      method: "POST",
      credentials: "include",
    }
  );
}
