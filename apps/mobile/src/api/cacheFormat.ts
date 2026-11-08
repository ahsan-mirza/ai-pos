export interface CachedRead<T> {
  savedAt: string;
  value: T;
}

/** Older installs stored the payload alone. Those reads stay usable and are marked as saved at an unknown time. */
export function unpackCache<T>(parsed: unknown): CachedRead<T> | null {
  if (parsed === null || parsed === undefined) return null;
  if (typeof parsed === "object" && !Array.isArray(parsed) && "savedAt" in parsed && "value" in parsed) {
    const savedAt = parsed.savedAt;
    if (typeof savedAt === "string") return { savedAt, value: parsed.value as T };
  }
  return { savedAt: "", value: parsed as T };
}
