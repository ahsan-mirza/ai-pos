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
import {
  clearStoredSession,
  readStoredSession,
  renewFailureSignsOut,
  restorePlan,
  writeStoredSession,
  type SessionBucket,
  type StoredSession,
} from "./sessionStore";

const RENEW_LEAD_MS = 60_000;
const RENEW_RETRY_MS = 15_000;
const PROFILE_RETRY_MS = 3_000;

function storageBuckets(): { persistent: SessionBucket; legacy: SessionBucket } | null {
  if (typeof window === "undefined") return null;
  try {
    return { persistent: window.localStorage, legacy: window.sessionStorage };
  } catch {
    return null;
  }
}

function initialSession(): { session: StoredSession | null; status: "checking" | "signed-out" | "signed-in" } {
  const buckets = storageBuckets();
  if (buckets === null) return { session: null, status: "signed-out" };
  const stored = readStoredSession(buckets.persistent, buckets.legacy);
  if (restorePlan(stored, Date.now()) === "sign-out") {
    clearStoredSession(buckets.persistent, buckets.legacy);
    return { session: null, status: "signed-out" };
  }
  return { session: stored, status: "checking" };
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const boot = useState(initialSession)[0];
  const [session, setSession] = useState<StoredSession | null>(boot.session);
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>(boot.status);
  const generation = useRef(0);

  const logout = useCallback(() => {
    generation.current += 1;
    const buckets = storageBuckets();
    if (buckets) clearStoredSession(buckets.persistent, buckets.legacy);
    void clearUserCaches();
    setAccessToken(null);
    setSession(null);
    setUser(null);
    setStatus("signed-out");
  }, []);

  const begin = useCallback((response: TokenResponse) => {
    const next = { token: response.access_token, expiresAt: Date.now() + response.expires_in * 1000 };
    const buckets = storageBuckets();
    if (buckets) {
      writeStoredSession(buckets.persistent, next);
      clearStoredSession(buckets.legacy);
    }
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
        if (error instanceof ApiRequestError && renewFailureSignsOut(error.status)) return false;
        throw error;
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
    const onOnline = () => {
      refreshUser().catch((error: unknown) => {
        if (stopped) return;
        if (error instanceof ApiRequestError && error.status === 401) logout();
      });
    };
    window.addEventListener("online", onOnline);
    return () => {
      stopped = true;
      window.removeEventListener("online", onOnline);
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
