import type { CatalogExportFormat } from "../types";

import { useDownloadAction, type DownloadAction } from "../lib/use-download-action";
import DownloadFeedback from "./DownloadFeedback";

interface ExportActionsProps {
  title: string;
  note?: string;
  onExport: (format: CatalogExportFormat) => Promise<void>;
  disabled?: boolean;
  compact?: boolean;
  includeTechnicalSheet?: boolean;
  collapsible?: boolean;
  downloadAction?: DownloadAction;
}

const EXPORT_BUTTONS: Array<{ format: CatalogExportFormat; label: string }> = [
  { format: "csv", label: "CSV" },
  { format: "xlsx", label: "Excel" },
  { format: "pdf", label: "PDF" },
  { format: "zip", label: "ZIP" },
  { format: "json", label: "JSON" },
];

export default function ExportActions({
  title,
  note,
  onExport,
  disabled = false,
  compact = false,
  includeTechnicalSheet = false,
  collapsible = false,
  downloadAction,
}: ExportActionsProps): JSX.Element {
  const localDownload = useDownloadAction();
  const download = downloadAction ?? localDownload;
  const buttons = includeTechnicalSheet
    ? [{ format: "ficha" as CatalogExportFormat, label: "Ficha técnica" }, ...EXPORT_BUTTONS]
    : EXPORT_BUTTONS;

  const panel = (
    <section className={`export-panel ${compact ? "is-compact" : ""}`} aria-label={title}>
      <div className="export-copy">
        <strong>{title}</strong>
        {note ? <span>{note}</span> : null}
      </div>

      <div className="export-actions">
        {buttons.map((item) => (
          <button
            key={item.format}
            type="button"
            className="export-button"
            onClick={() => void download.run(item.label, () => onExport(item.format))}
            disabled={disabled || download.pending !== null}
          >
            {download.pending === item.label ? `Preparando ${item.label}…` : item.label}
          </button>
        ))}
      </div>
      {!downloadAction && <DownloadFeedback feedback={download.feedback} />}
    </section>
  );
  return collapsible ? (
    <details
      className="export-menu"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.currentTarget.open = false;
          event.currentTarget.querySelector("summary")?.focus();
        }
      }}
    >
      <summary className="export-button">Baixar catálogo</summary>
      {panel}
    </details>
  ) : (
    panel
  );
}
