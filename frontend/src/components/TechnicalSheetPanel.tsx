import { useRef, useState } from "react";
import { ApiRequestError, importTechnicalSheet, previewTechnicalSheet } from "../lib/catalog-api";
import type { TechnicalSheetPreview } from "../types";
import { MAX_TECHNICAL_FILE_BYTES } from "../lib/technical-sheet-limits";

interface Props {
  onApplied: () => Promise<void>;
  onUnauthorized: () => Promise<void>;
}

const STATUS_LABELS = { updated: "Será atualizado", unchanged: "Sem alteração", invalid: "Corrigir linha" };
const PAGE_SIZE = 30;

export default function TechnicalSheetPanel({ onApplied, onUnauthorized }: Props): JSX.Element {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [sheet, setSheet] = useState("");
  const [preview, setPreview] = useState<TechnicalSheetPreview | null>(null);
  const [busy, setBusy] = useState<"read" | "apply" | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [applied, setApplied] = useState(false);
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);

  async function reportError(cause: unknown): Promise<void> {
    setError(cause instanceof Error ? cause.message : "Não foi possível ler a planilha. Tente novamente.");
    if (cause instanceof ApiRequestError && cause.status === 401) await onUnauthorized();
  }

  async function readFile(selected: File, selectedSheet?: string): Promise<void> {
    setPreview(null);
    setError("");
    setSuccess("");
    setApplied(false);
    setPage(0);
    setFilter("all");
    if (!selected.name.toLowerCase().endsWith(".xlsx")) {
      setError("Selecione uma planilha .xlsx. Se o arquivo for .xls, salve uma cópia como .xlsx no Excel.");
      return;
    }
    if (selected.size > MAX_TECHNICAL_FILE_BYTES) {
      setError("A planilha deve ter no máximo 300 MB.");
      return;
    }
    setBusy("read");
    try {
      const result = await previewTechnicalSheet(selected, selectedSheet);
      setPreview(result);
      setSheets(result.sheets);
      setSheet(result.sheet);
    } catch (cause) {
      await reportError(cause);
    } finally {
      setBusy(null);
    }
  }

  async function applyData(): Promise<void> {
    if (!file || !preview || busy || applied) return;
    setBusy("apply");
    setError("");
    setSuccess("");
    try {
      const result = await importTechnicalSheet(file, preview);
      setApplied(true);
      setSuccess(`Dados técnicos de ${result.updated_count} produto(s) atualizados. ${result.unchanged_count} sem alteração e ${result.invalid_count} linha(s) ignorada(s).`);
      try {
        await onApplied();
      } catch {
        setError("Os dados foram salvos. Atualize o painel para consultar os produtos atualizados.");
      }
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.status === 409) setPreview(null);
      await reportError(cause);
    } finally {
      setBusy(null);
    }
  }

  const rows = (preview?.rows || []).filter((row) => filter === "all" || row.status === filter);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));

  return (
    <section className="admin-panel technical-sheet-panel" aria-labelledby="technical-sheet-title" aria-busy={Boolean(busy)}>
      <div className="admin-panel-head">
        <div>
          <h2 id="technical-sheet-title">Leitor de dados técnicos</h2>
          <p className="admin-auth-copy">Anexe o Excel e confira os dados antes de atualizar as especificações dos produtos pelo código.</p>
        </div>
        <a className="export-button is-secondary" href="/modelo-dados-tecnicos.xlsx" download>Baixar modelo Excel</a>
      </div>
      <div className="admin-status-box">
        <strong>Modelo de cadastro Nitrolux</strong>
        <p>Use o mesmo formato do arquivo <b>teste.xlsx</b>: cabeçalhos na <b>linha 3</b>, produtos a partir da <b>linha 4</b> e código na <b>coluna B</b>. Mantenha as colunas nas posições originais.</p>
        <p>A leitura usa a <b>Ficha técnica (L)</b>, as características e medidas de <b>M a AC</b>, a <b>Embalagem (AD a AH)</b>, a <b>Caixa master (AI a AO)</b>, o <b>código Inmetro (G)</b> e a <b>Cubagem (AS)</b>.</p>
        <span className="admin-status-meta">Formato .xlsx, até 300 MB e 10.000 produtos por aba. Use valores fixos. Para preservar zeros à esquerda, formate o código como texto.</span>
        <span className="admin-status-meta">As colunas de fotos AP, AQ e AR são ignoradas, inclusive quando contêm erros. Planilhas com imagens são aceitas.</span>
        <span className="admin-status-meta">A aplicação substitui as especificações dos produtos válidos. Nomes, fotos e os demais dados do cadastro são preservados. Linhas com problemas são ignoradas.</span>
      </div>
      <div className="technical-sheet-upload">
        <h3>Anexe sua planilha aqui</h3>
        <p>Selecione o arquivo Excel no computador ou celular. A prévia aparece abaixo.</p>
        <input ref={fileInputRef} className="sr-only" id="technical-sheet-file" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" aria-label="Planilha Excel de dados técnicos" aria-describedby="technical-sheet-file-help" disabled={Boolean(busy)} onChange={(event) => {
          const selected = event.target.files?.[0];
          if (!selected) return;
          setFile(selected);
          setSheets([]);
          setSheet("");
          void readFile(selected);
        }} />
        <button type="button" className="export-button technical-sheet-choose" disabled={Boolean(busy)} onClick={() => fileInputRef.current?.click()}>
          {busy === "read" ? "Lendo planilha..." : file ? "Trocar planilha Excel" : "Anexar planilha Excel"}
        </button>
        <span className="admin-status-meta" id="technical-sheet-file-help">Arquivo .xlsx de até 300 MB</span>
      </div>
      <div className="admin-inline-actions technical-sheet-actions">
        {sheets.length > 1 && (
          <label className="technical-sheet-file">
            <span>Aba da planilha</span>
            <select value={sheet} disabled={Boolean(busy)} onChange={(event) => {
              setSheet(event.target.value);
              if (file) void readFile(file, event.target.value);
            }}>
              {sheets.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
        )}
        {file && <button type="button" className="export-button is-secondary" disabled={Boolean(busy)} onClick={() => void readFile(file, sheet || undefined)}>Ler novamente</button>}
      </div>
      {file && <p className="admin-status-meta">Arquivo selecionado: {file.name}</p>}
      {busy === "read" && <p role="status">Preparando a planilha e conferindo os códigos dos produtos. Arquivos maiores podem levar alguns segundos...</p>}
      {error && <div className="banner banner-warning" role="alert">{error}</div>}
      {success && <div className="banner banner-success" role="status">{success}</div>}
      {preview && (
        <>
          <div className="admin-stats-grid" aria-label="Resumo da leitura">
            <article className="stat-card"><strong>{preview.updated_count}</strong><span>{applied ? "Produtos atualizados" : "Produtos para atualizar"}</span></article>
            <article className="stat-card"><strong>{preview.unchanged_count}</strong><span>Sem alteração</span></article>
            <article className="stat-card"><strong>{preview.invalid_count}</strong><span>Linhas para corrigir</span></article>
          </div>
          {preview.invalid_count > 0 && <p className="admin-auth-copy">Confira as linhas para corrigir. Ao aplicar, somente os {preview.updated_count} produtos válidos serão atualizados.</p>}
          <div className="admin-panel-head">
            <h3>Prévia: {preview.sheet}</h3>
            <label className="technical-sheet-file">
              <span>Exibir linhas</span>
              <select value={filter} onChange={(event) => { setFilter(event.target.value); setPage(0); }}>
                <option value="all">Todas ({preview.total_rows})</option>
                <option value="updated">Para atualizar ({preview.updated_count})</option>
                <option value="invalid">Para corrigir ({preview.invalid_count})</option>
                <option value="unchanged">Sem alteração ({preview.unchanged_count})</option>
              </select>
            </label>
          </div>
          <div className="technical-sheet-table-wrap" role="region" aria-label="Dados técnicos encontrados" tabIndex={0}>
            <table className="technical-sheet-table">
              <caption className="sr-only">Comparação dos dados atuais com os dados da planilha</caption>
              <thead><tr><th scope="col">Linha / produto</th><th scope="col">Dados atuais</th><th scope="col">Dados da planilha</th><th scope="col">Resultado</th></tr></thead>
              <tbody>
                {rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((row) => (
                  <tr key={row.row}>
                    <th scope="row"><small>Linha {row.row}</small><strong>#{row.code || "Sem código"}</strong><span>{row.name || "Produto não identificado"}</span></th>
                    <td>{row.previous_specs || "Sem dados técnicos"}</td>
                    <td>{row.specs || "Sem dados preenchidos"}</td>
                    <td><strong>{applied && row.status === "updated" ? "Atualizado" : STATUS_LABELS[row.status]}</strong>{row.issues.map((issue) => <p key={issue}>{issue}</p>)}</td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={4}>Nenhuma linha neste filtro.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="admin-inline-actions">
            <button type="button" className="export-button is-secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Anterior</button>
            <span role="status">Página {page + 1} de {pages} · {rows.length} linhas</span>
            <button type="button" className="export-button is-secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Próxima</button>
          </div>
          <div className="admin-inline-actions">
            <button type="button" className="export-button" disabled={Boolean(busy) || applied || preview.updated_count === 0} onClick={() => void applyData()}>
              {busy === "apply" ? "Aplicando dados..." : applied ? "Dados aplicados" : `Aplicar dados técnicos (${preview.updated_count})`}
            </button>
          </div>
        </>
      )}
      {!preview && !busy && !error && <p className="admin-auth-copy">Selecione uma planilha para ver a prévia. O modelo para download usa as mesmas colunas; preencha os produtos a partir da linha 4.</p>}
    </section>
  );
}
