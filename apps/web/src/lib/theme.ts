/** Runtime primary (accent) color for the admin portal; the business setting lives on the API. */

export const DEFAULT_PRIMARY = "#FD3706";

export const PRIMARY_PRESETS = [
  { name: "Vibrant Orange", hex: "#FF4500" },
  { name: "Royal Blue", hex: "#2563EB" },
  { name: "Emerald Green", hex: "#10B981" },
  { name: "Deep Purple", hex: "#8B5CF6" },
  { name: "Rose Pink", hex: "#F43F5E" },
] as const;

const STORAGE_KEY = "ai-pos.primary-color";

/** "#abc" / "abc123" / "#ABC123" → "#ABC123"; null when it is not a 3- or 6-digit hex color. */
export function normalizeHex(value: string): string | null {
  const text = value.trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(text)) {
    return `#${text
      .split("")
      .map((char) => char + char)
      .join("")
      .toUpperCase()}`;
  }
  return /^[0-9a-f]{6}$/i.test(text) ? `#${text.toUpperCase()}` : null;
}

function channels(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((channel) => {
    const unit = channel / 255;
    return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast of white text on `hex`; buttons and active pills put white labels on the primary color. */
export function contrastWithWhite(hex: string): number {
  return 1.05 / (luminance(hex) + 0.05);
}

/** Sets --primary / --primary-rgb / --primary-hover-rgb on <html>; null restores the brand default. */
export function applyPrimaryColor(hex: string | null): void {
  const color = (hex && normalizeHex(hex)) || DEFAULT_PRIMARY;
  const [r, g, b] = channels(color);
  const style = document.documentElement.style;
  style.setProperty("--primary", color);
  style.setProperty("--primary-rgb", `${r} ${g} ${b}`);
  style.setProperty("--primary-hover-rgb", [r, g, b].map((channel) => Math.round(channel * 0.88)).join(" "));
}

export function storedPrimaryColor(): string | null {
  try {
    return normalizeHex(localStorage.getItem(STORAGE_KEY) ?? "");
  } catch {
    return null;
  }
}

/** Applies and remembers the business color so the next launch paints it before the API answers. */
export function syncPrimaryColor(hex: string | null): void {
  applyPrimaryColor(hex);
  try {
    if (hex) localStorage.setItem(STORAGE_KEY, hex);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage disabled: the color still applies for this session.
  }
}
