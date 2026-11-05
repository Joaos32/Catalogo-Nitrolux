import { read, utils, write, type CellObject, type WorkSheet } from "xlsx";
import { MAX_TECHNICAL_FILE_BYTES, MAX_TECHNICAL_UPLOAD_BYTES } from "./technical-sheet-limits";

/** Keep the original cells and coordinates; discard images and presentation data. */
export function compactTechnicalWorkbook(source: ArrayBuffer): ArrayBuffer {
  if (!source.byteLength) throw new Error("O arquivo está vazio.");
  if (source.byteLength > MAX_TECHNICAL_FILE_BYTES) {
    throw new Error("Selecione uma planilha de até 300 MB.");
  }
  const signature = new Uint8Array(source, 0, Math.min(4, source.byteLength));
  if (signature[0] !== 0x50 || signature[1] !== 0x4b || signature[2] !== 3 || signature[3] !== 4) {
    throw new Error("Arquivo Excel inválido. Abra o arquivo no Excel e salve novamente como .xlsx.");
  }
  let original;
  try {
    original = read(source, { type: "array", cellNF: true, cellHTML: false, cellText: false, cellStyles: false, cellFormula: true, sheetStubs: true });
  } catch {
    throw new Error("Não foi possível abrir a planilha. Verifique se o arquivo .xlsx está íntegro e sem senha.");
  }
  if (!original.SheetNames.length || original.SheetNames.length > 20) {
    throw new Error("Use uma pasta de trabalho com 1 a 20 abas.");
  }
  const compact = utils.book_new();
  let totalCharacters = 0;
  for (const name of original.SheetNames) {
    const sheet: WorkSheet = {};
    let maxRow = 0;
    let maxColumn = 0;
    for (const [address, cell] of Object.entries(original.Sheets[name])) {
      if (address.startsWith("!") || !cell || (cell.v == null && !cell.f) || (cell.v === "" && !cell.f)) continue;
      const position = utils.decode_cell(address);
      if (position.r >= 10020 || position.c >= 100) {
        throw new Error(`A aba "${name}" excede o limite de 10.000 produtos ou 100 colunas. Nenhuma linha foi enviada.`);
      }
      const valueLength = String(cell.v ?? "").length;
      if (valueLength > 8000) throw new Error(`Aba "${name}", célula ${address}: o texto excede 8.000 caracteres.`);
      totalCharacters += valueLength;
      if (totalCharacters > 16 * 1024 * 1024) {
        throw new Error("As células da planilha contêm dados demais. Selecione uma cópia com apenas os dados técnicos dos produtos.");
      }
      // XML normalizes line endings. SheetJS otherwise writes carriage returns
      // as escape sequences that the server can expose as literal cell text.
      const value = typeof cell.v === "string" ? cell.v.replace(/\r\n?/g, "\n") : cell.v;
      const copied: CellObject = { t: cell.t, v: value };
      // Preserve formulas for the server to flag, and number formats for leading zeros and dates.
      if (cell.f) {
        copied.f = cell.f;
        if (copied.t === "z") copied.t = "n";
      }
      if (cell.z) copied.z = cell.z;
      sheet[address] = copied;
      maxRow = Math.max(maxRow, position.r);
      maxColumn = Math.max(maxColumn, position.c);
    }
    sheet["!ref"] = utils.encode_range({ s: { r: 0, c: 0 }, e: { r: maxRow, c: maxColumn } });
    utils.book_append_sheet(compact, sheet, name);
  }
  const output = write(compact, { type: "array", bookType: "xlsx", compression: true, bookSST: true }) as ArrayBuffer;
  if (output.byteLength > MAX_TECHNICAL_UPLOAD_BYTES) {
    throw new Error("Os dados das células ainda excedem o limite de envio após a preparação. Salve uma cópia contendo apenas os códigos e os dados técnicos.");
  }
  return output;
}
