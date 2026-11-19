import { bindCapabilityTenant } from "../lib/capabilities";
import { applyPreviewTerminal, inTauri, readPreviewTerminal, terminalStatus, type TerminalStatus } from "../lib/tauri";
import { env } from "./env";

let current: TerminalStatus | null = null;

/**
 * Reads the activated identity before the rest of the app loads, so module-level store lookups
 * (catalog, receipts, floors) already use the activated branch instead of VITE_STORE_ID.
 */
export async function loadTerminal(): Promise<TerminalStatus | null> {
  if (!inTauri()) {
    const saved = readPreviewTerminal();
    if (saved === null) {
      const tenantId = env.tenantDomain?.trim() ?? "";
      bindCapabilityTenant(tenantId === "" ? null : { tenantId, environment: env.apiBaseUrl });
      return null;
    }
    applyPreviewTerminal(saved);
    current = saved.status;
    bindActiveTenant(current);
    return current;
  }
  current = await terminalStatus();
  if (current.activated && current.store_id) env.storeId = current.store_id;
  if (current.tenant_domain) env.tenantDomain = current.tenant_domain;
  bindActiveTenant(current);
  return current;
}

function bindActiveTenant(status: TerminalStatus | null): void {
  const tenantId = status?.activated ? status.tenant_slug.trim() : "";
  bindCapabilityTenant(tenantId === "" ? null : { tenantId, environment: env.apiBaseUrl });
}

/** null in the browser preview; otherwise the register's activation state. */
export function terminal(): TerminalStatus | null {
  return current;
}

export function needsActivation(): boolean {
  return inTauri() && (current === null || !current.activated);
}
