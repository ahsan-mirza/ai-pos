import { hasPermission, type Permission, type TokenResponse, type User } from "@ai-pos/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ApiRequestError,
  apiGet,
  apiPublicPost,
  renewAccessToken,
  requestSessionRenewal,
  setAccessToken,
  setSessionRenewer,
  setUnauthorizedHandler,
} from "./api";
import { clearUserCaches } from "../pwa/register";

const STORAGE_KEY = "ai-pos.portal-session";
const RENEW_LEAD_MS = 60_000;
const RENEW_RETRY_MS = 15_000;
const PROFILE_RETRY_MS = 3_000;

interface StoredSession {
  token: string;
  expiresAt: number;
}

interface AuthState {
  user: User | null;
  status: "checking" | "signed-out" | "signed-in";
  login: (username: string, password: string) => Promise<void>;
  /** Signs in with the single-use token signup hands to a newly provisioned store. */
  handoff: (token: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  /** Keeps this browser signed in after the server issues a replacement token. */
  replaceSession: (response: TokenResponse) => void;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

function readSession(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    if (typeof parsed.token !== "string" || parsed.expiresAt <= Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StoredSession | null>(() => readSession());
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>(session ? "checking" : "signed-out");
  const generation = useRef(0);

  const logout = useCallback(() => {
    generation.current += 1;
    sessionStorage.removeItem(STORAGE_KEY);
    void clearUserCaches();
    setAccessToken(null);
    setSession(null);
    setUser(null);
    setStatus("signed-out");
  }, []);

  const begin = useCallback((response: TokenResponse) => {
    const next = { token: response.access_token, expiresAt: Date.now() + response.expires_in * 1000 };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    setAccessToken(next.token);
    setUser(response.user);
    setSession(next);
    setStatus("signed-in");
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    setSessionRenewer(async () => {
      const stamp = generation.current;
      try {
        const next = await renewAccessToken<TokenResponse>();
        if (stamp !== generation.current) return false;
        begin(next);
        return true;
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 0) throw error;
        return false;
      }
    });
    return () => setSessionRenewer(null);
  }, [begin]);

  const refreshUser = useCallback(async () => {
    setUser(await apiGet<User>("/api/v1/auth/me"));
    setStatus("signed-in");
  }, []);

  useEffect(() => {
    if (session === null) return;
    setAccessToken(session.token);
    let stopped = false;
    let renewTimer = 0;
    let profileTimer = 0;
    const scheduleRenew = (delay: number) => {
      renewTimer = window.setTimeout(() => {
        void requestSessionRenewal()
          .then((ok) => {
            if (stopped || ok) return;
            logout();
          })
          .catch(() => {
            if (!stopped) scheduleRenew(RENEW_RETRY_MS);
          });
      }, delay);
    };
    scheduleRenew(Math.max(0, session.expiresAt - Date.now() - RENEW_LEAD_MS));
    if (user === null) {
      const loadProfile = () => {
        refreshUser().catch((error: unknown) => {
          if (stopped) return;
          if (error instanceof ApiRequestError && error.status === 401) {
            logout();
            return;
          }
          profileTimer = window.setTimeout(loadProfile, PROFILE_RETRY_MS);
        });
      };
      loadProfile();
    }
    return () => {
      stopped = true;
      window.clearTimeout(renewTimer);
      window.clearTimeout(profileTimer);
    };
  }, [session, user, logout, refreshUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      begin(await apiPublicPost<TokenResponse>("/api/v1/auth/login-password", { username, password }));
    },
    [begin],
  );

  const handoff = useCallback(
    async (token: string) => {
      begin(await apiPublicPost<TokenResponse>("/api/v1/auth/handoff", { token }));
    },
    [begin],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      status,
      login,
      handoff,
      logout,
      refreshUser,
      replaceSession: begin,
      can: (permission) => hasPermission(user, permission),
    }),
    [user, status, login, handoff, logout, refreshUser, begin],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}

/** Mirrors the API rule for platform files such as the POS installer: the Super Admin role only. */
export function useIsSuperAdmin(): boolean {
  return useAuth().user?.role.name === "Super Admin";
}
