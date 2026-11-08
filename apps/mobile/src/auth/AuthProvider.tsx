import {
  hasPermission,
  normalizeStoreCode,
  type Permission,
  type TokenResponse,
  type User,
} from "@ai-pos/shared-types";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet, apiPublicPost, apiRefresh, setAccessToken, setSessionRenewer, setTenantDomain, setUnauthorizedHandler } from "@/api/client";
import { queryClient } from "@/api/queryClient";
import { ApiRequestError } from "@/api/errors";
import { parseSession, renewFailureSignsOut, restorePlan, type StoredSession } from "./session";
import { secureDelete, secureRead, secureWrite } from "./secure";

const SESSION_KEY = "axizpos.session";
const STORE_KEY = "axizpos.store-code";
const RENEW_LEAD_MS = 60_000;

interface AuthValue {
  user: User | null;
  status: "checking" | "signed-out" | "signed-in";
  storeCode: string;
  login: (username: string, password: string, storeCode: string) => Promise<void>;
  logout: () => void;
  can: (permission: Permission) => boolean;
  superAdmin: boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<StoredSession | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthValue["status"]>("checking");
  const [storeCode, setStoreCode] = useState("");

  const logout = useCallback(() => {
    setAccessToken(null);
    setSession(null);
    setUser(null);
    setStatus("signed-out");
    queryClient.clear();
    void secureDelete(SESSION_KEY);
  }, []);

  const begin = useCallback((response: TokenResponse) => {
    const next = { token: response.access_token, expiresAt: Date.now() + response.expires_in * 1000 };
    setAccessToken(next.token);
    setUser(response.user);
    setSession(next);
    setStatus("signed-in");
    void secureWrite(SESSION_KEY, JSON.stringify(next));
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    setSessionRenewer(async () => {
      try {
        const next = await apiRefresh<TokenResponse>("/api/v1/auth/refresh");
        begin(next);
        return true;
      } catch (error) {
        if (error instanceof ApiRequestError && renewFailureSignsOut(error.status)) return false;
        throw error;
      }
    });
    return () => setSessionRenewer(null);
  }, [begin]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [rawSession, code] = await Promise.all([secureRead(SESSION_KEY), AsyncStorage.getItem(STORE_KEY)]);
      if (cancelled) return;
      const storedCode = code ?? "";
      setStoreCode(storedCode);
      setTenantDomain(storedCode === "" ? null : storedCode);
      const stored = parseSession(rawSession);
      const plan = restorePlan(stored, Date.now());
      if (plan === "sign-out" || stored === null) {
        setStatus("signed-out");
        return;
      }
      setAccessToken(stored.token);
      setSession(stored);
      try {
        if (plan === "refresh") {
          const next = await apiRefresh<TokenResponse>("/api/v1/auth/refresh");
          if (!cancelled) begin(next);
          return;
        }
        const profile = await apiGet<User>("/api/v1/auth/me");
        if (!cancelled) {
          setUser(profile);
          setStatus("signed-in");
        }
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiRequestError && error.status === 401) logout();
        else setStatus("signed-in");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [begin, logout]);

  useEffect(() => {
    if (session === null || status !== "signed-in") return;
    const delay = Math.max(0, session.expiresAt - Date.now() - RENEW_LEAD_MS);
    const timer = setTimeout(() => {
      void apiRefresh<TokenResponse>("/api/v1/auth/refresh")
        .then(begin)
        .catch((error: unknown) => {
          if (error instanceof ApiRequestError && error.status === 401) logout();
        });
    }, delay);
    return () => clearTimeout(timer);
  }, [session, status, begin, logout]);

  const login = useCallback(
    async (username: string, password: string, code: string) => {
      const normalized = normalizeStoreCode(code);
      setTenantDomain(normalized === "" ? null : normalized);
      const response = await apiPublicPost<TokenResponse>("/api/v1/auth/login-password", { username, password });
      await AsyncStorage.setItem(STORE_KEY, normalized);
      setStoreCode(normalized);
      begin(response);
    },
    [begin],
  );

  const value = useMemo<AuthValue>(
    () => ({
      user,
      status,
      storeCode,
      login,
      logout,
      can: (permission) => hasPermission(user, permission),
      superAdmin: user?.role.name === "Super Admin",
    }),
    [user, status, storeCode, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
