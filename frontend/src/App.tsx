import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import ExportActions from "./components/ExportActions";
import ProductCard from "./components/ProductCard";
import ProductDetail from "./components/ProductDetail";
import {
  downloadCatalogExport,
  fetchRepresentativeSession,
  fetchImagesByCode,
  fetchPhotosByCode,
  fetchProducts,
  logoutRepresentative,
} from "./lib/catalog-api";
import {
  DEMO_PRODUCTS,
  buildGalleryEntries,
  fallbackPhotos,
  getHomeShowcaseProducts,
  hasAnyPhoto,
  normalizeProduct,
  normalizeText,
} from "./lib/catalog-products";
import { persistUiState, readPersistedUiState } from "./lib/catalog-storage";
import type { CatalogBrand, CatalogExportFormat, CatalogProduct, ProductPhotos } from "./types";

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
    exportTitle: "Exportar recorte Nitrolux",
  },
  pienza: {
    tabLabel: "Pienza",
    kicker: "Coleção premium",
    title: "PIENZA",
    subtitle: "Pendentes, arandelas e luminárias decorativas",
    pageClassName: "brand-theme-pienza",
    heroClassName: "hero-premium",
    resultLabel: "coleção Pienza",
    exportTitle: "Exportar recorte Pienza",
  },
};
function formatDisplayNumber(value: number): string {
  const maximumFractionDigits = Number.isInteger(value) ? 0 : 1;
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits }).format(value);
}

