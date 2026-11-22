import { useEffect, useState } from "react";
import { env } from "../../config/env";
import { beginSync, noteSyncCounts } from "../../lib/syncActivity";
import { flushSync, inTauri, pendingCount, rejectedCount, type SyncReport } from "../../lib/tauri";
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
      if (!inTauri() || cancelled) return;
      const waiting = await pendingCount().catch(() => 0);
      const end = waiting > 0 ? beginSync() : () => undefined;
      try {
        const next = await flushSync();
        if (!cancelled) {
          setReport(next);
          noteSyncCounts({ pending: next.pending });
        }
      } catch (error) {
        const pending = await pendingCount().catch(() => waiting);
        if (!cancelled) {
          noteSyncCounts({ pending });
          setReport({
            pending,
            applied: 0,
            duplicates: 0,
            message: error instanceof Error ? error.message : "Sync failed.",
          });
        }
      } finally {
        end();
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

/** Rejected batches stay out of the pending count. The header reads them separately. */
export function useRejectedSyncCount(active: boolean, pulse = 0) {
  const [failed, setFailed] = useState(0);
  useEffect(() => {
    if (!active) return;
    const poll = () =>
      void rejectedCount()
        .then((count) => {
          const failed = Math.max(0, count);
          setFailed(failed);
          noteSyncCounts({ failed });
        })
        .catch(() => undefined);
    poll();
    const timer = window.setInterval(poll, 15_000);
    return () => window.clearInterval(timer);
  }, [active, pulse]);
  return failed;
}
