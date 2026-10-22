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

export function StoreScopeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const pinnedId = user?.store_id ?? null;
  const [selected, setSelected] = useState<string | null>(null);
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

  const setStoreId = useCallback((storeId: string | null) => setSelected(storeId), []);
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
