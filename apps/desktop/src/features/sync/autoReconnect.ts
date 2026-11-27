import { useEffect } from "react";
import { businessApiReachable, markApiReachable, syncBusinessCurrency } from "../checkout/currency";
import { connectivityStatus, flushLocalExpenses, flushSync, inTauri } from "../../lib/tauri";

/** Checkout reloads the catalogue when the server answers again. */
export const LINK_RESTORED_EVENT = "pos-link-restored";

const PROBE_MS = 5_000;
const FLUSH_MS = 15_000;

export interface LinkSnapshot {
  known: boolean;
  up: boolean;
  message: string;
}

const unknown: LinkSnapshot = { known: false, up: false, message: "Checking the register API." };
let current = unknown;
const listeners = new Set<() => void>();

export function linkSnapshot(): LinkSnapshot {
  return current;
}

export function subscribeLink(listener: () => void): () => void {
  listeners.add(listener);
  listener();
  return () => listeners.delete(listener);
}

function publish(next: LinkSnapshot): void {
  if (current.known === next.known && current.up === next.up && current.message === next.message) return;
  current = next;
  for (const listener of listeners) listener();
}

/** A reachable server syncs immediately, then again on the normal interval. A drop does not sync. */
export function reconnectPlan(input: { wasUp: boolean; up: boolean; sinceFlushMs: number; intervalMs: number }): {
  flush: boolean;
  restored: boolean;
} {
  if (!input.up) return { flush: false, restored: false };
  const restored = !input.wasUp;
  return { flush: restored || input.sinceFlushMs >= input.intervalMs, restored };
}

export function useAutoReconnect(): void {
  useEffect(() => {
    if (!inTauri()) return;
    let stopped = false;
    let busy = false;
    let wasUp = false;
    let lastFlush = 0;

    const tick = async () => {
      if (stopped || busy) return;
      busy = true;
      try {
        let up = false;
        let message = "You're working offline. Local POS operations remain available. Pending changes will synchronize when a connection is restored.";
        try {
          const status = await connectivityStatus();
          up = status.state === "online";
          message = status.message;
        } catch {
          up = false;
        }
        if (stopped) return;
        if (!up) {
          wasUp = false;
          markApiReachable(false);
          publish({ known: true, up: false, message });
          return;
        }
        const plan = reconnectPlan({
          wasUp,
          up: true,
          sinceFlushMs: lastFlush === 0 ? FLUSH_MS : Date.now() - lastFlush,
          intervalMs: FLUSH_MS,
        });
        wasUp = true;
        publish({ known: true, up: true, message });
        if (!businessApiReachable() || plan.flush) {
          await syncBusinessCurrency().catch(() => undefined);
        }
        if (!plan.flush || stopped) return;
        lastFlush = Date.now();
        await flushSync().catch(() => undefined);
        await flushLocalExpenses().catch(() => undefined);
        if (plan.restored) window.dispatchEvent(new Event(LINK_RESTORED_EVENT));
      } finally {
        busy = false;
      }
    };

    void tick();
    const timer = window.setInterval(() => void tick(), PROBE_MS);
    const soon = () => void tick();
    window.addEventListener("online", soon);
    window.addEventListener("focus", soon);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.removeEventListener("online", soon);
      window.removeEventListener("focus", soon);
    };
  }, []);
}
