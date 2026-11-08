import AsyncStorage from "@react-native-async-storage/async-storage";
import { unpackCache, type CachedRead } from "@/api/cacheFormat";

export type { CachedRead };
export { unpackCache };

const PREFIX = "axizpos.cache.";

/** Non-sensitive read cache. Tokens never go here. */
export async function readCache<T>(key: string): Promise<CachedRead<T> | null> {
  try {
    const raw = await AsyncStorage.getItem(PREFIX + key);
    if (raw === null) return null;
    return unpackCache<T>(JSON.parse(raw) as unknown);
  } catch {
    return null;
  }
}

export async function writeCache(key: string, value: unknown): Promise<void> {
  try {
    const entry: CachedRead<unknown> = { savedAt: new Date().toISOString(), value };
    await AsyncStorage.setItem(PREFIX + key, JSON.stringify(entry));
  } catch {
    // A full disk must not block the screen that already has the response.
  }
}
