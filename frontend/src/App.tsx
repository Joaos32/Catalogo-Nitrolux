import { useRepresentativeSession } from "./lib/use-representative-session";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useCatalogFilters } from "./lib/use-catalog-filters";
import { rememberCatalogPosition, useCatalogNavigation } from "./lib/use-catalog-navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import ExportActions from "./components/ExportActions";
import ProductCard from "./components/ProductCard";
import ProductDetail from "./components/ProductDetail";
import {
  ApiRequestError,
  downloadCatalogExport,
  fetchImagesByCode,
  fetchPhotosByCodes,
  fetchProducts,
  logoutRepresentative,
} from "./lib/catalog-api";
import {
  DEMO_PRODUCTS,
  deduplicateProducts,
  buildGalleryEntries,
  fallbackPhotos,
  normalizeProduct,
  normalizeText,
} from "./lib/catalog-products";
import { persistPhotosByCode, readPersistedPhotos } from "./lib/catalog-storage";
import { mergePhotoSources, mergePhotosByCode, type PhotosByCode } from "./lib/catalog-photo-cache";
import type { CatalogBrand, CatalogExportFormat, ProductPhotos } from "./types";

type PhotosByProductId = Record<string, ProductPhotos>;
const INITIAL_PRODUCTS_LIMIT = 15;
const BRAND_ORDER: CatalogBrand[] = ["nitrolux", "pienza"];

const BRAND_META: Record<
  CatalogBrand,
  {
    tabLabel: string;
    kicker: string;
    title: string;
    subtitle: string;
    pageClassName: string;
    heroClassName: string;
    resultLabel: string;
    exportTitle: string;
  }
> = {
  nitrolux: {
    tabLabel: "Nitrolux",
    kicker: "Catálogo de produtos",
    title: "NITROLUX",
    subtitle: "Sua vida com mais brilho",
    pageClassName: "brand-theme-nitrolux",
    heroClassName: "",
    resultLabel: "linha Nitrolux",
    exportTitle: "Baixar catálogo Nitrolux",
  },
  pienza: {
    tabLabel: "Pienza",
    kicker: "Coleção premium",
    title: "PIENZA",
    subtitle: "Pendentes, arandelas e luminárias decorativas",
    pageClassName: "brand-theme-pienza",
    heroClassName: "hero-premium",
    resultLabel: "coleção Pienza",
    exportTitle: "Baixar catálogo Pienza",
  },
};
function useCatalogProducts() {
  return useQuery({
    queryKey: ["catalog-products"],
    queryFn: fetchProducts,
    staleTime: 60_000,
    retry: (failureCount, error) => {
      if (error instanceof ApiRequestError && error.status < 500) return false;
      return failureCount < 2;
    },
  });
}

function getResponsiveProductsBatch(): number {
  if (typeof window === "undefined") return INITIAL_PRODUCTS_LIMIT;
  if (window.innerWidth <= 520) return 6;
  if (window.innerWidth <= 740) return 8;
  if (window.innerWidth <= 1024) return 12;
  return INITIAL_PRODUCTS_LIMIT;
}

function useResponsiveProductsBatch(): number {
  const [batchSize, setBatchSize] = useState(getResponsiveProductsBatch);

  useEffect(() => {
    const updateBatchSize = () => setBatchSize(getResponsiveProductsBatch());
    window.addEventListener("resize", updateBatchSize);
    return () => window.removeEventListener("resize", updateBatchSize);
  }, []);

  return batchSize;
}

