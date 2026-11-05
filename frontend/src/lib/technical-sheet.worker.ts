import { compactTechnicalWorkbook } from "./technical-sheet-workbook";
import { readTechnicalWorkbookParts } from "./technical-sheet-archive";

const workerScope = self as unknown as {
  onmessage: (event: MessageEvent<File>) => Promise<void>;
  postMessage: (message: { content?: ArrayBuffer; error?: string }, transfer?: Transferable[]) => void;
};

workerScope.onmessage = async (event) => {
  try {
    const cells = await readTechnicalWorkbookParts(event.data);
    const content = compactTechnicalWorkbook(cells);
    workerScope.postMessage({ content }, [content]);
  } catch (error) {
    workerScope.postMessage({ error: error instanceof Error ? error.message : "Não foi possível preparar a planilha." });
  }
};
