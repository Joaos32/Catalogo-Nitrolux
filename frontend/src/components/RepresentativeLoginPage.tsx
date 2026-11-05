import { useRepresentativeSession } from "../lib/use-representative-session";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";

import {
  ApiRequestError,
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
    if (error.status === 503) {
      return "O serviço de acesso está temporariamente indisponível. Tente novamente mais tarde.";
    }
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
  const noticeRef = useRef<HTMLDivElement>(null);
  const confirmationRef = useRef<HTMLInputElement>(null);
  const [confirmationError, setConfirmationError] = useState("");
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

  useEffect(() => {
    if (notice?.tone === "warning") noticeRef.current?.focus();
  }, [notice]);

  const nextPath = sanitizeNextPath(searchParams.get("next"));
  const sessionQuery = useRepresentativeSession();

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
    if (isSubmitting) return;
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
    if (isSubmitting) return;
    setConfirmationError("");
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
      setConfirmationError("A confirmação precisa ser igual à nova senha.");
      confirmationRef.current?.focus();
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
      <a className="skip-link" href="#login-content">
        Pular para o login
      </a>
      <div className="bg-orb orb-a" aria-hidden="true"></div>
      <div className="bg-orb orb-b" aria-hidden="true"></div>

      <header className="hero auth-hero">
        <div className="hero-identity">
          <h1 className="sr-only">Acesso ao catálogo</h1>
          <div className="hero-kicker">Acesso para representantes</div>
          <div className="hero-brand" aria-label="Acesso restrito ao catálogo">
            <p className="hero-brand-name">ÁREA COMERCIAL</p>
            <p className="hero-brand-subtitle">
              Entre com seu login para acessar o catálogo completo
            </p>
          </div>
        </div>
      </header>

      <main
        id="login-content"
        tabIndex={-1}
        className="content-wrap admin-content"
        aria-busy={isSubmitting}
      >
        {notice && (
          <div
            ref={noticeRef}
            tabIndex={-1}
            role={notice.tone === "warning" ? "alert" : "status"}
            className={`banner banner-${notice.tone}`}
          >
            {notice.text}
          </div>
        )}

        <section className="admin-auth-shell">
          <article className="admin-panel admin-auth-panel auth-panel">
            <div className="admin-panel-head">
              <div>
                <p className="admin-eyebrow">Área comercial</p>
                <h2>{mode === "login" ? "Entrar no catálogo" : "Recuperar acesso"}</h2>
              </div>
            </div>

            <p className="admin-auth-copy">
              {mode === "login"
                ? "Use o e-mail e a senha fornecidos para sua equipe comercial."
                : "Use o código de recuperação fornecido pelo administrador e defina uma nova senha."}
            </p>

            <form
              onSubmit={(event) => {
                event.preventDefault();
                void (mode === "login" ? handleSubmit() : handlePasswordReset());
              }}
            >
              <fieldset className="auth-fields" disabled={isSubmitting}>
                <label className="field">
                  <span>E-mail</span>
                  <input
                    type="email"
                    name="email"
                    required
                    spellCheck={false}
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
                      name="password"
                      required
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
                        name="resetCode"
                        required
                        spellCheck={false}
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
                        name="newPassword"
                        required
                        minLength={10}
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
                        name="confirmPassword"
                        ref={confirmationRef}
                        required
                        minLength={10}
                        aria-invalid={Boolean(confirmationError)}
                        aria-describedby={confirmationError ? "confirmation-error" : undefined}
                        value={confirmPassword}
                        onChange={(event) => {
                          setConfirmPassword(event.target.value);
                          setConfirmationError("");
                        }}
                        placeholder="Repita a nova senha"
                        autoComplete="new-password"
                      />
                    </label>
                  </>
                )}

                {confirmationError && (
                  <p id="confirmation-error" className="field-error" role="alert">
                    {confirmationError}
                  </p>
                )}
                <div className="admin-inline-actions">
                  <button
                    type="submit"
                    className="export-button auth-submit-button"
                    disabled={isSubmitting}
                  >
                    {isSubmitting
                      ? mode === "login"
                        ? "Entrando…"
                        : "Alterando…"
                      : mode === "login"
                        ? "Entrar no catálogo"
                        : "Alterar senha"}
                  </button>
                  <button
                    type="button"
                    className="export-button is-secondary"
                    onClick={() => {
                      setNotice(null);
                      setConfirmationError("");
                      setMode(mode === "login" ? "reset" : "login");
                    }}
                  >
                    {mode === "login" ? "Esqueci minha senha" : "Voltar ao login"}
                  </button>
                  <Link className="export-button is-secondary" to="/erp">
                    Painel interno
                  </Link>
                </div>
              </fieldset>
            </form>
          </article>
        </section>
      </main>
    </div>
  );
}
