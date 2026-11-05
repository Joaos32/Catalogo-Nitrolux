import { BlobReader, Uint8ArrayReader, Uint8ArrayWriter, ZipReader, ZipWriter, type FileEntry } from "@zip.js/zip.js/index-native.js";
import { MAX_TECHNICAL_FILE_BYTES } from "./technical-sheet-limits";

const MAX_CELL_PACKAGE_BYTES = 64 * 1024 * 1024;
const MAX_CELL_PACKAGE_ENTRIES = 100;

class TechnicalArchiveError extends Error {}

function isCellDataPart(name: string): boolean {
  return /^(?:\[Content_Types\]\.xml|_rels\/\.rels|xl\/(?:workbook\.xml|_rels\/workbook\.xml\.rels|styles\.xml|sharedStrings\.xml|worksheets\/[^/]+\.xml))$/i.test(name);
}

function cellContentTypes(entries: FileEntry[]): Uint8Array {
  const overrides = entries.flatMap((entry) => {
    const name = entry.filename.toLowerCase();
    const type = name === "xl/workbook.xml" ? "sheet.main"
      : name === "xl/styles.xml" ? "styles"
      : name === "xl/sharedstrings.xml" ? "sharedStrings"
      : name.startsWith("xl/worksheets/") ? "worksheet" : null;
    if (!type) return [];
    const path = entry.filename.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return [`<Override PartName="/${path}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.${type}+xml"/>`];
  });
  return new TextEncoder().encode(
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' + overrides.join("") + '</Types>',
  );
}

/** Read ZIP metadata and cell XML ranges; never load the entire workbook or media. */
export async function readTechnicalWorkbookParts(source: Blob): Promise<ArrayBuffer> {
  if (!source.size) throw new TechnicalArchiveError("O arquivo está vazio.");
  if (source.size > MAX_TECHNICAL_FILE_BYTES) throw new TechnicalArchiveError("Selecione uma planilha de até 300 MB.");
  const reader = new ZipReader(new BlobReader(source), { useWebWorkers: false, checkCrc32: true });
  try {
    const entries = (await reader.getEntries()).filter((entry): entry is FileEntry => !entry.directory && isCellDataPart(entry.filename));
    if (!entries.some((entry) => entry.filename.toLowerCase() === "xl/workbook.xml") ||
        !entries.some((entry) => entry.filename.toLowerCase() === "[content_types].xml")) {
      throw new TechnicalArchiveError("Arquivo Excel inválido. Abra o arquivo no Excel e salve novamente como .xlsx.");
    }
    const names = new Set<string>();
    let declaredBytes = 0;
    for (const entry of entries) {
      const key = entry.filename.toLowerCase();
      if (names.has(key) || entry.encrypted) {
        throw new TechnicalArchiveError("A planilha possui dados duplicados ou protegidos. Salve uma nova cópia .xlsx sem senha.");
      }
      names.add(key);
      declaredBytes += entry.uncompressedSize;
      if (!Number.isSafeInteger(entry.uncompressedSize) || entry.uncompressedSize < 0 || declaredBytes > MAX_CELL_PACKAGE_BYTES || names.size > MAX_CELL_PACKAGE_ENTRIES) {
        throw new TechnicalArchiveError("Os dados das células e estilos são muito grandes. Salve uma cópia contendo apenas os códigos e os dados técnicos.");
      }
    }
    const writer = new ZipWriter(new Uint8ArrayWriter(), { useWebWorkers: false, level: 0, dataDescriptor: false });
    let extractedBytes = 0;
    for (const entry of entries) {
      if (entry.filename.toLowerCase() === "[content_types].xml") continue;
      const bytes = await entry.getData(new Uint8ArrayWriter(), {
        useWebWorkers: false,
        checkCrc32: true,
        onprogress: (loaded) => {
          if (extractedBytes + loaded > MAX_CELL_PACKAGE_BYTES) {
            throw new TechnicalArchiveError("Os dados das células excedem o tamanho disponível para leitura.");
          }
        },
      });
      extractedBytes += bytes.byteLength;
      await writer.add(entry.filename, new Uint8ArrayReader(bytes));
    }
    // The original manifest also declares discarded parts (people, metadata,
    // drawings). SheetJS follows those declarations even when reading only cells.
    await writer.add("[Content_Types].xml", new Uint8ArrayReader(cellContentTypes(entries)));
    const content = await writer.close();
    return content.buffer.slice(content.byteOffset, content.byteOffset + content.byteLength) as ArrayBuffer;
  } catch (error) {
    if (error instanceof TechnicalArchiveError) throw error;
    throw new Error("Não foi possível ler o Excel. Verifique se o arquivo está íntegro e sem senha e use um navegador atualizado.");
  } finally {
    await reader.close();
  }
}
