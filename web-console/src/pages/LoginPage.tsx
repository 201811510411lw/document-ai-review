import { FormEvent, useState } from "react";
import { LockKeyhole, LogIn, ShieldCheck } from "lucide-react";
import { login, saveSession } from "../api/auth";
import { navigateTo } from "../navigation";

export function LoginPage() {
  const [username, setUsername] = useState("reviewer");
  const [password, setPassword] = useState("reviewer123");
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");

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
