import type { ScaleConfig } from "../../lib/tauri";

/** The weighing scale this register reads, kept on the machine it is plugged into. */
const CONFIG_KEY = "ai-pos.scale";

export const SCALE_BAUD_RATES = [2400, 4800, 9600, 19200] as const;

export const DEFAULT_SCALE_CONFIG: ScaleConfig = { port: "", baud: 9600, protocol: "continuous" };

export function loadScaleConfig(): ScaleConfig | null {
  try {
    const raw = localStorage.getItem(CONFIG_KEY);
    return raw ? (JSON.parse(raw) as ScaleConfig) : null;
  } catch {
    return null;
  }
}

export function saveScaleConfig(config: ScaleConfig): void {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
