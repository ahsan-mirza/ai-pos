/**
 * The register's single primary accent. Every highlight (active nav, mode toggle, selected tender, totals, primary
 * buttons) reads the --primary-* variables, so changing the color here re-themes the whole terminal at once.
 */

export const DEFAULT_PRIMARY = "#FF4500";

export const PRIMARY_PRESETS = [
  { name: "Vibrant Orange", hex: "#FF4500" },
  { name: "Royal Blue", hex: "#2563EB" },
  { name: "Emerald Green", hex: "#10B981" },
  { name: "Deep Purple", hex: "#8B5CF6" },
  { name: "Rose Pink", hex: "#F43F5E" },
  { name: "Midnight Zinc", hex: "#3F3F46" },
] as const;

export const PRIMARY_STORAGE_KEY = "ai-pos.register.primary-color";

/** Shade → mix toward white (positive) or black (negative); 500 is the chosen color itself. */
const SHADES: Record<number, number> = { 50: 0.92, 100: 0.84, 200: 0.68, 300: 0.45, 400: 0.22, 500: 0, 600: -0.14, 700: -0.28 };

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

export function shade(hex: string, step: number): [number, number, number] {
  const mix = SHADES[step] ?? 0;
  return channels(hex).map((channel) =>
    Math.round(mix >= 0 ? channel + (255 - channel) * mix : channel * (1 + mix)),
  ) as [number, number, number];
}

/** WCAG contrast of white text on `hex`; active pills and primary buttons put white labels on the accent. */
export function contrastWithWhite(hex: string): number {
  const [r, g, b] = channels(hex).map((channel) => {
    const unit = channel / 255;
    return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05);
}

export function applyPrimaryColor(hex: string | null): void {
  const color = (hex && normalizeHex(hex)) || DEFAULT_PRIMARY;
  const style = document.documentElement.style;
  for (const step of Object.keys(SHADES).map(Number)) {
    style.setProperty(`--primary-${step}-rgb`, shade(color, step).join(" "));
  }
  style.setProperty("--primary", color);
  style.setProperty("--primary-rgb", shade(color, 500).join(" "));
  style.setProperty("--primary-hover-rgb", shade(color, 600).join(" "));
}

export function storedPrimaryColor(): string | null {
  try {
    return normalizeHex(window.localStorage.getItem(PRIMARY_STORAGE_KEY) ?? "");
  } catch {
    return null;
  }
}

/** Applies and remembers the terminal's accent; other register windows pick it up through the storage event. */
export function savePrimaryColor(hex: string | null): void {
  applyPrimaryColor(hex);
  try {
    if (hex && normalizeHex(hex) !== DEFAULT_PRIMARY) window.localStorage.setItem(PRIMARY_STORAGE_KEY, hex);
    else window.localStorage.removeItem(PRIMARY_STORAGE_KEY);
  } catch {
    // Storage unavailable: the color still applies until the app restarts.
  }
}

/** Paints the stored accent before first render and follows changes made in another register window. */
export function initPrimaryColor(): void {
  applyPrimaryColor(storedPrimaryColor());
  window.addEventListener("storage", (event) => {
    if (event.key === PRIMARY_STORAGE_KEY || event.key === null) applyPrimaryColor(storedPrimaryColor());
  });
}
