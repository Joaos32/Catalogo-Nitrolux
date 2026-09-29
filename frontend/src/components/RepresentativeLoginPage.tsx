import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import {
  ApiRequestError,
  fetchRepresentativeSession,
  loginRepresentative,
  resetRepresentativePassword,
} from "../lib/catalog-api";

interface NoticeState {
  tone: "warning" | "info";
  text: string;
}

function sanitizeNextPath(value: string | null): string {
  const candidate = String(value || "").trim();
  if (!candidate.startsWith("/") || candidate.startsWith("//")) return "/";
  return candidate || "/";
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 403 || /invalid representative credentials/i.test(error.message)) {
      return "E-mail ou senha incorretos. Confira os dados ou use a recuperação de senha.";
    }
    return error.message || "Não foi possível entrar no catálogo.";
  }
  if (error instanceof Error && error.message) return error.message;
  return "Não foi possível entrar no catálogo.";
}

export default function RepresentativeLoginPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [mode, setMode] = useState<"login" | "reset">("login");
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nextPath = sanitizeNextPath(searchParams.get("next"));
  const sessionQuery = useQuery({
    queryKey: ["representative-session"],
    queryFn: fetchRepresentativeSession,
    retry: false,
  });

  if (sessionQuery.isLoading) {
    return (
      <div className="page-shell">
        <main className="content-wrap">
          <section className="loading-state" role="status" aria-live="polite">
            Validando configuração de acesso...
          </section>
        </main>
      </div>
    );
  }

  if (sessionQuery.isError) {
    return (
      <div className="page-shell">
        <main className="content-wrap">
          <div className="banner banner-warning">
            Não foi possível carregar a autenticação agora. Atualize a página para tentar novamente.
          </div>
        </main>
      </div>
    );
  }

  if (!sessionQuery.data?.protection_enabled || sessionQuery.data?.authenticated) {
    return <Navigate to={nextPath} replace />;
  }

  const handleSubmit = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedPassword = password.trim();

    if (!normalizedEmail) {
      setNotice({ tone: "warning", text: "Informe o e-mail do representante para continuar." });
      return;
    }
    if (!normalizedPassword) {
      setNotice({ tone: "warning", text: "Informe a senha do representante para continuar." });
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    try {
      await loginRepresentative(normalizedEmail, normalizedPassword);
      await queryClient.invalidateQueries({ queryKey: ["representative-session"] });
      navigate(nextPath, { replace: true });
    } catch (error) {
      setNotice({ tone: "warning", text: getErrorMessage(error) });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePasswordReset = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedCode = resetCode.trim();
    const normalizedPassword = newPassword.trim();
    const normalizedConfirmation = confirmPassword.trim();

    if (!normalizedEmail) {
      setNotice({ tone: "warning", text: "Informe o e-mail do representante." });
      return;
    }
    if (!normalizedCode) {
      setNotice({ tone: "warning", text: "Informe o código de recuperação." });
      return;
    }
    if (normalizedPassword.length < 10) {
      setNotice({ tone: "warning", text: "A nova senha precisa ter pelo menos 10 caracteres." });
      return;
    }
    if (normalizedPassword !== normalizedConfirmation) {
      setNotice({ tone: "warning", text: "A confirmação precisa ser igual à nova senha." });
      return;
    }

    setIsSubmitting(true);
    setNotice(null);
    try {
      await resetRepresentativePassword(normalizedEmail, normalizedCode, normalizedPassword);
      setPassword("");
      setResetCode("");
      setNewPassword("");
      setConfirmPassword("");
      setMode("login");
      setNotice({ tone: "info", text: "Senha alterada. Entre com a nova senha para continuar." });
    } catch (error) {
      setNotice({ tone: "warning", text: getErrorMessage(error) });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="page-shell auth-page-shell">
      <div className="bg-orb orb-a" aria-hidden="true"></div>
      <div className="bg-orb orb-b" aria-hidden="true"></div>

      <header className="hero auth-hero">
        <div className="hero-identity">
          <div className="hero-kicker">Acesso para representantes</div>
          <div className="hero-brand" aria-label="Acesso restrito ao catálogo">
            <p className="hero-brand-name">ÁREA COMERCIAL</p>
            <p className="hero-brand-subtitle">Entre com seu login para acessar o catálogo completo</p>
          </div>
        </div>
      </header>

      <main className="content-wrap admin-content" aria-busy={isSubmitting}>
        {notice && <div className={`banner banner-${notice.tone}`}>{notice.text}</div>}

        <section className="admin-auth-shell">
          <article className="admin-panel admin-auth-panel auth-panel">
            <div className="admin-panel-head">
              <div>
                <p className="admin-eyebrow">Login JWT</p>
                <h2>Entrar no catálogo</h2>
              </div>
            </div>

            <p className="admin-auth-copy">
              {mode === "login"
                ? "Use o e-mail e a senha fornecidos para sua equipe comercial."
                : "Use o código de recuperação fornecido pelo administrador e defina uma nova senha."}
            </p>

            <label className="field">
              <span>E-mail</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="representante@empresa.com"
                autoComplete="username"
              />
            </label>

            {mode === "login" ? (
              <label className="field">
                <span>Senha</span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Informe sua senha"
                  autoComplete="current-password"
                />
              </label>
            ) : (
              <>
                <label className="field">
                  <span>Código de recuperação</span>
                  <input
                    type="text"
                    value={resetCode}
                    onChange={(event) => setResetCode(event.target.value)}
                    placeholder="Código fornecido pelo administrador"
                    autoComplete="one-time-code"
                  />
                </label>
                <label className="field">
                  <span>Nova senha</span>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    placeholder="Defina a nova senha"
                    autoComplete="new-password"
                  />
                </label>
                <label className="field">
                  <span>Confirmar nova senha</span>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="Repita a nova senha"
                    autoComplete="new-password"
                  />
                </label>
              </>
            )}

            <div className="admin-inline-actions">
              <button
                type="button"
                className="export-button auth-submit-button"
                onClick={() => void (mode === "login" ? handleSubmit() : handlePasswordReset())}
                disabled={isSubmitting}
              >
                {isSubmitting
                  ? mode === "login"
                    ? "Entrando..."
                    : "Alterando..."
                  : mode === "login"
                    ? "Entrar no catálogo"
                    : "Alterar senha"}
              </button>
              <button
                type="button"
                className="export-button is-secondary"
                onClick={() => {
                  setNotice(null);
                  setMode(mode === "login" ? "reset" : "login");
                }}
              >
                {mode === "login" ? "Esqueci minha senha" : "Voltar ao login"}
              </button>
              <button
                type="button"
                className="export-button is-secondary"
                onClick={() => navigate("/erp")}
              >
                Painel interno
              </button>
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