function useCatalogProducts() {
  return useQuery({
    queryKey: ["catalog-products"],
    queryFn: fetchProducts,
    staleTime: 60_000,
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
  const initialUiState = useMemo(() => readPersistedUiState(), []);
  const responsiveProductsBatch = useResponsiveProductsBatch();

  const [query, setQuery] = useState(initialUiState.query);
  const [category, setCategory] = useState(initialUiState.category);
  const [brand, setBrand] = useState<CatalogBrand>(initialUiState.brand);
  const [isLoggingOutRepresentative, setIsLoggingOutRepresentative] = useState(false);
  const [visibleProductCount, setVisibleProductCount] = useState(responsiveProductsBatch);

  const productsQuery = useCatalogProducts();
  const representativeSessionQuery = useQuery({
    queryKey: ["representative-session"],
    queryFn: fetchRepresentativeSession,
    retry: false,
    staleTime: 30_000,
  });

  const products = useMemo(() => {
    const source = productsQuery.data && productsQuery.data.length > 0 ? productsQuery.data : DEMO_PRODUCTS;
    return source.map((item, index) => normalizeProduct(item, index));
  }, [productsQuery.data]);

  const selectedProduct = useMemo(() => {
    if (!productId) return null;
    return products.find((item) => item.routeId === productId) || null;
  }, [productId, products]);

  useEffect(() => {
    if (!productId || productsQuery.isLoading) return;
    if (!selectedProduct) {
      navigate("/", { replace: true });
    }
  }, [navigate, productId, productsQuery.isLoading, selectedProduct]);

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

  useEffect(() => {
    persistUiState({ query, category, brand });
  }, [brand, query, category]);

  useEffect(() => {
    if (!selectedProduct?.brand) return;
    if (selectedProduct.brand !== brand) {
      setBrand(selectedProduct.brand);
    }
  }, [brand, selectedProduct]);

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

  const brandProducts = useMemo(() => products.filter((item) => item.brand === brand), [brand, products]);

  const categories = useMemo(() => {
    const values = Array.from(new Set(brandProducts.map((item) => item.category).filter(Boolean))).sort((a, b) =>
      a.localeCompare(b)
    );
    return ["Todas", ...values];
  }, [brandProducts]);

  useEffect(() => {
    if (category === "Todas") return;
    if (!categories.includes(category)) {
      setCategory("Todas");
    }
  }, [category, categories]);

  const filteredProducts = useMemo(() => {
    const search = normalizeText(query);

    return products.filter((item) => {
      if (item.brand !== brand) return false;
      const categoryOk = category === "Todas" || item.category === category;
      const textBlob = normalizeText(`${item.name} ${item.code} ${item.description} ${item.category}`);
      const queryOk = !search || textBlob.includes(search);
      return categoryOk && queryOk;
    });
  }, [brand, category, products, query]);

  const isHomeShowcase = category === "Todas" && normalizeText(query) === "";

  useEffect(() => {
    setVisibleProductCount(responsiveProductsBatch);
  }, [brand, category, query, responsiveProductsBatch]);

  const visibleProducts = useMemo(() => {
    if (isHomeShowcase) {
      return getHomeShowcaseProducts(filteredProducts, INITIAL_PRODUCTS_LIMIT);
    }
    return filteredProducts.slice(0, visibleProductCount);
  }, [filteredProducts, isHomeShowcase, visibleProductCount]);

  const embeddedPhotosByProductId = useMemo(() => {
    const entries = new Map<string, ProductPhotos>();
    for (const item of visibleProducts) {
      if (hasAnyPhoto(item.photos)) {
        entries.set(item.id, item.photos);
      }
    }
    if (selectedProduct && hasAnyPhoto(selectedProduct.photos)) {
      entries.set(selectedProduct.id, selectedProduct.photos);
    }
    return Object.fromEntries(entries) as PhotosByProductId;
  }, [selectedProduct, visibleProducts]);

  const photoTargets = useMemo(() => {
    if (!selectedProduct || hasAnyPhoto(selectedProduct.photos)) {
      return [];
    }
    return [selectedProduct];
  }, [selectedProduct]);

  const photosQuery = useQuery({
    queryKey: [
      "catalog-photos",
      photoTargets
        .map((item) => item.code || item.id)
        .join("|")
        .toLowerCase(),
    ],
    enabled: photoTargets.length > 0,
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<PhotosByProductId> => {
      const entries = await Promise.all(
        photoTargets.map(async (product) => {
          if (hasAnyPhoto(product.photos)) {
            return [product.id, product.photos] as const;
          }

          const code = product.code || product.id;
          const payload = await fetchPhotosByCode(code);
          const normalized = hasAnyPhoto(payload) ? payload : fallbackPhotos(code);
          return [product.id, normalized] as const;
        })
      );

      return Object.fromEntries(entries) as PhotosByProductId;
    },
  });

  const photosByProductId = useMemo(
    () => ({ ...embeddedPhotosByProductId, ...(photosQuery.data || {}) }),
    [embeddedPhotosByProductId, photosQuery.data]
  );
  const selectedPhotos = selectedProduct ? photosByProductId[selectedProduct.id] || null : null;

  const productsByCategory = useMemo(() => {
    const groups = new Map<string, CatalogProduct[]>();
    for (const item of visibleProducts) {
      const group = item.category || "Sem categoria";
      const list = groups.get(group) || [];
      list.push(item);
      groups.set(group, list);
    }
    return Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right));
  }, [visibleProducts]);
  const visibleCategoryCount = productsByCategory.length;
  const showGroupedCatalog = category === "Todas" && !isHomeShowcase;
  const showcaseCategories = useMemo(
    () =>
      productsByCategory.map(([groupName, groupProducts]) => ({
        name: groupName,
        count: groupProducts.length,
      })),
    [productsByCategory]
  );

  const selectedGalleryEntries = useMemo(() => {
    if (!selectedProduct) return [];
    return buildGalleryEntries(selectedProduct, selectedPhotos, galleryQuery.data || []);
  }, [galleryQuery.data, selectedPhotos, selectedProduct]);

  const loading = productsQuery.isLoading;
  const loadingPhotos = photosQuery.isFetching;
  const loadedPhotoCount = Object.keys(photosByProductId).length;
  const hiddenProductsCount = Math.max(filteredProducts.length - visibleProducts.length, 0);
  const canLoadMoreProducts = !isHomeShowcase && hiddenProductsCount > 0;
  const homeShowcaseHasMonthlySales = isHomeShowcase && visibleProducts.some((item) => item.monthlySales > 0);
  const homeShowcaseSalesTotal = homeShowcaseHasMonthlySales
    ? visibleProducts.reduce((total, item) => total + item.monthlySales, 0)
    : 0;
  const representativeName =
    representativeSessionQuery.data?.user?.name ||
    representativeSessionQuery.data?.user?.email ||
    "Representante";

  const productsError = productsQuery.isError ? "Não foi possível carregar os produtos agora." : "";
  const emptyError = !loading && !productsError && brandProducts.length === 0 ? "Nenhum produto cadastrado." : "";

  const openProduct = (item: CatalogProduct) => {
    navigate(`/produto/${item.routeId}`);
  };

  const closeDetail = () => {
    navigate("/");
  };

  const handleRepresentativeLogout = async () => {
    setIsLoggingOutRepresentative(true);
    try {
      await logoutRepresentative();
      await queryClient.invalidateQueries({ queryKey: ["representative-session"] });
      navigate("/login", { replace: true });
    } finally {
      setIsLoggingOutRepresentative(false);
    }
  };

  const exportCatalog = (format: CatalogExportFormat) => {
    void downloadCatalogExport({
      format,
      query,
      category: category === "Todas" ? "" : category,
      brand,
    });
  };

  const exportSelectedProduct = (format: CatalogExportFormat) => {
    if (!selectedProduct) return;
    void downloadCatalogExport({
      format,
      code: selectedProduct.code,
    });
  };

  const loadMoreProducts = () => {
    setVisibleProductCount((current) => Math.min(current + responsiveProductsBatch, filteredProducts.length));
  };

  return (
    <div className={`page-shell ${brandMeta.pageClassName}`}>
      <div className="bg-orb orb-a" aria-hidden="true"></div>
      <div className="bg-orb orb-b" aria-hidden="true"></div>

      <header className={`hero ${brandMeta.heroClassName}`.trim()}>
        <div className="hero-identity">
          <h1 className="sr-only">Catálogo de produtos {brandMeta.tabLabel}</h1>
          <div className="hero-kicker">{brandMeta.kicker}</div>
          <div className="hero-brand" aria-label={`Marca ${brandMeta.tabLabel}`}>
            <p className="hero-brand-name">{brandMeta.title}</p>
            <p className="hero-brand-subtitle">{brandMeta.subtitle}</p>
          </div>
          <div className="hero-admin-actions">
            {representativeSessionQuery.data?.authenticated && (
              <span className="hero-session-pill">Acesso liberado para {representativeName}</span>
            )}
            <button type="button" className="hero-link-button" onClick={() => navigate("/erp")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
              </svg>
              Painel admin
            </button>
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

      <main className="content-wrap" aria-busy={loading || loadingPhotos}>
        {selectedProduct ? (
          <ProductDetail
            item={selectedProduct}
            photos={selectedPhotos}
            galleryEntries={selectedGalleryEntries}
            onBack={closeDetail}
            onExport={exportSelectedProduct}
          />
        ) : (
          <>
            <section className="brand-tabs" aria-label="Selecionar linha da marca">
              {BRAND_ORDER.map((value) => {
                const meta = BRAND_META[value];
                const isActive = brand === value;
                return (
                  <button
                    key={value}
                    type="button"
                    className={`brand-tab ${isActive ? "is-active" : ""} ${value === "pienza" ? "is-premium" : ""}`}
                    onClick={() => setBrand(value)}
                    aria-pressed={isActive}
                    aria-current={isActive ? "true" : undefined}
                  >
                    <span className="brand-tab-title">{meta.tabLabel}</span>
                    <span className="brand-tab-copy">{brandCounts[value]} produtos</span>
                  </button>
                );
              })}
            </section>

            <section className="toolbar" aria-label="Filtros do catálogo">
              <label className="field search-field">
                <span>Buscar produto</span>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Nome, código ou categoria"
                />
              </label>

              <label className="field filter-field">
                <span>Categoria</span>
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  {categories.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </section>

            <ExportActions
              title={brandMeta.exportTitle}
              note={
                isHomeShowcase
                  ? homeShowcaseHasMonthlySales
                    ? `${visibleProducts.length} produtos no ranking mensal e ${filteredProducts.length} na ${brandMeta.resultLabel}, com dados e fotos conforme o formato.`
                    : `${visibleProducts.length} produtos em destaque agora e ${filteredProducts.length} na ${brandMeta.resultLabel}, com dados e fotos conforme o formato.`
                  : `${visibleProducts.length} itens exibidos agora e ${filteredProducts.length} no recorte atual da ${brandMeta.resultLabel}, com dados e fotos conforme o formato.`
              }
              onExport={exportCatalog}
              disabled={loading || filteredProducts.length === 0}
            />

            <p className="result-summary" role="status" aria-live="polite">
              {loading
                ? "Carregando produtos..."
                : hiddenProductsCount > 0
                  ? isHomeShowcase
                    ? homeShowcaseHasMonthlySales
                      ? `${filteredProducts.length} itens encontrados na ${brandMeta.resultLabel}, exibindo os ${visibleProducts.length} mais vendidos do mês`
                      : `${filteredProducts.length} itens encontrados na ${brandMeta.resultLabel}, exibindo ${visibleProducts.length} produtos em destaque`
                    : `${filteredProducts.length} itens encontrados na ${brandMeta.resultLabel}, exibindo ${visibleProducts.length} na grade inicial`
                  : `${filteredProducts.length} itens encontrados na ${brandMeta.resultLabel}`}
            </p>

            {productsError && <div className="banner banner-warning">{productsError}</div>}
            {emptyError && <div className="banner banner-warning">{emptyError}</div>}
            {!productsError && !emptyError && loadingPhotos && (
              <div className="banner banner-info">Carregando fotos dos produtos...</div>
            )}

            <section className="stats-grid" aria-label="Resumo">
              <article className="stat-card">
                <strong>{visibleProducts.length}</strong>
                <span>
                  {isHomeShowcase
                    ? homeShowcaseHasMonthlySales
                      ? `${brandMeta.tabLabel} no top do mês`
                      : `${brandMeta.tabLabel} em destaque`
                    : "Itens exibidos"}
                </span>
              </article>
              <article className="stat-card">
                <strong>{homeShowcaseHasMonthlySales ? formatDisplayNumber(homeShowcaseSalesTotal) : visibleCategoryCount}</strong>
                <span>
                  {isHomeShowcase
                    ? homeShowcaseHasMonthlySales
                      ? "Vendas somadas no top 15"
                      : "Categorias em destaque"
                    : "Categorias no recorte"}
                </span>
              </article>
              <article className="stat-card">
                <strong>{homeShowcaseHasMonthlySales ? visibleCategoryCount : loadedPhotoCount}</strong>
                <span>{homeShowcaseHasMonthlySales ? "Categorias no top 15" : "Galerias prontas"}</span>
              </article>
            </section>

            {loading ? (
              <section className="loading-state" role="status" aria-live="polite">
                Carregando lista de produtos...
              </section>
            ) : visibleProducts.length > 0 ? (
              <>
                {isHomeShowcase && homeShowcaseHasMonthlySales && (
                  <section className="showcase-hero-panel" aria-label="Mais vendidos do mês">
                    <p className="showcase-hero-kicker">Ranking do mês</p>
                    <h2>15 produtos mais vendidos</h2>
                    <p>
                      A seleção inicial agora prioriza a coluna de venda mensal do relatório de estoque mais
                      recente para destacar o que mais gira na {brandMeta.resultLabel}.
                    </p>
                  </section>
                )}
                {isHomeShowcase && (
                  <section
                    className="showcase-category-strip"
                    aria-label={homeShowcaseHasMonthlySales ? "Categorias presentes no top 15" : "Categorias em destaque"}
                  >
                    {showcaseCategories.map((entry) => (
                      <span key={`${entry.name}-${entry.count}`} className="showcase-category-pill">
                        {entry.name} ({entry.count})
                      </span>
                    ))}
                  </section>
                )}
                {showGroupedCatalog ? (
                  <section className="catalog-groups">
                    {productsByCategory.map(([groupName, groupProducts]) => (
                      <section key={groupName} className="category-group">
                        <h2 className="category-title">{groupName}</h2>
                        <div className="catalog-grid">
                          {groupProducts.map((item, index) => (
                            <ProductCard
                              key={`${item.routeId}-${item.id}`}
                              item={item}
                              photos={photosByProductId[item.id]}
                              index={index}
                              onOpen={() => openProduct(item)}
                            />
                          ))}
                        </div>
                      </section>
                    ))}
                  </section>
                ) : (
                  <section className="catalog-grid catalog-grid-flat">
                    {visibleProducts.map((item, index) => (
                      <ProductCard
                        key={`${item.routeId}-${item.id}`}
                        item={item}
                        photos={photosByProductId[item.id]}
                        index={index}
                        showSalesHighlight={homeShowcaseHasMonthlySales}
                        salesRank={homeShowcaseHasMonthlySales ? index + 1 : undefined}
                        onOpen={() => openProduct(item)}
                      />
                    ))}
                  </section>
                )}
                {canLoadMoreProducts && (
                  <div className="load-more-panel">
                    <button type="button" className="load-more-button" onClick={loadMoreProducts}>
                      Carregar mais {Math.min(responsiveProductsBatch, hiddenProductsCount)} produtos
                    </button>
                    <span>{hiddenProductsCount} ainda no recorte atual</span>
                  </div>
                )}
              </>
            ) : (
              <section className="empty-state">
                <h2>Nenhum item encontrado</h2>
                <p>Ajuste a busca ou selecione outra categoria.</p>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
