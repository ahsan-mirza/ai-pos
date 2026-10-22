import { Capability } from "@ai-pos/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { activeStore } from "../checkout/currency";
import { useCapabilities } from "../../lib/capabilities";
import { playAlertChime } from "./alertChime";
import { listenForPosAlerts, sendPosAlertAck, type PosTableAlert } from "./tableAlertClient";

interface TableAlertApi {
  alerts: PosTableAlert[];
  /** Banner rows the cashier has not swiped away. The floor card keeps glowing until Acknowledge. */
  banner: PosTableAlert[];
  forTable: (tableId: string | null) => PosTableAlert | null;
  acknowledge: (id: string) => void;
  acknowledgeTable: (tableId: string) => void;
  clear: (id: string) => void;
}

const TableAlertContext = createContext<TableAlertApi | null>(null);

export function TableAlertProvider({ children }: { children: ReactNode }) {
  const capabilities = useCapabilities();
  const tablesOn = capabilities.foodAndBeverage && capabilities.enabled.has(Capability.Tables);
  const storeId = activeStore().id;
  const [alerts, setAlerts] = useState<PosTableAlert[]>([]);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(() => new Set());
  const alertsRef = useRef(alerts);
  alertsRef.current = alerts;
  const seen = useRef(new Set<string>());

  useEffect(() => {
    if (!tablesOn) return;
    return listenForPosAlerts(storeId, (event) => {
      if (event.type === "cleared") {
        setAlerts((current) => current.filter((item) => item.id !== event.alertId));
        setHidden((current) => {
          if (!current.has(event.alertId)) return current;
          const next = new Set(current);
          next.delete(event.alertId);
          return next;
        });
        return;
      }
      if (seen.current.has(event.alert.id)) return;
      seen.current.add(event.alert.id);
      playAlertChime(event.alert.alert);
      setAlerts((current) => [event.alert, ...current.filter((item) => item.id !== event.alert.id)].slice(0, 12));
    });
  }, [storeId, tablesOn]);

  const acknowledge = useCallback((id: string) => {
    const alert = alertsRef.current.find((item) => item.id === id);
    if (alert) sendPosAlertAck(alert.id, alert.tableId);
    setAlerts((current) => current.filter((item) => item.id !== id));
    setHidden((current) => {
      if (!current.has(id)) return current;
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }, []);

  const acknowledgeTable = useCallback(
    (tableId: string) => {
      for (const alert of alertsRef.current.filter((item) => item.tableId === tableId)) acknowledge(alert.id);
    },
    [acknowledge],
  );

  const clear = useCallback((id: string) => {
    setHidden((current) => {
      const next = new Set(current);
      next.add(id);
      return next;
    });
  }, []);

  const forTable = useCallback((tableId: string | null) => {
    if (!tableId) return null;
    const rows = alerts.filter((item) => item.tableId === tableId);
    return rows.find((item) => item.alert === "request-bill") ?? rows[0] ?? null;
  }, [alerts]);

  const banner = useMemo(() => alerts.filter((item) => !hidden.has(item.id)), [alerts, hidden]);
  const value = useMemo(
    () => ({ alerts, banner, forTable, acknowledge, acknowledgeTable, clear }),
    [alerts, banner, forTable, acknowledge, acknowledgeTable, clear],
  );
  return <TableAlertContext.Provider value={value}>{children}</TableAlertContext.Provider>;
}

export function useTableAlerts(): TableAlertApi {
  const value = useContext(TableAlertContext);
  if (value === null) throw new Error("TableAlertProvider is missing.");
  return value;
}

/** Floor cards render inside the register. Outside it they simply show no alert. */
export function useTableAlertFor(tableId: string | null): { alert: PosTableAlert | null; acknowledge: () => void } {
  const value = useContext(TableAlertContext);
  if (value === null || tableId === null) return { alert: null, acknowledge: () => undefined };
  return { alert: value.forTable(tableId), acknowledge: () => value.acknowledgeTable(tableId) };
}
