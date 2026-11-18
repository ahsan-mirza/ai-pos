import { BUSINESS_SETTINGS_STORAGE_KEY } from "@ai-pos/shared-types";

/** Drops this browser's copy of the previous store. The demo tenant itself is left as it is. */
export function clearTenantClientState(): void {
  try {
    localStorage.removeItem(BUSINESS_SETTINGS_STORAGE_KEY);
    const assistant: string[] = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key !== null && key.startsWith("ai-pos.assistant.")) assistant.push(key);
    }
    for (const key of assistant) localStorage.removeItem(key);
  } catch {
    // Storage can be blocked. The session clear still proceeds.
  }
}
