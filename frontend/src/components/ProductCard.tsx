import { useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";

import type { CatalogProduct, ProductPhotos } from "../types";
import { CARD_FALLBACK_IMAGE } from "../lib/catalog-core";
import { getProductImageCandidates, hasProductValue } from "../lib/catalog-products";
import { optimizeCatalogImageUrl } from "../lib/catalog-api";
import { ThumbStrip } from "./Thumb";

interface ProductCardProps {
  item: CatalogProduct;
  photos?: ProductPhotos | null;
  index: number;
  href: string;
  onOpen: () => void;
  onPhotoError?: () => void;
}

export default function ProductCard({
  item,
  photos,
  index,
  href,
  onOpen,
  onPhotoError,
}: ProductCardProps): JSX.Element {
  const [failedImages, setFailedImages] = useState<string[]>([]);
  const previewImage =
    getProductImageCandidates(photos, item.cover)
      .map((url) => optimizeCatalogImageUrl(url, "card"))
      .find((url): url is string => Boolean(url) && !failedImages.includes(url || "")) ||
    CARD_FALLBACK_IMAGE;
  const description = item.description.replace(/\s+\+\s+/g, " · ");

  return (
    <article
      className="product-card"
      style={{ "--stagger": `${Math.min(index * 70, 700)}ms` } as CSSProperties}
    >
      <Link
        to={href}
        id={`product-link-${item.routeId}`}
        className="card-hitbox"
        onClick={(event) => {
          if (
            !event.metaKey &&
            !event.ctrlKey &&
            !event.shiftKey &&
            !event.altKey &&
            event.button === 0
          )
            onOpen();
        }}
        aria-label={`Abrir detalhes de ${item.name || "produto"}`}
      >
        <div className="media">
          <img
            key={previewImage}
            src={previewImage}
            alt={item.name || "Produto"}
            loading={index < 4 ? "eager" : "lazy"}
            decoding="async"
            width="900"
            height="700"
            onError={() => {
              if (previewImage === CARD_FALLBACK_IMAGE) return;
              setFailedImages((previous) =>
                previous.includes(previewImage) ? previous : [...previous, previewImage]
              );
              onPhotoError?.();
            }}
          />
          <div className="media-overlay" aria-hidden="true"></div>
          <span className="chip chip-code">#{item.code}</span>
          {hasProductValue(item.category) && (
            <span className="chip chip-category">{item.category}</span>
          )}
        </div>

        <div className="card-body">
          <h3 title={item.name || "Produto"}>{item.name || "Produto"}</h3>
          {hasProductValue(description) && <p className="description">{description}</p>}
          <span className="expand-label">Ver produto e fotos</span>
        </div>
      </Link>

      <ThumbStrip photos={photos} />
    </article>
  );
}
