import type { UnitCreate, UnitOfMeasure } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../../lib/api";

export const unitsApi = {
  list: () => apiGet<UnitOfMeasure[]>("/api/v1/units"),
  create: (body: UnitCreate) => apiPost<UnitOfMeasure>("/api/v1/units", body),
  update: (id: string, body: Partial<Pick<UnitOfMeasure, "name" | "short_name" | "is_active">>) =>
    apiPatch<UnitOfMeasure>(`/api/v1/units/${id}`, body),
  remove: (id: string) => apiDelete(`/api/v1/units/${id}`),
};

/** Built-in and custom units, smallest first. `active` is what may be assigned to a product. */
export function useUnits() {
  const [units, setUnits] = useState<UnitOfMeasure[]>([]);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setUnits(await unitsApi.list());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load units.");
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { units, active: units.filter((unit) => unit.is_active), error, reload };
}
