import type { Store } from "@ai-pos/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet } from "./api";
import { useAuth } from "./auth";

interface StoreScopeState {
  /** `null` means every store, consolidated. Store-bound users are always pinned to their branch. */
  storeId: string | null;
  setStoreId: (storeId: string | null) => void;
  pinned: boolean;
  stores: Store[];
}

const StoreScopeContext = createContext<StoreScopeState | null>(null);

const BRANCH_COOKIE = "axiz_branch";
const BRANCH_MAX_AGE = 60 * 60 * 24 * 365;

function readBranchCookie(): string | null {
  if (typeof document === "undefined") return null;
  const row = document.cookie.split("; ").find((part) => part.startsWith(`${BRANCH_COOKIE}=`));
  if (!row) return null;
  try {
    const value = decodeURIComponent(row.slice(BRANCH_COOKIE.length + 1));
    return /^[0-9a-f-]{36}$/i.test(value) ? value : null;
  } catch {
    return null;
  }
}

function writeBranchCookie(storeId: string | null): void {
  if (typeof document === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  if (!storeId) {
    document.cookie = `${BRANCH_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
    return;
  }
  document.cookie = `${BRANCH_COOKIE}=${encodeURIComponent(storeId)}; Path=/; Max-Age=${BRANCH_MAX_AGE}; SameSite=Lax${secure}`;
}

export function StoreScopeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const pinnedId = user?.store_id ?? null;
  const [selected, setSelected] = useState<string | null>(() => readBranchCookie());
  const [stores, setStores] = useState<Store[]>([]);

  useEffect(() => {
    let live = true;
    apiGet<Store[]>("/api/v1/stores?limit=200")
      .then((rows) => live && setStores(rows))
      .catch(() => live && setStores([]));
    return () => {
      live = false;
    };
  }, [user?.id]);

  useEffect(() => {
    if (pinnedId !== null || stores.length === 0 || selected === null) return;
    if (stores.some((store) => store.id === selected)) return;
    setSelected(null);
    writeBranchCookie(null);
  }, [pinnedId, stores, selected]);

  const setStoreId = useCallback((storeId: string | null) => {
    setSelected(storeId);
    writeBranchCookie(storeId);
  }, []);
  const value = useMemo<StoreScopeState>(
    () => ({ storeId: pinnedId ?? selected, setStoreId, pinned: pinnedId !== null, stores }),
    [pinnedId, selected, setStoreId, stores],
  );
  return <StoreScopeContext.Provider value={value}>{children}</StoreScopeContext.Provider>;
}

export function useStoreScope(): StoreScopeState {
  const context = useContext(StoreScopeContext);
  if (context === null) throw new Error("useStoreScope must be used inside StoreScopeProvider.");
  return context;
}
