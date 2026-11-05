import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useDownloadAction } from "../lib/use-download-action";
import DownloadFeedback from "./DownloadFeedback";

import ExportActions from "./ExportActions";
import type { CatalogExportFormat, CatalogProduct, GalleryEntry, ProductPhotos } from "../types";
import { DETAIL_FALLBACK_IMAGE, THUMB_FALLBACK_IMAGE, setFallbackImage } from "../lib/catalog-core";
import { downloadImageFile, optimizeCatalogImageUrl } from "../lib/catalog-api";
import {
  buildGalleryEntries,
  findPreferredGalleryIndex,
  getPrimaryProductImage,
  getTechnicalPresentation,
  hasProductValue,
} from "../lib/catalog-products";

interface ProductDetailProps {
  item: CatalogProduct;
  photos?: ProductPhotos | null;
  galleryEntries: GalleryEntry[];
  backTo: string;
  onExport: (format: CatalogExportFormat) => Promise<void>;
}

const ATTRIBUTE_LABEL_MAP: Record<string, string> = {
  CODPROD: "Código",
  CODAUXILIAR: "Código de barras",
  INFORMACOESTECNICAS: "Informações técnicas",
  NBM: "NCM",
  PERCIPIVENDA: "IPI",
};

function getAttributeDisplayLabel(label: string): string {
  const normalized = String(label || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/gi, "")
    .trim()
    .toUpperCase();
  return ATTRIBUTE_LABEL_MAP[normalized] || label;
}

