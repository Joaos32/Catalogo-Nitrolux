export interface ProductPhotos {
  white_background?: string | null;
  ambient?: string | null;
  measures?: string | null;
}

export interface ProductRecord {
  [key: string]: unknown;
}

export interface ProductAttribute {
  label: string;
  value: string;
}

export type CatalogBrand = "nitrolux" | "pienza";

export interface CatalogProduct {
  id: string;
  routeId: string;
  code: string;
  name: string;
  brand: CatalogBrand;
  brandCode: string;
  brandLabel: string;
  description: string;
  category: string;
  cover: string;
  specs: string;
  photos: ProductPhotos | null;
  monthlySales: number;
  attributes: ProductAttribute[];
}

export interface GalleryApiImage {
  name?: string;
  url?: string;
  variant?: number;
}

export interface ProductImagesResponse {
  codigo: string;
  imagens: GalleryApiImage[];
}

export interface GalleryEntry {
  key: string;
  label: string;
  url: string;
}

export type CatalogExportFormat = "csv" | "xlsx" | "json" | "pdf" | "ficha" | "zip";

export interface CatalogExportOptions {
  format: CatalogExportFormat;
  query?: string;
  category?: string;
  code?: string;
  brand?: CatalogBrand;
}

export interface ErpImportSummary {
  path: string;
  products_imported: number;
  imported_at: string;
  products_loaded?: number;
  updated_at?: string;
  source_path?: string | null;
  source_name?: string | null;
  source_size_bytes?: number | null;
  source_updated_at?: string | null;
  last_change_summary?: ErpPreviewChangeSummary | null;
}

export interface ErpStatusResponse {
  path: string;
  exists: boolean;
  products_loaded: number;
  imported_at?: string | null;
  updated_at: string | null;
  source_path?: string | null;
  source_name?: string | null;
  source_size_bytes?: number | null;
  source_updated_at?: string | null;
  last_change_summary?: ErpPreviewChangeSummary | null;
}

export interface ErpFileRecord {
  path: string;
  name: string;
  size_bytes: number;
  updated_at: string;
  is_active: boolean;
  is_deployed_source?: boolean;
}

export interface ErpProductsResponse extends ErpStatusResponse {
  products: ProductRecord[];
}

export interface ErpProductSaveSummary extends ErpImportSummary {
  code: string;
  created: boolean;
  product: ProductRecord;
}

export interface ErpPreviewCategoryStat {
  name: string;
  count: number;
}

export interface ErpPreviewSampleProduct {
  Codigo: string;
  Nome: string;
  Categoria: string;
}

export type ErpPreviewChangeType = "added" | "updated" | "removed";

export interface ErpPreviewChangeRecord {
  change_type: ErpPreviewChangeType;
  code: string;
  name: string;
  category: string;
  previous_name?: string | null;
  previous_category?: string | null;
  changed_fields: string[];
}

export interface ErpPreviewChangeSummary {
  compared_to_path?: string | null;
  compared_to_name?: string | null;
  added_count: number;
  updated_count: number;
  removed_count: number;
  unchanged_count: number;
  changes: ErpPreviewChangeRecord[];
}

export interface ErpFilePreview {
  path: string;
  name: string;
  size_bytes: number;
  updated_at: string | null;
  is_active: boolean;
  is_deployed_source: boolean;
  products_loaded: number;
  records_detected: number;
  ignored_records: number;
  imported_at?: string | null;
  payload_updated_at?: string | null;
  categories: ErpPreviewCategoryStat[];
  sample_products: ErpPreviewSampleProduct[];
  change_summary?: ErpPreviewChangeSummary | null;
}

export interface ErpStageFileSummary extends ErpFilePreview {
  staged: boolean;
}

export interface AdminSessionStatus {
  authenticated: boolean;
  provider?: string | null;
  logged_in_at?: string | null;
  password_login_available: boolean;
  password_login_requires_email?: boolean;
  azure_login_available: boolean;
  protection_enabled: boolean;
}

export interface RepresentativeUser {
  email: string;
  name: string;
}

export interface RepresentativeAdminUser extends RepresentativeUser {
  managed: boolean;
  source: "managed" | "environment";
  is_admin: boolean;
  role: "admin" | "representative";
  created_at?: string | null;
  updated_at?: string | null;
  password_reset_expires_at?: string | null;
  password_reset_pending?: boolean;
}

export interface RepresentativeAdminListResponse {
  users: RepresentativeAdminUser[];
  total_users: number;
  managed_users: number;
  environment_users: number;
  admin_users: number;
  representative_users: number;
}

export interface RepresentativeAdminSavePayload {
  email: string;
  name: string;
  password?: string;
  is_admin?: boolean;
}

export interface RepresentativeAdminSaveResponse extends RepresentativeAdminListResponse {
  created: boolean;
  user: RepresentativeAdminUser;
}

export interface RepresentativeAdminDeleteResponse extends RepresentativeAdminListResponse {
  deleted: boolean;
  email: string;
}

export interface RepresentativePasswordResetResponse extends RepresentativeAdminListResponse {
  reset_code: string;
  expires_at: string;
  user: RepresentativeAdminUser;
}

export interface RepresentativeSessionStatus {
  authenticated: boolean;
  provider?: string | null;
  expires_at?: string | null;
  login_available: boolean;
  protection_enabled: boolean;
  user?: RepresentativeUser | null;
}

export interface RepresentativeAuthResponse extends RepresentativeSessionStatus {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RepresentativePasswordResetCompleteResponse {
  success: boolean;
  user: RepresentativeUser;
}