export default function App(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { productId } = useParams<{ productId: string }>();
  const location = useLocation();
  const responsiveProductsBatch = useResponsiveProductsBatch();

  const { query, category, brand, limit, update, loadMore } =
    useCatalogFilters(responsiveProductsBatch);
  const [knownPhotosByCode, setKnownPhotosByCode] = useState(readPersistedPhotos);
  const [failedPhotoCodes, setFailedPhotoCodes] = useState<ReadonlySet<string>>(() => new Set());
  const refreshFailedPhoto = (code: string) => {
    setFailedPhotoCodes((previous) =>
      previous.has(code) ? previous : new Set([...previous, code])
    );
  };
  const [isLoggingOutRepresentative, setIsLoggingOutRepresentative] = useState(false);
  const [sessionError, setSessionError] = useState("");

  const productsQuery = useCatalogProducts();
  const representativeSessionQuery = useRepresentativeSession();

  const products = useMemo(() => {
    const source =
      productsQuery.data && productsQuery.data.length > 0 ? productsQuery.data : DEMO_PRODUCTS;
    return deduplicateProducts(source).map((item, index) => normalizeProduct(item, index));
  }, [productsQuery.data]);

  const selectedProduct = useMemo(() => {
    if (!productId) return null;
    return products.find((item) => item.routeId === productId) || null;
  }, [productId, products]);

  useEffect(() => {
    if (!productId || !productsQuery.isSuccess) return;
    if (!selectedProduct) {
      navigate(`/${location.search}`, { replace: true });
    }
  }, [navigate, productId, productsQuery.isSuccess, selectedProduct, location.search]);

  const galleryQuery = useQuery({
    queryKey: ["catalog-gallery", selectedProduct?.code || selectedProduct?.id || "none"],
    enabled: Boolean(selectedProduct),
    staleTime: 5 * 60_000,
    queryFn: async () => {
      if (!selectedProduct) return [];
      const code = selectedProduct.code || selectedProduct.id;
      const payload = await fetchImagesByCode(code);
      return payload && Array.isArray(payload.imagens) ? payload.imagens : [];
    },
  });

  const activeBrand = selectedProduct?.brand || brand;
  const brandMeta = BRAND_META[activeBrand];

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    document.body.classList.toggle("body-theme-pienza", activeBrand === "pienza");
    return () => {
      document.body.classList.remove("body-theme-pienza");
    };
  }, [activeBrand]);

  const brandCounts = useMemo(() => {
    const counts: Record<CatalogBrand, number> = { nitrolux: 0, pienza: 0 };
    for (const item of products) {
      counts[item.brand] += 1;
    }
    return counts;
  }, [products]);

  const brandProducts = useMemo(
    () => products.filter((item) => item.brand === brand),
    [brand, products]
  );

  const categories = useMemo(() => {
    const values = Array.from(
      new Set(brandProducts.map((item) => item.category).filter(Boolean))
    ).sort((a, b) => a.localeCompare(b));
    return ["Todas", ...values];
  }, [brandProducts]);

  useEffect(() => {
    if (category === "Todas" || !productsQuery.isSuccess) return;
    if (!categories.includes(category)) {
      update({ category: "Todas" }, true);
    }
  }, [category, categories, productsQuery.isSuccess, update]);

  const searchIndex = useMemo(
    () =>
      new Map(
        products.map((item) => [
          item.id,
          normalizeText(`${item.name} ${item.code} ${item.description} ${item.category}`),
        ])
      ),
    [products]
  );

  const filteredProducts = useMemo(() => {
    const search = normalizeText(query);

    return products.filter((item) => {
      if (item.brand !== brand) return false;
      const categoryOk = category === "Todas" || item.category === category;
      const textBlob = searchIndex.get(item.id) || "";
      const queryOk = !search || textBlob.includes(search);
      return categoryOk && queryOk;
    });
  }, [brand, category, products, query, searchIndex]);

  const visibleProducts = useMemo(
    () => filteredProducts.slice(0, limit),
    [filteredProducts, limit]
  );
  useCatalogNavigation(productId, productsQuery.isSuccess, location.search);

  useEffect(() => {
    document.title = selectedProduct
      ? `${selectedProduct.name} | ${brandMeta.tabLabel}`
      : `Catálogo ${brandMeta.tabLabel}`;
  }, [brandMeta.tabLabel, selectedProduct]);

  const photoTargets = useMemo(() => {
    if (productId && !galleryQuery.isError) {
      return [];
    }

    const targets = visibleProducts.filter(
      (item) =>
        failedPhotoCodes.has(item.code) ||
        !mergePhotoSources(item.photos, knownPhotosByCode[item.code])
    );
    if (
      selectedProduct &&
      (failedPhotoCodes.has(selectedProduct.code) ||
        !mergePhotoSources(selectedProduct.photos, knownPhotosByCode[selectedProduct.code])) &&
      !targets.some((item) => item.id === selectedProduct.id)
    ) {
      targets.push(selectedProduct);
    }
    return targets;
  }, [
    failedPhotoCodes,
    galleryQuery.isError,
    knownPhotosByCode,
    productId,
    selectedProduct,
    visibleProducts,
  ]);

  const photoQueryKey = useMemo(
    () =>
      [
        "catalog-photos",
        photoTargets
          .map((item) => item.code || item.id)
          .join("|")
          .toLowerCase(),
      ] as const,
    [photoTargets]
  );

  const photosQuery = useQuery({
    queryKey: photoQueryKey,
    enabled: photoTargets.length > 0,
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<PhotosByCode> => {
      const previousPhotos = queryClient.getQueryData<PhotosByCode>(photoQueryKey) || {};
      const remoteCodes = photoTargets.map((product) => product.code || product.id);
      // Uma falha de rede deve manter os dados anteriores no React Query.
      // Nao transforme indisponibilidade temporaria em placeholders.
      const remotePhotos = await fetchPhotosByCodes(remoteCodes);
      const entries = photoTargets.map((product) => {
        const code = product.code || product.id;
        const payload = remotePhotos[code] || null;
        const previous = mergePhotoSources(
          previousPhotos[code],
          knownPhotosByCode[code],
          product.photos
        );
        const normalized = mergePhotoSources(payload, previous) || fallbackPhotos(code);
        return [code, normalized] as const;
      });

      return Object.fromEntries(entries) as PhotosByCode;
    },
  });

  useEffect(() => {
    if (!photosQuery.data) return;

    const received = photosQuery.data;
    persistPhotosByCode(received);
    // The session cache is independent of localStorage and the changing batch key.
    setKnownPhotosByCode((current) => mergePhotosByCode(current, received));
    setFailedPhotoCodes((current) => {
      const remaining = [...current].filter((code) => !(code in received));
      return remaining.length === current.size ? current : new Set(remaining);
    });
  }, [photosQuery.data]);

  const photosByProductId = useMemo(() => {
    const entries: PhotosByProductId = {};
    const displayed = selectedProduct ? [...visibleProducts, selectedProduct] : visibleProducts;
    for (const item of displayed) {
      const photos = mergePhotoSources(
        photosQuery.data?.[item.code],
        knownPhotosByCode[item.code],
        item.photos
      );
      if (photos) entries[item.id] = photos;
    }
    return entries;
  }, [knownPhotosByCode, photosQuery.data, selectedProduct, visibleProducts]);
  const selectedPhotos = selectedProduct ? photosByProductId[selectedProduct.id] || null : null;

  const selectedGalleryEntries = useMemo(() => {
    if (!selectedProduct) return [];
    return buildGalleryEntries(selectedProduct, selectedPhotos, galleryQuery.data || []);
  }, [galleryQuery.data, selectedPhotos, selectedProduct]);

  const loading = productsQuery.isLoading;
  const loadingPhotos = photosQuery.isFetching;
  const hiddenProductsCount = Math.max(filteredProducts.length - visibleProducts.length, 0);
  const canLoadMoreProducts = hiddenProductsCount > 0;
  const representativeName =
    representativeSessionQuery.data?.user?.name ||
    representativeSessionQuery.data?.user?.email ||
    "Representante";

  const productsError = productsQuery.isError ? "Não foi possível carregar os produtos agora." : "";
  const emptyError =
    !loading && !productsError && brandProducts.length === 0 ? "Nenhum produto cadastrado." : "";

  const handleRepresentativeLogout = async () => {
    setIsLoggingOutRepresentative(true);
    setSessionError("");
    try {
      await logoutRepresentative();
      await queryClient.invalidateQueries({ queryKey: ["representative-session"] });
      navigate("/login", { replace: true });
    } catch {
      setSessionError("Não foi possível sair. Tente novamente.");
    } finally {
      setIsLoggingOutRepresentative(false);
    }
  };

  const exportCatalog = (format: CatalogExportFormat) => {
    return downloadCatalogExport({
      format,
      query,
      category: category === "Todas" ? "" : category,
      brand,
    });
  };

  const exportSelectedProduct = async (format: CatalogExportFormat) => {
    if (!selectedProduct) return;
    await downloadCatalogExport({
      format,
      code: selectedProduct.code,
    });
  };

  return (
    <div className={`page-shell catalog-page ${brandMeta.pageClassName}`}>
      <a className="skip-link" href="#catalog-content">
        Pular para os produtos
      </a>
      <div className="bg-orb orb-a" aria-hidden="true"></div>
      <div className="bg-orb orb-b" aria-hidden="true"></div>

      <header className={`hero ${brandMeta.heroClassName}`.trim()}>
        <div className="hero-identity">
          <h1 className="sr-only">
            {selectedProduct?.name || `Catálogo de produtos ${brandMeta.tabLabel}`}
          </h1>
          <div className="hero-kicker">{brandMeta.kicker}</div>
          <div className="hero-brand" aria-label={`Marca ${brandMeta.tabLabel}`}>
            <p className="hero-brand-name">{brandMeta.title}</p>
            <p className="hero-brand-subtitle">{brandMeta.subtitle}</p>
          </div>
          <div className="hero-admin-actions">
            {representativeSessionQuery.data?.authenticated && (
              <span className="hero-session-pill">Acesso liberado para {representativeName}</span>
            )}
            <Link className="hero-link-button" to="/erp">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14" />
              </svg>
              Painel admin
            </Link>
            {representativeSessionQuery.data?.authenticated && (
              <button
                type="button"
                className="hero-link-button"
                onClick={() => void handleRepresentativeLogout()}
                disabled={isLoggingOutRepresentative}
              >
                {isLoggingOutRepresentative ? "Saindo..." : "Sair"}
              </button>
            )}
          </div>
        </div>
      </header>

      <main id="catalog-content" tabIndex={-1} className="content-wrap" aria-busy={loading}>
        {sessionError && (
          <div className="banner banner-warning" role="alert">
            {sessionError}
          </div>
        )}
        {selectedProduct ? (
          <>
            {galleryQuery.isFetching && <p role="status">Carregando fotos…</p>}
            {galleryQuery.isError && (
              <div className="banner banner-warning" role="alert">
                Não foi possível carregar todas as fotos.{" "}
                <button
                  className="hero-link-button"
                  type="button"
                  onClick={() => void galleryQuery.refetch()}
                >
                  Tentar novamente
                </button>
              </div>
            )}
            <ProductDetail
              item={selectedProduct}
              photos={selectedPhotos}
              galleryEntries={selectedGalleryEntries}
              backTo={`/${location.search}`}
              onExport={exportSelectedProduct}
            />
          </>
        ) : (
          <>
            <section className="brand-tabs" aria-label="Selecionar linha da marca">
              {BRAND_ORDER.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={`brand-tab ${brand === value ? "is-active" : ""} ${value === "pienza" ? "is-premium" : ""}`}
                  onClick={() => update({ brand: value, category: "Todas" })}
                  aria-pressed={brand === value}
                >
                  <span className="brand-tab-title">{BRAND_META[value].tabLabel}</span>
                  <span className="brand-tab-copy">{brandCounts[value]} produtos</span>
                </button>
              ))}
            </section>
            <section className="toolbar" aria-label="Filtros do catálogo">
              <label className="field search-field">
                <span>Buscar produto</span>
                <input
                  type="search"
                  name="q"
                  autoComplete="off"
                  spellCheck={false}
                  value={query}
                  onChange={(event) => update({ q: event.target.value }, true)}
                  placeholder="Nome, código ou categoria…"
                />
              </label>
              <label className="field filter-field">
                <span>Categoria</span>
                <select
                  name="category"
                  value={category}
                  onChange={(event) => update({ category: event.target.value })}
                >
                  {categories.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </section>
            <div className="catalog-summary">
              <p className="result-summary" role="status" aria-live="polite">
                {loading
                  ? "Carregando produtos…"
                  : `${visibleProducts.length} de ${filteredProducts.length} produtos`}
                {loadingPhotos ? " · Carregando fotos…" : ""}
              </p>
              <ExportActions
                title={brandMeta.exportTitle}
                note={`${filteredProducts.length} produtos da seleção atual. Os filtros também se aplicam ao download.`}
                onExport={exportCatalog}
                disabled={loading || Boolean(productsError) || filteredProducts.length === 0}
                collapsible
              />
            </div>
            {productsError && (
              <div className="banner banner-warning" role="alert">
                {productsError}{" "}
                <button
                  type="button"
                  className="hero-link-button"
                  onClick={() => void productsQuery.refetch()}
                  disabled={productsQuery.isFetching}
                >
                  {productsQuery.isFetching ? "Tentando novamente…" : "Tentar novamente"}
                </button>
              </div>
            )}
            {photosQuery.isError && (
              <div className="banner banner-warning" role="alert">
                Algumas fotos não puderam ser carregadas.{" "}
                <button
                  type="button"
                  className="hero-link-button"
                  onClick={() => void photosQuery.refetch()}
                  disabled={photosQuery.isFetching}
                >
                  Tentar novamente
                </button>
              </div>
            )}
            <h2 className="sr-only">Produtos {brandMeta.tabLabel}</h2>
            {loading ? (
              <section className="loading-state" role="status">
                Carregando lista de produtos…
              </section>
            ) : visibleProducts.length > 0 ? (
              <>
                <section className="catalog-grid catalog-grid-flat" aria-label="Lista de produtos">
                  {visibleProducts.map((item, index) => (
                    <ProductCard
                      key={item.routeId}
                      item={item}
                      photos={photosByProductId[item.id]}
                      index={index}
                      href={`/produto/${item.routeId}${location.search}`}
                      onOpen={() => rememberCatalogPosition(location.search, item.routeId)}
                      onPhotoError={() => refreshFailedPhoto(item.code)}
                    />
                  ))}
                </section>
                {canLoadMoreProducts && (
                  <div className="load-more-panel">
                    <button
                      type="button"
                      className="load-more-button"
                      onClick={() => loadMore(filteredProducts.length)}
                    >
                      Carregar mais {Math.min(responsiveProductsBatch, hiddenProductsCount)}{" "}
                      produtos
                    </button>
                    <span>{hiddenProductsCount} produtos restantes</span>
                  </div>
                )}
              </>
            ) : (
              !productsError && (
                <section className="empty-state">
                  <h2>{emptyError || "Nenhum item encontrado"}</h2>
                  <p>Ajuste a busca ou selecione outra categoria.</p>
                  {(query || category !== "Todas") && (
                    <button
                      className="export-button"
                      type="button"
                      onClick={() => update({ q: "", category: "Todas" })}
                    >
                      Limpar filtros
                    </button>
                  )}
                </section>
              )
            )}
          </>
        )}
      </main>
    </div>
  );
}
