import { useState } from "react";

import type { ProductPhotos } from "../types";
import { optimizeCatalogImageUrl } from "../lib/catalog-api";

interface ThumbProps {
  image?: string | null;
  label: string;
}

export function Thumb({ image, label }: ThumbProps): JSX.Element {
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const source = String(image || "").trim();
  const isPlaceholder =
    !source ||
    source.toLowerCase().startsWith("data:image/svg+xml") ||
    /placehold\.co|placeholder|sem foto|sem imagem/i.test(source);
  const imageUrl = isPlaceholder ? "" : optimizeCatalogImageUrl(source, "thumb") || "";
  const isUnavailable = !imageUrl || failedImage === source;

  return (
    <figure className={`thumb ${isUnavailable ? "is-unavailable" : ""}`}>
      {isUnavailable ? (
        <div className="thumb-placeholder" role="img" aria-label={`Foto ${label.toLowerCase()} indisponível`}>
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
            <circle cx="9" cy="9" r="1.5" />
            <path d="m5 17 5-5 3 3 2-2 4 4" />
          </svg>
          <span>Sem foto</span>
        </div>
      ) : (
        <img
          src={imageUrl}
          alt={`Foto ${label.toLowerCase()} do produto`}
          loading="lazy"
          decoding="async"
          width="240"
          height="240"
          onError={() => setFailedImage(source)}
        />
      )}
      <figcaption>{label}</figcaption>
    </figure>
  );
}

interface ThumbStripProps {
  photos?: ProductPhotos | null;
}

export function ThumbStrip({ photos }: ThumbStripProps): JSX.Element {
  return (
    <div className="thumb-strip" role="group" aria-label="Fotos do produto">
      <Thumb image={photos?.white_background} label="Fundo branco" />
      <Thumb image={photos?.measures} label="Medidas" />
      <Thumb image={photos?.ambient} label="Ambientada" />
    </div>
  );
}
