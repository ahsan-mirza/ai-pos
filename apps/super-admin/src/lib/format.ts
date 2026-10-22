import { formatMoney } from "@ai-pos/shared-types";

export function bytes(value: number | null): string {
  if (value === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function money(cents: number, currency: string | null): string {
  return currency ? formatMoney(cents, currency) : (cents / 100).toFixed(2);
}

export function date(value: string | null): string {
  return value ? value.slice(0, 10) : "—";
}

export function when(value: string | null): string {
  return value ? value.slice(0, 16).replace("T", " ") : "—";
}