export default function ProductDetail({
  item,
  photos,
  galleryEntries,
  backTo,
  onExport,
}: ProductDetailProps): JSX.Element {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const download = useDownloadAction();
  const [activeIndex, setActiveIndex] = useState(0);
  const gallery =
    galleryEntries && galleryEntries.length > 0
      ? galleryEntries
      : buildGalleryEntries(item, photos, []);
  const preferredGalleryIndex = findPreferredGalleryIndex(
    gallery,
    getPrimaryProductImage(photos, item.cover)
  );
  const technical = getTechnicalPresentation(item.specs, item.code);
  const attributes = item.attributes.filter((attribute) => hasProductValue(attribute.value));
  const hasTechnical = technical.attributes.length > 0 || technical.notes.length > 0;
  const galleryResetKey = gallery.map((entry) => entry.key || entry.url || entry.label).join("|");
  const currentIndex =
    activeIndex >= 0 && activeIndex < gallery.length ? activeIndex : preferredGalleryIndex;
  const activeImage = gallery[currentIndex] || gallery[preferredGalleryIndex] || gallery[0] || null;

  useEffect(() => {
    setActiveIndex(preferredGalleryIndex);
  }, [item.routeId, galleryResetKey, preferredGalleryIndex]);

  useEffect(() => {
    window.scrollTo(0, 0);
    headingRef.current?.focus({ preventScroll: true });
  }, [item.routeId]);

  const hasDownloadablePhoto = Boolean(
    activeImage?.url && !activeImage.url.startsWith("data:image/svg+xml")
  );
  const hasAnyDownloadablePhoto = gallery.some(
    (entry) => entry.url && !entry.url.startsWith("data:image/svg+xml")
  );
  const downloadSelectedImage = () => {
    if (!activeImage?.url || !hasDownloadablePhoto) return;
    void download.run("foto selecionada", () =>
      downloadImageFile(activeImage.url, `${item.code}-${activeImage.label}`)
    );
  };

  return (
    <section className="detail-panel" aria-label="Detalhes do produto">
      <Link className="detail-back" to={backTo}>
        Voltar ao catálogo
      </Link>
      <DownloadFeedback feedback={download.feedback} />

      <div className="detail-layout">
        <div className="detail-visual">
          <div className="detail-media">
            <img
              key={activeImage?.url || item.routeId}
              src={optimizeCatalogImageUrl(activeImage?.url, "detail") || DETAIL_FALLBACK_IMAGE}
              alt={`${item.name || "Produto"} — ${activeImage?.label || "Foto"}`}
              width="1200"
              height="900"
              decoding="async"
              {...{ fetchpriority: "high" }}
              onError={(event) => setFallbackImage(event, DETAIL_FALLBACK_IMAGE)}
            />
          </div>
          <section className="detail-photo-browser" aria-label="Fotos do produto">
            <h3>Fotos do produto</h3>
            <div className="detail-gallery">
              {gallery.map((image, idx) => (
                <button
                  key={image.key || `${image.label}-${idx}`}
                  type="button"
                  className={`detail-gallery-btn ${idx === currentIndex ? "is-active" : ""}`}
                  onClick={() => setActiveIndex(idx)}
                  aria-pressed={idx === currentIndex}
                  aria-label={`Selecionar ${image.label}`}
                >
                  <img
                    src={optimizeCatalogImageUrl(image.url, "thumb") || THUMB_FALLBACK_IMAGE}
                    alt={image.label}
                    width="240"
                    height="240"
                    loading="lazy"
                    decoding="async"
                    onError={(event) => setFallbackImage(event, THUMB_FALLBACK_IMAGE)}
                  />
                  <span>{image.label}</span>
                </button>
              ))}
            </div>
            <div className="detail-gallery-actions">
              <button
                type="button"
                className="detail-action-button"
                onClick={downloadSelectedImage}
                disabled={!hasDownloadablePhoto || download.pending !== null}
              >
                {download.pending === "foto selecionada"
                  ? "Preparando foto…"
                  : "Baixar foto selecionada"}
              </button>
              <button
                type="button"
                className="detail-action-button is-secondary"
                disabled={!hasAnyDownloadablePhoto || download.pending !== null}
                onClick={() => void download.run("ZIP de fotos", () => onExport("zip"))}
              >
                Baixar todas em ZIP
              </button>
            </div>
          </section>
        </div>

        <aside className="detail-meta">
          <header className="detail-product-heading">
            <span className="detail-eyebrow">Informações do produto</span>
            <h2 ref={headingRef} tabIndex={-1}>
              {item.name || "Produto"}
            </h2>
            <div className="detail-tags" aria-label="Identificação do produto">
              <span className="detail-tag detail-tag-brand">{item.brandLabel}</span>
              <span className="detail-tag detail-tag-code">
                <span>Código</span>
                <strong>{item.code}</strong>
              </span>
              {hasProductValue(item.category) && (
                <span className="detail-tag detail-tag-category">{item.category}</span>
              )}
            </div>
          </header>

          <div className="detail-information">
            {hasProductValue(item.description) && (
              <section className="detail-information-block">
                <h3>Descrição</h3>
                <p>{item.description}</p>
              </section>
            )}
            {hasTechnical && (
              <section className="detail-information-block detail-information-technical">
                <h3>Especificações técnicas</h3>
                {technical.attributes.length > 0 && (
                  <dl className="detail-technical-grid">
                    {technical.attributes.map((attribute) => (
                      <div key={`${attribute.label}-${attribute.value}`}>
                        <dt>{attribute.label}</dt>
                        <dd>{attribute.value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
                {technical.notes.map((note) => (
                  <p key={note}>{note}</p>
                ))}
              </section>
            )}
            {attributes.length > 0 && (
              <section
                className="detail-attributes-section"
                aria-label="Características do produto"
              >
                <div className="detail-section-heading">
                  <h3>Características</h3>
                  <span>
                    {attributes.length} {attributes.length === 1 ? "item" : "itens"}
                  </span>
                </div>
                <dl className="detail-attributes">
                  {attributes.map((attribute) => (
                    <div
                      key={`${attribute.label}-${attribute.value}`}
                      className="detail-attribute-item"
                    >
                      <dt>{getAttributeDisplayLabel(attribute.label)}</dt>
                      <dd>{attribute.value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
          </div>

          <ExportActions
            title="Baixar este produto"
            note="Baixe a ficha técnica em PDF ou exporte os dados e fotos do produto."
            onExport={onExport}
            compact
            includeTechnicalSheet
            downloadAction={download}
          />
        </aside>
      </div>
    </section>
  );
}
