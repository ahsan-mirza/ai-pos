import { useEffect, useState } from "react";
import { env } from "../../config/env";
import { flushSync, inTauri, pendingCount, type SyncReport } from "../../lib/tauri";
import { syncBusinessCurrency } from "./currency";

const idle: SyncReport = {
  pending: 0,
  applied: 0,
  duplicates: 0,
  message: "Browser preview keeps the queue in memory. The Tauri shell persists it in SQLite.",
};

export function useSyncEngine(pulse: number) {
  const [report, setReport] = useState<SyncReport>(idle);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      await syncBusinessCurrency().catch(() => undefined);
      if (!inTauri()) return;
      try {
        const next = await flushSync();
        if (!cancelled) setReport(next);
      } catch (error) {
        const pending = await pendingCount().catch(() => 0);
        if (!cancelled) {
          setReport({
            pending,
            applied: 0,
            duplicates: 0,
            message: error instanceof Error ? error.message : "Sync failed.",
          });
        }
      }
    };

    void run();
    const timer = window.setInterval(() => void run(), env.syncIntervalMs);
    const reconnected = () => void run();
    window.addEventListener("online", reconnected);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("online", reconnected);
    };
  }, [pulse]);

  return { report, setReport, desktop: inTauri() };
}
