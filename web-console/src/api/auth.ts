export interface AuthUser {
  username: string;
  displayName: string;
  provider?: string;
  externalId?: string;
  email?: string;
}

export interface AuthSession {
  accessToken: string;
  expiresAt: number;
  user: AuthUser;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const SESSION_KEY = "document-ai-review.web-console.session";

function apiUrl(path: string) {
  if (API_BASE_URL) {
    return `${API_BASE_URL}${path}`;
  }
  return new URL(path, window.location.origin).toString();
}

export async function login(username: string, password: string): Promise<AuthSession> {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error("INVALID_CREDENTIALS");
  }
  const payload = await response.json();
  return {
    accessToken: payload.access_token,
    expiresAt: payload.expires_at,
    user: {
      username: payload.user.username,
      displayName: payload.user.display_name,
    },
  };
}

export interface AuthProvider {
  id: string;
  label: string;
  type: string;
  configured: boolean;
  loginPath: string;
  callbackPath: string;
  status: string;
}

export async function loadAuthProviders(): Promise<AuthProvider[]> {
  let response: Response;
  try {
    response = await fetch(apiUrl("/api/v1/auth/providers"));
  } catch {
    return [];
  }
  if (!response.ok) {
    return [];
  }
  const payload = await response.json();
  return (payload.providers ?? []).map((provider: ApiAuthProvider) => ({
    id: provider.id,
    label: provider.label,
    type: provider.type,
    configured: provider.configured,
    loginPath: apiUrl(provider.login_path),
    callbackPath: provider.callback_path,
    status: provider.status
  }));
}

export async function startSso(providerId: string): Promise<string> {
  const response = await fetch(
    apiUrl(`/api/v1/auth/sso/start?provider=${encodeURIComponent(providerId)}`)
  );
  if (!response.ok) {
    throw new Error("SSO_START_FAILED");
  }
  const payload = await response.json();
  return payload.redirect_url;
}

export async function loadCurrentSession(): Promise<AuthSession | null> {
  const local = loadSession();
  if (local) {
    return local;
  }
  let response: Response;
  try {
    response = await fetch(apiUrl("/api/v1/auth/me"), {
      credentials: "include"
    });
  } catch {
    return null;
  }
  if (!response.ok) {
    return null;
  }
  const payload = await response.json();
  const session = {
    accessToken: "cookie-session",
    expiresAt: Math.floor(Date.now() / 1000) + 3600,
    user: {
      username: payload.user.username,
      displayName: payload.user.display_name,
      provider: payload.user.provider,
      externalId: payload.user.external_id,
      email: payload.user.email
    }
  };
  saveSession(session);
  return session;
}

export function loadSession(): AuthSession | null {
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }
  try {
    const session = JSON.parse(raw) as AuthSession;
    if (!session.accessToken || session.expiresAt * 1000 <= Date.now()) {
      clearSession();
      return null;
    }
    return session;
  } catch {
    clearSession();
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  window.localStorage.removeItem(SESSION_KEY);
}

export function authHeaders(): Record<string, string> {
  const session = loadSession();
  if (!session || session.accessToken === "cookie-session") {
    return {};
  }
  return { Authorization: `Bearer ${session.accessToken}` };
}

interface ApiAuthProvider {
  id: string;
  label: string;
  type: string;
  configured: boolean;
  login_path: string;
  callback_path: string;
  status: string;
}
