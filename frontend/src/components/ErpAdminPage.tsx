import { type ChangeEvent, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ApiRequestError,
  createRepresentativePasswordReset,
  deleteRepresentativeUser,
  fetchAdminSession,
  fetchErpFilePreview,
  fetchErpFiles,
  fetchErpProducts,
  fetchRepresentativeUsers,
  fetchErpStatus,
  importErpFileFromPath,
  loginAdminWithPassword,
  logoutAdminSession,
  saveRepresentativeUser,
  saveErpProduct,
  stageErpJsonFile,
} from "../lib/catalog-api";
import { normalizeText } from "../lib/catalog-products";
import type {
  ErpPreviewChangeRecord,
  ErpPreviewChangeSummary,
  ProductRecord,
  RepresentativeAdminUser,
} from "../types";

interface ErpProductDraft {
  code: string;
  name: string;
  category: string;
  description: string;
  specs: string;
  coverUrl: string;
  whiteUrl: string;
  ambientUrl: string;
  measuresUrl: string;
  deptCode: string;
  sectionCode: string;
  extraJson: string;
}

interface NoticeState {
  tone: "success" | "warning" | "info";
  text: string;
}

interface RepresentativeDraft {
  currentEmail: string;
  email: string;
  name: string;
  password: string;
}

const EMPTY_DRAFT: ErpProductDraft = {
  code: "",
  name: "",
  category: "",
  description: "",
  specs: "",
  coverUrl: "",
  whiteUrl: "",
  ambientUrl: "",
  measuresUrl: "",
  deptCode: "",
  sectionCode: "",
  extraJson: "",
};

const EMPTY_REPRESENTATIVE_DRAFT: RepresentativeDraft = {
  currentEmail: "",
  email: "",
  name: "",
  password: "",
};

const CORE_PRODUCT_KEYS = new Set(
  ["código", "nome", "categoria", "descrição", "especificações", "urlfoto", "fotobranco", "fotoambient", "fotomedidas", "codepto", "codsec"].map((value) => normalizeText(value))
);

function normalizeKey(value: string): string {
  return normalizeText(value).replace(/[^a-z0-9]+/g, "");
}

