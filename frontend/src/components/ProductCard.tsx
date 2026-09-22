import type { CSSProperties } from "react";

import type { CatalogProduct, ProductPhotos } from "../types";
import { CARD_FALLBACK_IMAGE, setFallbackImage } from "../lib/catalog-core";
import { getPrimaryProductImage } from "../lib/catalog-products";
import { optimizeCatalogImageUrl } from "../lib/catalog-api";
import { ThumbStrip } from "./Thumb";

interface ProductCardProps {
  item: CatalogProduct;
  photos?: ProductPhotos | null;
  index: number;
  onOpen: () => void;
}

export default function ProductCard({
  item,
  photos,
  index,
  onOpen,
}: ProductCardProps): JSX.Element {
  const previewImage =
    optimizeCatalogImageUrl(getPrimaryProductImage(photos, item.cover), "card") || CARD_FALLBACK_IMAGE;

  return (
    <article className="product-card" style={{ "--stagger": `${Math.min(index * 70, 700)}ms` } as CSSProperties}>
      <button
        type="button"
        className="card-hitbox"
        onClick={onOpen}
        aria-label={`Abrir detalhes de ${item.name || "produto"}`}
      >
        <div className="media">
          <img
            src={previewImage}
            alt={item.name || "Produto"}
            loading="lazy"
            decoding="async"
            width="900"
            height="700"
            onError={(event) => setFallbackImage(event, CARD_FALLBACK_IMAGE)}
          />
          <div className="media-overlay"></div>
          <span className="chip chip-code">#{item.code}</span>
          <span className="chip chip-category">{item.category}</span>
        </div>

        <div className="card-body">
          <h3>{item.name || "Produto"}</h3>
          <p className="description">{item.description || "Descrição indisponível para este produto."}</p>
          <span className="expand-label">Abrir galeria completa</span>
        </div>
      </button>

      <ThumbStrip photos={photos} />
    </article>
  );
}
