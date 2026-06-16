import { FormEvent, useEffect, useState } from "react";
import { LockKeyhole, LogIn, QrCode, ShieldCheck } from "lucide-react";
import { loadAuthProviders, login, saveSession, startSso, type AuthProvider } from "../api/auth";
import { navigateTo } from "../navigation";

export function LoginPage() {
  const [username, setUsername] = useState("reviewer");
  const [password, setPassword] = useState("reviewer123");
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [ssoStatus, setSsoStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [providers, setProviders] = useState<AuthProvider[]>([]);

  useEffect(() => {
    loadAuthProviders().then(setProviders);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("submitting");
    try {
      const session = await login(username, password);
      saveSession(session);
      navigateTo(nextPath());
    } catch {
      setStatus("error");
    }
  }

  async function submitWecom() {
    setSsoStatus("submitting");
    try {
      window.location.href = await startSso("wecom", isEnterpriseWeChatBrowser() ? "work" : "qr");
    } catch {
      setSsoStatus("error");
    }
  }

  const wecomProvider = providers.find((provider) => provider.id === "wecom");

  return (
    <main className="login-shell">
      <section className="login-panel" aria-label="登录工作台">
        <div className="login-brand">
          <ShieldCheck size={28} aria-hidden="true" />
          <div>
            <span>Document AI</span>
            <strong>营业执照审核工作台</strong>
          </div>
        </div>
        <form className="login-form" onSubmit={submit}>
          <button
            className="primary-button"
            disabled={ssoStatus === "submitting" || wecomProvider?.configured === false}
            onClick={submitWecom}
            type="button"
          >
            {ssoStatus === "submitting" ? (
              <LockKeyhole size={16} aria-hidden="true" />
            ) : (
              <QrCode size={16} aria-hidden="true" />
            )}
            企业微信登录
          </button>
          {wecomProvider && !wecomProvider.configured && (
            <p className="login-error">企业微信应用尚未配置。</p>
          )}
          {ssoStatus === "error" && <p className="login-error">企业微信登录启动失败。</p>}
          <div className="login-divider">本地账号登录</div>
          <label>
            <span>账号</span>
            <input
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label>
            <span>密码</span>
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {status === "error" && <p className="login-error">账号或密码不正确。</p>}
          <button className="primary-button" disabled={status === "submitting"} type="submit">
            {status === "submitting" ? (
              <LockKeyhole size={16} aria-hidden="true" />
            ) : (
              <LogIn size={16} aria-hidden="true" />
            )}
            登录
          </button>
        </form>
      </section>
    </main>
  );
}

function nextPath() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  return next && next.startsWith("/") ? next : "/reviews";
}

function isEnterpriseWeChatBrowser() {
  return /wxwork/i.test(window.navigator.userAgent);
}