function getRecordField(item: ProductRecord, aliases: string[]): string {
  const lookup: Record<string, unknown> = {};
  Object.entries(item || {}).forEach(([key, value]) => {
    lookup[normalizeKey(key)] = value;
  });
  for (const alias of aliases) {
    const value = lookup[normalizeKey(alias)];
    if (value === undefined || value === null) continue;
    const rendered = String(value).trim();
    if (rendered) return rendered;
  }
  return "";
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function productToDraft(product: ProductRecord): ErpProductDraft {
  const extraEntries = Object.entries(product || {}).filter(([key]) => !CORE_PRODUCT_KEYS.has(normalizeKey(key)));
  const extraPayload = Object.fromEntries(extraEntries);
  return {
    code: getRecordField(product, ["Codigo"]),
    name: getRecordField(product, ["Nome"]),
    category: getRecordField(product, ["Categoria"]),
    description: getRecordField(product, ["Descricao"]),
    specs: getRecordField(product, ["Especificacoes"]),
    coverUrl: getRecordField(product, ["URLFoto"]),
    whiteUrl: getRecordField(product, ["FotoBranco"]),
    ambientUrl: getRecordField(product, ["FotoAmbient"]),
    measuresUrl: getRecordField(product, ["FotoMedidas"]),
    deptCode: getRecordField(product, ["CODEPTO"]),
    sectionCode: getRecordField(product, ["CODSEC"]),
    extraJson: extraEntries.length > 0 ? JSON.stringify(extraPayload, null, 2) : "",
  };
}

function buildPayloadFromDraft(draft: ErpProductDraft): ProductRecord {
  let extraPayload: Record<string, unknown> = {};
  const extraJson = String(draft.extraJson || "").trim();
  if (extraJson) {
    const parsed = JSON.parse(extraJson) as unknown;
    if (!isPlainRecord(parsed)) {
      throw new Error("A seção de atributos extras precisa conter um objeto JSON.");
    }
    extraPayload = parsed;
  }
  return {
    ...extraPayload,
    Codigo: draft.code.trim(),
    Nome: draft.name.trim(),
    Categoria: draft.category.trim(),
    Descricao: draft.description.trim(),
    Especificacoes: draft.specs.trim(),
    URLFoto: draft.coverUrl.trim(),
    FotoBranco: draft.whiteUrl.trim(),
    FotoAmbient: draft.ambientUrl.trim(),
    FotoMedidas: draft.measuresUrl.trim(),
    CODEPTO: draft.deptCode.trim(),
    CODSEC: draft.sectionCode.trim(),
  };
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "Não disponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function formatBytes(value: number | null | undefined): string {
  if (!Number.isFinite(value) || Number(value) <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value);
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) return error.message || fallback;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function buildSearchBlob(product: ProductRecord): string {
  return normalizeText([getRecordField(product, ["Codigo"]), getRecordField(product, ["Nome"]), getRecordField(product, ["Categoria"]), getRecordField(product, ["Descricao"])].join(" "));
}

function representativeToDraft(user: RepresentativeAdminUser): RepresentativeDraft {
  return {
    currentEmail: user.email,
    email: user.email,
    name: user.name,
    password: "",
  };
}

function getChangeTypeLabel(changeType: ErpPreviewChangeRecord["change_type"]): string {
  if (changeType === "added") return "Novo";
  if (changeType === "removed") return "Removido";
  return "Atualizado";
}

function getChangeSummaryTitle(summary: ErpPreviewChangeSummary | null | undefined): string {
  const comparedTo = String(summary?.compared_to_name || "").trim();
  if (comparedTo) return `Comparado com ${comparedTo}`;
  return "Sem JSON ativo para comparar";
}

function getChangeSummaryMeta(summary: ErpPreviewChangeSummary | null | undefined): string {
  const comparedPath = String(summary?.compared_to_path || "").trim();
  if (comparedPath) return comparedPath;
  return "A primeira implantação vai entrar como novo conteudo do catálogo.";
}

function getChangeDetails(change: ErpPreviewChangeRecord): string {
  if (change.change_type === "updated") {
    const previousBits = [change.previous_name, change.previous_category].filter(Boolean);
    const fields = change.changed_fields.length > 0 ? `Campos alterados: ${change.changed_fields.join(", ")}` : "";
    return [previousBits.length > 0 ? `Antes: ${previousBits.join(" | ")}` : "", fields].filter(Boolean).join(" | ");
  }
  if (change.change_type === "added") {
    return "Produto novo identificado neste JSON.";
  }
  return "Produto presente no catálogo ativo e ausente neste JSON.";
}

export default function ErpAdminPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<ErpProductDraft>(EMPTY_DRAFT);
  const [representativeDraft, setRepresentativeDraft] = useState<RepresentativeDraft>(EMPTY_REPRESENTATIVE_DRAFT);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [busyFilePath, setBusyFilePath] = useState("");
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [busyRepresentativeEmail, setBusyRepresentativeEmail] = useState("");
  const [busyPasswordResetEmail, setBusyPasswordResetEmail] = useState("");
  const [passwordResetCode, setPasswordResetCode] = useState<{
    email: string;
    code: string;
    expiresAt: string;
  } | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingRepresentative, setIsSavingRepresentative] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [activeAdminSection, setActiveAdminSection] = useState<"deploy" | "representatives" | "products">("deploy");

  const sessionQuery = useQuery({ queryKey: ["admin-session"], queryFn: fetchAdminSession, retry: false });
  const protectionEnabled = Boolean(sessionQuery.data?.protection_enabled);
  const authenticated = Boolean(sessionQuery.data?.authenticated);
  const canAccessPanel = authenticated || !protectionEnabled;

  const statusQuery = useQuery({ queryKey: ["erp-admin-status"], queryFn: () => fetchErpStatus(), enabled: canAccessPanel, retry: false });
  const filesQuery = useQuery({ queryKey: ["erp-admin-files"], queryFn: () => fetchErpFiles(), enabled: canAccessPanel, retry: false });
  const productsQuery = useQuery({ queryKey: ["erp-admin-products"], queryFn: () => fetchErpProducts(), enabled: canAccessPanel, retry: false });
  const representativeUsersQuery = useQuery({
    queryKey: ["erp-admin-representatives"],
    queryFn: () => fetchRepresentativeUsers(),
    enabled: canAccessPanel,
    retry: false,
  });
  const previewQuery = useQuery({
    queryKey: ["erp-file-preview", selectedFilePath],
    queryFn: () => fetchErpFilePreview(selectedFilePath),
    enabled: canAccessPanel && Boolean(selectedFilePath),
    retry: false,
  });

  const files = useMemo(() => filesQuery.data || [], [filesQuery.data]);
  const products = useMemo(() => productsQuery.data?.products || [], [productsQuery.data]);
  const representativeUsers = useMemo(
    () => representativeUsersQuery.data?.users || [],
    [representativeUsersQuery.data]
  );
  const filteredProducts = useMemo(() => {
    const normalizedSearch = normalizeText(search);
    if (!normalizedSearch) return products;
    return products.filter((product) => buildSearchBlob(product).includes(normalizedSearch));
  }, [products, search]);
  const selectedFile = useMemo(() => files.find((file) => file.path === selectedFilePath) || null, [files, selectedFilePath]);
  const representativeSummary = representativeUsersQuery.data;
  const selectedRepresentative = useMemo(
    () =>
      representativeUsers.find((user) => user.email === representativeDraft.currentEmail) || null,
    [representativeDraft.currentEmail, representativeUsers]
  );

  useEffect(() => {
    if (!canAccessPanel) return;
    if (files.length === 0) {
      if (selectedFilePath) setSelectedFilePath("");
      return;
    }
    if (files.some((file) => file.path === selectedFilePath)) return;
    const preferred = files.find((file) => file.is_deployed_source) || files.find((file) => file.is_active) || files[0];
    if (preferred?.path) setSelectedFilePath(preferred.path);
  }, [canAccessPanel, files, selectedFilePath]);

  const refreshAdminData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-session"] }),
      queryClient.invalidateQueries({ queryKey: ["erp-admin-status"] }),
      queryClient.invalidateQueries({ queryKey: ["erp-admin-files"] }),
      queryClient.invalidateQueries({ queryKey: ["erp-admin-products"] }),
      queryClient.invalidateQueries({ queryKey: ["erp-admin-representatives"] }),
      queryClient.invalidateQueries({ queryKey: ["erp-file-preview"] }),
    ]);
  };

  const handleUnauthorized = async () => {
    await queryClient.invalidateQueries({ queryKey: ["admin-session"] });
  };

  const handleActivateFile = async (filePath: string, label: string) => {
    if (!filePath) return;
    setBusyFilePath(filePath);
    setNotice(null);
    try {
      const result = await importErpFileFromPath(filePath);
      await refreshAdminData();
      setSelectedFilePath(filePath);
      setNotice({ tone: "success", text: `${label} foi implantado com ${result.products_imported} produtos.` });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) await handleUnauthorized();
      setNotice({ tone: "warning", text: getErrorMessage(error, "Não foi possível implantar o JSON selecionado.") });
    } finally {
      setBusyFilePath("");
    }
  };

  const handleStageFileUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setIsUploading(true);
    setNotice(null);
    try {
      const result = await stageErpJsonFile(file);
      queryClient.setQueryData(["erp-file-preview", result.path], result);
      setSelectedFilePath(result.path);
      await refreshAdminData();
      setNotice({ tone: "success", text: `${file.name} foi enviado para revisão. Confira a prévia e implante quando estiver pronto.` });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) await handleUnauthorized();
      setNotice({ tone: "warning", text: getErrorMessage(error, "Não foi possível enviar o JSON para revisão.") });
    } finally {
      setIsUploading(false);
    }
  };

  const handleSaveProduct = async () => {
    const code = draft.code.trim();
    if (!code) {
      setNotice({ tone: "warning", text: "Informe o código do produto antes de salvar." });
      return;
    }
    setIsSaving(true);
    setNotice(null);
    try {
      const result = await saveErpProduct(code, buildPayloadFromDraft(draft));
      await refreshAdminData();
      setDraft(productToDraft(result.product));
      setNotice({ tone: "success", text: result.created ? `Produto ${code} incluído com sucesso no JSON ativo.` : `Produto ${code} atualizado com sucesso no JSON ativo.` });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) await handleUnauthorized();
      setNotice({ tone: "warning", text: getErrorMessage(error, "Não foi possível salvar o produto no JSON.") });
    } finally {
      setIsSaving(false);
    }
  };

  const resetRepresentativeDraft = () => {
    setRepresentativeDraft(EMPTY_REPRESENTATIVE_DRAFT);
  };

  const handleSaveRepresentative = async () => {
    const targetEmail = representativeDraft.currentEmail || representativeDraft.email;
    const normalizedEmail = targetEmail.trim().toLowerCase();
    const normalizedName = representativeDraft.name.trim();
    const normalizedPassword = representativeDraft.password.trim();

    if (!normalizedEmail) {
      setNotice({ tone: "warning", text: "Informe o e-mail do representante." });
      return;
    }
    if (!normalizedName) {
      setNotice({ tone: "warning", text: "Informe o nome do representante." });
      return;
    }
    if (!representativeDraft.currentEmail && !normalizedPassword) {
      setNotice({ tone: "warning", text: "Informe uma senha para concluir o cadastro do representante." });
      return;
    }

    setIsSavingRepresentative(true);
    setNotice(null);
    try {
      const result = await saveRepresentativeUser({
        email: normalizedEmail,
        name: normalizedName,
        password: normalizedPassword || undefined,
      });
      await refreshAdminData();
      setRepresentativeDraft({
        currentEmail: result.user.email,
        email: result.user.email,
        name: result.user.name,
        password: "",
      });
      setNotice({
        tone: "success",
        text: result.created
          ? `Representante ${result.user.email} cadastrado com sucesso.`
          : `Representante ${result.user.email} atualizado com sucesso.`,
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) await handleUnauthorized();
      setNotice({
        tone: "warning",
        text: getErrorMessage(error, "Não foi possível salvar o representante."),
      });
    } finally {
      setIsSavingRepresentative(false);
    }
  };

  const handleDeleteRepresentative = async (user: RepresentativeAdminUser) => {
    if (!user.managed) {
      setNotice({
        tone: "info",
        text: "Representantes configurados por ambiente são somente leitura no painel.",
      });
      return;
    }
    if (typeof window !== "undefined") {
      const confirmed = window.confirm(`Excluir o acesso de ${user.email}?`);
      if (!confirmed) return;
    }

    setBusyRepresentativeEmail(user.email);
    setNotice(null);
    try {
      await deleteRepresentativeUser(user.email);
      await refreshAdminData();
      if (representativeDraft.currentEmail === user.email) {
        resetRepresentativeDraft();
      }
      setNotice({ tone: "success", text: `Representante ${user.email} removido com sucesso.` });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) await handleUnauthorized();
      setNotice({
        tone: "warning",
        text: getErrorMessage(error, "Não foi possível excluir o representante."),
      });
    } finally {
      setBusyRepresentativeEmail("");
    }
  };

  const handleCreatePasswordReset = async (user: RepresentativeAdminUser) => {
    setBusyPasswordResetEmail(user.email);
    setPasswordResetCode(null);
    setNotice(null);
    try {
      const result = await createRepresentativePasswordReset(user.email);
      await refreshAdminData();
      setPasswordResetCode({
        email: result.user.email,
        code: result.reset_code,
        expiresAt: result.expires_at,
      });
      setNotice({
        tone: "success",
        text: `Código de recuperação gerado para ${result.user.email}. Entregue esse código ao representante.`,
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) await handleUnauthorized();
      setNotice({
        tone: "warning",
        text: getErrorMessage(error, "Não foi possível gerar o código de recuperação."),
      });
    } finally {
      setBusyPasswordResetEmail("");
    }
  };

  const handlePasswordLogin = async () => {
    const email = loginEmail.trim();
    const password = loginPassword.trim();
    if (sessionQuery.data?.password_login_requires_email && !email) {
      setNotice({ tone: "warning", text: "Informe o e-mail autorizado para abrir o painel interno." });
      return;
    }
    if (!password) {
      setNotice({ tone: "warning", text: "Informe a senha de acesso para abrir o painel interno." });
      return;
    }
    setIsLoggingIn(true);
    setNotice(null);
    try {
      await loginAdminWithPassword(email, password);
      setLoginEmail("");
      setLoginPassword("");
      await refreshAdminData();
      setNotice({ tone: "success", text: "Login realizado com sucesso." });
    } catch (error) {
      setNotice({ tone: "warning", text: getErrorMessage(error, "Não foi possível entrar no painel.") });
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    setIsLoggingOut(true);
    setNotice(null);
    try {
      await logoutAdminSession();
      setDraft(EMPTY_DRAFT);
      resetRepresentativeDraft();
      setSelectedFilePath("");
      await refreshAdminData();
      setNotice({ tone: "info", text: "Sessão encerrada." });
    } catch (error) {
      setNotice({ tone: "warning", text: getErrorMessage(error, "Não foi possível encerrar a sessão.") });
    } finally {
      setIsLoggingOut(false);
    }
  };

  const loading =
    sessionQuery.isLoading ||
    (canAccessPanel &&
      (statusQuery.isLoading ||
        filesQuery.isLoading ||
        productsQuery.isLoading ||
        representativeUsersQuery.isLoading));
  const previewLoading = previewQuery.isLoading || previewQuery.isFetching;
  const combinedError = [statusQuery, filesQuery, previewQuery, productsQuery, representativeUsersQuery]
    .filter((query) => query.isError)
    .map((query) => getErrorMessage(query.error, "Falha ao carregar dados administrativos."))
    .filter(Boolean)
    .join(" ");

  const renderChangeSummarySection = (
    summary: ErpPreviewChangeSummary | null | undefined,
    options: {
      eyebrow: string;
      title: string;
      emptyTitle: string;
      emptyCopy: string;
    }
  ): JSX.Element => {
    if (!summary) {
      return (
        <section className="admin-change-section">
          <div className="admin-change-head">
            <div>
              <p className="admin-eyebrow">{options.eyebrow}</p>
              <h3>{options.title}</h3>
            </div>
          </div>
          <div className="admin-status-box">
            <span className="admin-status-label">Resumo</span>
            <strong>{options.emptyTitle}</strong>
            <span className="admin-status-meta">{options.emptyCopy}</span>
          </div>
        </section>
      );
    }

    return (
      <section className="admin-change-section">
        <div className="admin-change-head">
          <div>
            <p className="admin-eyebrow">{options.eyebrow}</p>
            <h3>{options.title}</h3>
          </div>
        </div>
        <div className="admin-preview-grid">
          <div className="admin-status-box">
            <span className="admin-status-label">Novos</span>
            <strong>{summary.added_count}</strong>
            <span className="admin-status-meta">Entram pela primeira vez no catálogo.</span>
          </div>
          <div className="admin-status-box">
            <span className="admin-status-label">Atualizados</span>
            <strong>{summary.updated_count}</strong>
            <span className="admin-status-meta">Já existiam e tiveram campos alterados.</span>
          </div>
          <div className="admin-status-box">
            <span className="admin-status-label">Removidos</span>
            <strong>{summary.removed_count}</strong>
            <span className="admin-status-meta">Estão no catálogo ativo e não vieram neste JSON.</span>
          </div>
          <div className="admin-status-box">
            <span className="admin-status-label">Sem alteração</span>
            <strong>{summary.unchanged_count}</strong>
            <span className="admin-status-meta">Permanecem iguais em relação ao ativo.</span>
          </div>
        </div>
        <div className="admin-status-box">
          <span className="admin-status-label">Comparação</span>
          <strong>{getChangeSummaryTitle(summary)}</strong>
          <span className="admin-status-meta">{getChangeSummaryMeta(summary)}</span>
        </div>
        {summary.changes.length > 0 ? (
          <div className="admin-sample-table" role="list">
            {summary.changes.map((change) => (
              <article key={`${change.change_type}-${change.code}`} className="admin-sample-row admin-change-row" role="listitem">
                <div className="admin-change-copy">
                  <div className="admin-file-title-row">
                    <strong>{change.name}</strong>
                    <span className={`admin-change-chip is-${change.change_type}`}>{getChangeTypeLabel(change.change_type)}</span>
                  </div>
                  <span>{change.category}</span>
                  <small className="admin-change-note">{getChangeDetails(change)}</small>
                </div>
                <small>#{change.code}</small>
              </article>
            ))}
          </div>
        ) : (
          <div className="admin-status-box">
            <span className="admin-status-label">Amostra</span>
            <strong>{options.emptyTitle}</strong>
            <span className="admin-status-meta">{options.emptyCopy}</span>
          </div>
        )}
      </section>
    );
  };

  return (
    <div className="page-shell">
      <div className="bg-orb orb-a" aria-hidden="true"></div>
      <div className="bg-orb orb-b" aria-hidden="true"></div>
      <header className="hero hero-admin">
        <div className="hero-identity">
          <div className="hero-kicker">Painel interno</div>
          <div className="hero-brand" aria-label="Área administrativa do catálogo">
            <p className="hero-brand-name">CENTRAL JSON</p>
            <p className="hero-brand-subtitle">Revisão, implantação e manutenção do arquivo ativo</p>
          </div>
          <div className="hero-admin-actions">
            <button type="button" className="hero-link-button" onClick={() => navigate("/")}>Voltar ao catálogo</button>
            {authenticated && <button type="button" className="hero-link-button" onClick={() => void handleLogout()} disabled={isLoggingOut}>{isLoggingOut ? "Saindo..." : "Sair do painel"}</button>}
          </div>
        </div>
      </header>
      <main
        className="content-wrap admin-content"
        aria-busy={
          loading ||
          previewLoading ||
          isUploading ||
          isSaving ||
          isSavingRepresentative ||
          isLoggingIn ||
          isLoggingOut ||
          Boolean(busyRepresentativeEmail)
        }
      >
        {notice && <div className={`banner banner-${notice.tone}`}>{notice.text}</div>}
        {!canAccessPanel ? (
          <section className="admin-auth-shell">
            <article className="admin-panel admin-auth-panel">
              <div className="admin-panel-head"><div><p className="admin-eyebrow">Acesso restrito</p><h2>Entrar no painel</h2></div></div>
              <p className="admin-auth-copy">Esta área concentra a implantação dos JSONs do ERP e a manutenção do catálogo interno.</p>
              {sessionQuery.data?.password_login_available && sessionQuery.data?.password_login_requires_email && <label className="field"><span>E-mail de acesso</span><input type="email" value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} placeholder="usuario@empresa.com" autoComplete="username" /></label>}
              {sessionQuery.data?.password_login_available && <label className="field"><span>Senha de acesso</span><input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} placeholder="Informe a senha administrativa" autoComplete="current-password" /></label>}
              <div className="admin-inline-actions">
                {sessionQuery.data?.password_login_available && <button type="button" className="export-button" onClick={() => void handlePasswordLogin()} disabled={isLoggingIn}>{isLoggingIn ? "Entrando..." : "Entrar com senha"}</button>}
                {sessionQuery.data?.azure_login_available && <button type="button" className="export-button is-secondary" onClick={() => window.location.assign(`/auth/login?next=${encodeURIComponent("/erp")}`)}>Entrar com Microsoft</button>}
              </div>
            </article>
          </section>
        ) : (
          <>
            {!protectionEnabled && <div className="banner banner-warning">O painel está aberto neste ambiente porque nenhum login administrativo foi configurado no backend.</div>}
            {combinedError && <div className="banner banner-warning">{combinedError}</div>}
            <section className="admin-command-center" aria-label="Resumo administrativo">
              <div className="admin-command-copy">
                <p className="admin-eyebrow">Operação do catálogo</p>
                <h2>Painel administrativo</h2>
                <span>{statusQuery.data?.source_name || "Nenhum JSON ativo identificado"}</span>
              </div>
              <div className="admin-command-metrics" aria-label="Indicadores principais">
                <div>
                  <strong>{statusQuery.data?.products_loaded ?? 0}</strong>
                  <span>Produtos</span>
                </div>
                <div>
                  <strong>{files.length}</strong>
                  <span>JSONs</span>
                </div>
                <div>
                  <strong>{representativeSummary?.total_users ?? 0}</strong>
                  <span>Acessos</span>
                </div>
              </div>
            </section>
            <nav className="admin-workspace-tabs" aria-label="Áreas do painel">
              <button type="button" className={activeAdminSection === "deploy" ? "is-active" : ""} onClick={() => setActiveAdminSection("deploy")}>
                <span>Implantação</span>
                <small>Revisar e ativar JSON</small>
              </button>
              <button type="button" className={activeAdminSection === "representatives" ? "is-active" : ""} onClick={() => setActiveAdminSection("representatives")}>
                <span>Representantes</span>
                <small>Gerenciar acessos</small>
              </button>
              <button type="button" className={activeAdminSection === "products" ? "is-active" : ""} onClick={() => setActiveAdminSection("products")}>
                <span>Produtos</span>
                <small>Editar JSON ativo</small>
              </button>
            </nav>
            {activeAdminSection === "deploy" && (
              <>
            <section className="admin-grid admin-grid-deploy">
              <article className="admin-panel admin-summary-panel">
                <div className="admin-panel-head"><div><p className="admin-eyebrow">Implantação</p><h2>Controle do ambiente</h2></div></div>
                <p className="admin-auth-copy">Envie um novo JSON para revisão, confira a prévia e implante apenas quando o arquivo estiver validado.</p>
                <div className="admin-stats-grid">
                  <article className="stat-card"><strong>{statusQuery.data?.products_loaded ?? 0}</strong><span>Produtos no JSON ativo</span></article>
                  <article className="stat-card"><strong>{files.length}</strong><span>Arquivos encontrados</span></article>
                  <article className="stat-card"><strong>{formatDateTime(statusQuery.data?.updated_at)}</strong><span>Última atualização</span></article>
                </div>
                <div className="admin-status-box"><span className="admin-status-label">Arquivo ativo</span><strong>{statusQuery.data?.path || "Nenhum arquivo resolvido ainda"}</strong><span className="admin-status-meta">Origem: {statusQuery.data?.source_name || "não registrada"}</span></div>
                {renderChangeSummarySection(statusQuery.data?.last_change_summary, {
                  eyebrow: "Última implantação",
                  title: "Mudanças colocadas no catálogo",
                  emptyTitle: "Nenhuma implantação comparativa registrada",
                  emptyCopy: "Assim que um novo JSON for implantado, o painel mostra aqui o que entrou, mudou ou saiu.",
                })}
                <div className="admin-inline-actions">
                  <button type="button" className="export-button" onClick={() => void refreshAdminData()}>Atualizar dados</button>
                  <label className={`export-button admin-upload-button ${isUploading ? "is-disabled" : ""}`}><input type="file" accept=".json,application/json" onChange={(event) => void handleStageFileUpload(event)} disabled={isUploading} />{isUploading ? "Enviando JSON..." : "Enviar JSON para revisão"}</label>
                  <button type="button" className="export-button is-secondary" onClick={() => { setDraft(EMPTY_DRAFT); setNotice(null); setActiveAdminSection("products"); }}>Novo produto</button>
                </div>
              </article>
              <article className="admin-panel admin-preview-panel">
                <div className="admin-panel-head"><div><p className="admin-eyebrow">Prévia</p><h2>{selectedFile?.name || previewQuery.data?.name || "Selecione um arquivo"}</h2></div></div>
                {!selectedFilePath ? <div className="empty-state compact-empty"><h2>Nenhum arquivo selecionado</h2><p>Escolha um JSON da fila para validar a implantação.</p></div> : previewLoading ? <section className="loading-state">Carregando prévia do JSON selecionado...</section> : previewQuery.data ? <>
                  <div className="admin-preview-grid">
                    <div className="admin-status-box"><span className="admin-status-label">Arquivo</span><strong>{previewQuery.data.path}</strong><span className="admin-status-meta">{formatBytes(previewQuery.data.size_bytes)} | atualizado em {formatDateTime(previewQuery.data.updated_at)}</span></div>
                    <div className="admin-status-box"><span className="admin-status-label">Validação</span><strong>{previewQuery.data.products_loaded} produtos válidos</strong><span className="admin-status-meta">{previewQuery.data.records_detected} registros, {previewQuery.data.ignored_records} ignorados</span></div>
                  </div>
                  {renderChangeSummarySection(previewQuery.data.change_summary, {
                    eyebrow: "Comparação",
                    title: "O que este JSON vai alterar",
                    emptyTitle: "Nenhuma mudança detectada",
                    emptyCopy: "Se você implantar este arquivo agora, o catálogo ativo permanece igual.",
                  })}
                  <div className="admin-chip-row">{previewQuery.data.categories.map((category) => <span key={`${category.name}-${category.count}`} className="admin-category-chip">{category.name} ({category.count})</span>)}</div>
                  <div className="admin-sample-table" role="list">{previewQuery.data.sample_products.map((product) => <article key={`${product.Codigo}-${product.Nome}`} className="admin-sample-row" role="listitem"><div><strong>{product.Nome}</strong><span>{product.Categoria}</span></div><small>#{product.Codigo}</small></article>)}</div>
                  <div className="admin-inline-actions"><button type="button" className="export-button" disabled={busyFilePath === selectedFilePath || selectedFile?.is_active} onClick={() => void handleActivateFile(selectedFilePath, previewQuery.data?.name || "O JSON selecionado")}>{busyFilePath === selectedFilePath ? "Implantando..." : selectedFile?.is_active ? "Arquivo ativo" : previewQuery.data.is_deployed_source ? "Reimplantar este JSON" : "Implantar este JSON"}</button></div>
                </> : <div className="empty-state compact-empty"><h2>Prévia indisponível</h2><p>Selecione outro arquivo ou atualize os dados para tentar novamente.</p></div>}
              </article>
            </section>
            <section className="admin-panel">
              <div className="admin-panel-head"><div><p className="admin-eyebrow">Arquivos JSON</p><h2>Fila de implantação</h2></div><span className="result-summary">{filesQuery.isLoading ? "Carregando..." : `${files.length} arquivos disponíveis`}</span></div>
              <div className="admin-file-list" role="list">
                {files.map((file) => {
                  const isSelected = file.path === selectedFilePath;
                  return <article key={file.path} className={`admin-file-card ${file.is_active ? "is-active" : ""} ${isSelected ? "is-selected" : ""}`} role="listitem"><div className="admin-file-copy"><div className="admin-file-title-row"><strong>{file.name}</strong>{file.is_active && <span className="chip chip-code">Ativo</span>}{file.is_deployed_source && <span className="chip chip-category">Última origem</span>}{isSelected && <span className="admin-inline-chip">Selecionado</span>}</div><span>{file.path}</span><small>{formatBytes(file.size_bytes)} | atualizado em {formatDateTime(file.updated_at)}</small></div><div className="admin-file-actions"><button type="button" className="export-button is-secondary" onClick={() => setSelectedFilePath(file.path)}>{isSelected ? "Em revisão" : "Ver prévia"}</button><button type="button" className="export-button" disabled={busyFilePath === file.path || file.is_active} onClick={() => void handleActivateFile(file.path, file.name)}>{busyFilePath === file.path ? "Implantando..." : file.is_active ? "Arquivo ativo" : "Implantar"}</button></div></article>;
                })}
              </div>
            </section>
              </>
            )}
            {activeAdminSection === "representatives" && (
            <section className="admin-grid admin-grid-products">
              <article className="admin-panel">
                <div className="admin-panel-head">
                  <div>
                    <p className="admin-eyebrow">Representantes</p>
                    <h2>Acessos ao catálogo</h2>
                  </div>
                  <span className="result-summary">
                    {representativeUsersQuery.isLoading
                      ? "Carregando..."
                      : `${representativeSummary?.total_users ?? 0} representantes`}
                  </span>
                </div>
                <p className="admin-auth-copy">
                  Cadastre aqui os representantes que podem entrar no catálogo protegido por JWT.
                </p>
                <div className="admin-preview-grid">
                  <div className="admin-status-box">
                    <span className="admin-status-label">Total</span>
                    <strong>{representativeSummary?.total_users ?? 0}</strong>
                    <span className="admin-status-meta">Acessos conhecidos pelo catálogo.</span>
                  </div>
                  <div className="admin-status-box">
                    <span className="admin-status-label">Gerenciados no painel</span>
                    <strong>{representativeSummary?.managed_users ?? 0}</strong>
                    <span className="admin-status-meta">Podem ser editados e removidos por aqui.</span>
                  </div>
                  <div className="admin-status-box">
                    <span className="admin-status-label">Somente leitura</span>
                    <strong>{representativeSummary?.environment_users ?? 0}</strong>
                    <span className="admin-status-meta">Vieram de variáveis de ambiente do servidor.</span>
                  </div>
                </div>
                {passwordResetCode && (
                  <div className="admin-status-box">
                    <span className="admin-status-label">Código de recuperação</span>
                    <strong>{passwordResetCode.code}</strong>
                    <span className="admin-status-meta">
                      Envie para {passwordResetCode.email}. Válido até {formatDateTime(passwordResetCode.expiresAt)}.
                    </span>
                  </div>
                )}
                <div className="admin-file-list" role="list">
                  {representativeUsers.length > 0 ? (
                    representativeUsers.map((user) => {
                      const isSelected = representativeDraft.currentEmail === user.email;
                      const isDeleting = busyRepresentativeEmail === user.email;
                      const isCreatingReset = busyPasswordResetEmail === user.email;
                      return (
                        <article
                          key={`${user.source}-${user.email}`}
                          className={`admin-file-card ${isSelected ? "is-selected" : ""}`}
                          role="listitem"
                        >
                          <div className="admin-file-copy">
                            <div className="admin-file-title-row">
                              <strong>{user.name}</strong>
                              <span className="admin-inline-chip">
                                {user.managed ? "Painel" : "Ambiente"}
                              </span>
                              {!user.managed && <span className="chip chip-category">Somente leitura</span>}
                              {user.password_reset_pending && <span className="chip chip-code">Reset pendente</span>}
                            </div>
                            <span>{user.email}</span>
                            <small>
                              {user.password_reset_pending
                                ? `Código válido até ${formatDateTime(user.password_reset_expires_at)}`
                                : user.managed
                                  ? `Atualizado em ${formatDateTime(user.updated_at)}`
                                  : "Configurado por variável de ambiente no servidor."}
                            </small>
                          </div>
                          <div className="admin-file-actions">
                            {user.managed ? (
                              <>
                                <button
                                  type="button"
                                  className="export-button is-secondary"
                                  onClick={() => void handleCreatePasswordReset(user)}
                                  disabled={isCreatingReset}
                                >
                                  {isCreatingReset ? "Gerando..." : "Gerar código"}
                                </button>
                                <button
                                  type="button"
                                  className="export-button is-secondary"
                                  onClick={() => {
                                    setRepresentativeDraft(representativeToDraft(user));
                                    setNotice({ tone: "info", text: `Representante ${user.email} carregado para edição.` });
                                  }}
                                >
                                  {isSelected ? "Em edição" : "Editar"}
                                </button>
                                <button
                                  type="button"
                                  className="export-button"
                                  onClick={() => void handleDeleteRepresentative(user)}
                                  disabled={isDeleting}
                                >
                                  {isDeleting ? "Excluindo..." : "Excluir"}
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  className="export-button is-secondary"
                                  onClick={() => void handleCreatePasswordReset(user)}
                                  disabled={isCreatingReset}
                                >
                                  {isCreatingReset ? "Gerando..." : "Gerar código"}
                                </button>
                                <button
                                  type="button"
                                  className="export-button is-secondary"
                                  onClick={() =>
                                    setNotice({
                                      tone: "info",
                                      text: `O acesso ${user.email} vem do ambiente. O reset cria uma senha gerenciada pelo painel para este mesmo e-mail.`,
                                    })
                                  }
                                >
                                  Ver observação
                                </button>
                              </>
                            )}
                          </div>
                        </article>
                      );
                    })
                  ) : (
                    <div className="empty-state compact-empty">
                      <h2>Nenhum representante encontrado</h2>
                      <p>Use o formulário ao lado para liberar o primeiro acesso ao catálogo.</p>
                    </div>
                  )}
                </div>
              </article>
              <article className="admin-panel admin-form-panel">
                <div className="admin-panel-head">
                  <div>
                    <p className="admin-eyebrow">Cadastro</p>
                    <h2>
                      {representativeDraft.currentEmail
                        ? `Edição de ${representativeDraft.currentEmail}`
                        : "Novo representante"}
                    </h2>
                  </div>
                </div>
                <p className="admin-auth-copy">
                  O e-mail vira o login do representante. Em edições, deixe a senha em branco para manter a atual.
                </p>
                <div className="admin-form-grid">
                  <label className="field field-span-2">
                    <span>E-mail de acesso</span>
                    <input
                      type="email"
                      value={representativeDraft.email}
                      onChange={(event) =>
                        setRepresentativeDraft((current) => ({ ...current, email: event.target.value }))
                      }
                      placeholder="representante@empresa.com"
                      autoComplete="username"
                      disabled={Boolean(representativeDraft.currentEmail)}
                    />
                  </label>
                  <label className="field field-span-2">
                    <span>Nome do representante</span>
                    <input
                      type="text"
                      value={representativeDraft.name}
                      onChange={(event) =>
                        setRepresentativeDraft((current) => ({ ...current, name: event.target.value }))
                      }
                      placeholder="Nome exibido no acesso do catálogo"
                    />
                  </label>
                  <label className="field field-span-2">
                    <span>{representativeDraft.currentEmail ? "Nova senha (opcional)" : "Senha de acesso"}</span>
                    <input
                      type="password"
                      value={representativeDraft.password}
                      onChange={(event) =>
                        setRepresentativeDraft((current) => ({ ...current, password: event.target.value }))
                      }
                      placeholder={
                        representativeDraft.currentEmail
                          ? "Preencha apenas se quiser trocar a senha"
                          : "Defina a senha inicial do representante"
                      }
                      autoComplete={representativeDraft.currentEmail ? "new-password" : "current-password"}
                    />
                  </label>
                </div>
                {selectedRepresentative && !selectedRepresentative.managed && (
                  <div className="admin-status-box">
                    <span className="admin-status-label">Somente leitura</span>
                    <strong>{selectedRepresentative.email}</strong>
                    <span className="admin-status-meta">
                      Este acesso veio do ambiente do servidor e não pode ser alterado por esta tela.
                    </span>
                  </div>
                )}
                <div className="admin-inline-actions">
                  <button
                    type="button"
                    className="export-button"
                    onClick={() => void handleSaveRepresentative()}
                    disabled={isSavingRepresentative || Boolean(selectedRepresentative && !selectedRepresentative.managed)}
                  >
                    {isSavingRepresentative
                      ? "Salvando..."
                      : representativeDraft.currentEmail
                        ? "Atualizar representante"
                        : "Cadastrar representante"}
                  </button>
                  <button
                    type="button"
                    className="export-button is-secondary"
                    onClick={() => {
                      resetRepresentativeDraft();
                      setNotice(null);
                    }}
                    disabled={isSavingRepresentative}
                  >
                    Limpar formulário
                  </button>
                </div>
              </article>
            </section>
            )}
            {activeAdminSection === "products" && (
            <section className="admin-grid admin-grid-products">
              <article className="admin-panel">
                <div className="admin-panel-head"><div><p className="admin-eyebrow">Produtos do JSON ativo</p><h2>Lista para edição</h2></div><span className="result-summary">{productsQuery.isLoading ? "Carregando..." : `${filteredProducts.length} itens no recorte`}</span></div>
                <label className="field search-field"><span>Buscar produto no JSON ativo</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Código, nome ou categoria" /></label>
                <div className="admin-product-list" role="list">
                  {filteredProducts.map((product) => {
                    const code = getRecordField(product, ["Codigo"]);
                    const name = getRecordField(product, ["Nome"]) || `Produto ${code}`;
                    const category = getRecordField(product, ["Categoria"]) || "Sem categoria";
                    const isCurrentDraft = draft.code.trim() === code && Boolean(code);
                    return <button key={code || name} type="button" className={`admin-product-item ${isCurrentDraft ? "is-selected" : ""}`} onClick={() => { setDraft(productToDraft(product)); setNotice({ tone: "info", text: `Produto ${code} carregado para edição.` }); }} role="listitem"><div><strong>{name}</strong><span>{category}</span></div><small>#{code || "sem código"}</small></button>;
                  })}
                </div>
              </article>
              <article className="admin-panel admin-form-panel">
                <div className="admin-panel-head"><div><p className="admin-eyebrow">Produto</p><h2>{draft.code.trim() ? `Edição do código ${draft.code.trim()}` : "Novo produto"}</h2></div></div>
                <div className="admin-form-grid">
                  <label className="field"><span>Código</span><input type="text" value={draft.code} onChange={(event) => setDraft((current) => ({ ...current, code: event.target.value }))} placeholder="Ex.: 8877" /></label>
                  <label className="field"><span>Categoria</span><input type="text" value={draft.category} onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))} placeholder="Ex.: ILUMINACAO TECNICA" /></label>
                  <label className="field field-span-2"><span>Nome</span><input type="text" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Nome comercial do produto" /></label>
                  <label className="field field-span-2"><span>Descrição</span><textarea rows={4} value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="Descrição visível no catálogo" /></label>
                  <label className="field field-span-2"><span>Especificações</span><textarea rows={4} value={draft.specs} onChange={(event) => setDraft((current) => ({ ...current, specs: event.target.value }))} placeholder="Ex.: Potência: 12W | Cor: Branco" /></label>
                  <label className="field field-span-2"><span>Foto principal</span><input type="url" value={draft.coverUrl} onChange={(event) => setDraft((current) => ({ ...current, coverUrl: event.target.value }))} placeholder="https://..." /></label>
                  <label className="field"><span>Foto com fundo branco</span><input type="url" value={draft.whiteUrl} onChange={(event) => setDraft((current) => ({ ...current, whiteUrl: event.target.value }))} placeholder="https://..." /></label>
                  <label className="field"><span>Foto ambientada</span><input type="url" value={draft.ambientUrl} onChange={(event) => setDraft((current) => ({ ...current, ambientUrl: event.target.value }))} placeholder="https://..." /></label>
                  <label className="field"><span>Foto de medidas</span><input type="url" value={draft.measuresUrl} onChange={(event) => setDraft((current) => ({ ...current, measuresUrl: event.target.value }))} placeholder="https://..." /></label>
                  <label className="field"><span>CODEPTO</span><input type="text" value={draft.deptCode} onChange={(event) => setDraft((current) => ({ ...current, deptCode: event.target.value }))} placeholder="Código do departamento" /></label>
                  <label className="field"><span>CODSEC</span><input type="text" value={draft.sectionCode} onChange={(event) => setDraft((current) => ({ ...current, sectionCode: event.target.value }))} placeholder="Código da seção" /></label>
                  <label className="field field-span-2"><span>Atributos extras em JSON</span><textarea rows={10} value={draft.extraJson} onChange={(event) => setDraft((current) => ({ ...current, extraJson: event.target.value }))} placeholder='{"voltagem":"220V","CODAUXILIAR":"789..."}' /></label>
                </div>
                <div className="admin-inline-actions"><button type="button" className="export-button" onClick={() => void handleSaveProduct()} disabled={isSaving}>{isSaving ? "Salvando..." : "Salvar no JSON"}</button><button type="button" className="export-button is-secondary" onClick={() => { setDraft(EMPTY_DRAFT); setNotice(null); }} disabled={isSaving}>Limpar formulário</button></div>
              </article>
            </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
