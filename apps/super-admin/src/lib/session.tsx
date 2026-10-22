import type { ConsoleSession, Operator } from "@ai-pos/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, hasToken, onSignOut, setToken } from "./api";

interface SessionValue {
  operator: Operator | null;
  status: "checking" | "signed-in" | "signed-out";
  signIn: (email: string, password: string, code: string) => Promise<void>;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [operator, setOperator] = useState<Operator | null>(null);
  const [status, setStatus] = useState<SessionValue["status"]>(hasToken() ? "checking" : "signed-out");

  const signOut = useCallback(() => {
    setToken(null);
    setOperator(null);
    setStatus("signed-out");
  }, []);

  useEffect(() => {
    onSignOut(signOut);
    if (hasToken()) {
      api
        .get<Operator>("/me")
        .then((me) => {
          setOperator(me);
          setStatus("signed-in");
        })
        .catch(() => signOut());
    }
    return () => onSignOut(null);
  }, [signOut]);

  const signIn = useCallback(async (email: string, password: string, code: string) => {
    const session = await api.post<ConsoleSession>("/auth/login", { email, password, code });
    setToken(session.access_token);
    setOperator(session.operator);
    setStatus("signed-in");
  }, []);

  const value = useMemo(() => ({ operator, status, signIn, signOut }), [operator, status, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) throw new Error("useSession needs SessionProvider.");
  return value;
}
