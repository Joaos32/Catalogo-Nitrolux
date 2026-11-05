import { MAX_TECHNICAL_FILE_BYTES } from "./technical-sheet-limits";

const preparedFiles = new WeakMap<File, Promise<ArrayBuffer>>();

/** Reuse the exact same prepared bytes when applying the reviewed preview. */
export function prepareTechnicalSheet(file: File): Promise<ArrayBuffer> {
  const existing = preparedFiles.get(file);
  if (existing) return existing;
  const pending = prepare(file).catch((error) => {
    preparedFiles.delete(file);
    throw error;
  });
  preparedFiles.set(file, pending);
  return pending;
}

async function prepare(file: File): Promise<ArrayBuffer> {
  if (!file.name.toLowerCase().endsWith(".xlsx")) throw new Error("Selecione uma planilha Excel .xlsx.");
  if (file.size > MAX_TECHNICAL_FILE_BYTES) throw new Error("Selecione uma planilha de até 300 MB.");
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./technical-sheet.worker.ts", import.meta.url), { type: "module" });
    const finish = () => { clearTimeout(timer); worker.terminate(); };
    const timer = setTimeout(() => {
      finish();
      reject(new Error("A leitura demorou mais que o esperado. Feche outras abas e tente novamente."));
    }, 120_000);
    worker.onmessage = (event: MessageEvent<{ content?: ArrayBuffer; error?: string }>) => {
      finish();
      if (event.data.error) reject(new Error(event.data.error));
      else if (event.data.content) resolve(event.data.content);
      else reject(new Error("Não foi possível preparar a planilha."));
    };
    worker.onerror = () => {
      finish();
      reject(new Error("Não foi possível preparar a planilha. Atualize a página e tente novamente."));
    };
    worker.postMessage(file);
  });
}
