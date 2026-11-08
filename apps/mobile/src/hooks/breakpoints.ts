import { breakpoint } from "@/theme/tokens";

export type BreakpointName = "smallPhone" | "phone" | "largePhone" | "tablet" | "largeTablet";

export function breakpointOf(width: number): BreakpointName {
  if (width < breakpoint.smallPhone) return "smallPhone";
  if (width < breakpoint.largePhone) return "phone";
  if (width < breakpoint.tablet) return "largePhone";
  if (width < breakpoint.largeTablet) return "tablet";
  return "largeTablet";
}

export function gridColumns(width: number): number {
  const name = breakpointOf(width);
  if (name === "largeTablet") return 4;
  if (name === "tablet") return 3;
  if (name === "smallPhone") return 1;
  return 2;
}

/** Directory cards stay one column on phones so titles and summaries can wrap. */
export function directoryColumns(width: number): number {
  const name = breakpointOf(width);
  if (name === "largeTablet") return 3;
  if (name === "tablet") return 2;
  return 1;
}

/** Side-by-side record browsing needs a wide window, including large-phone landscape. */
export function masterDetail(width: number): boolean {
  return width >= 720;
}

/** Tab screens already sit above the system navigation bar. Stack screens pad it themselves. */
export function safeBottom(inTabs: boolean, bottomInset: number): number {
  return inTabs ? 0 : Math.max(0, bottomInset);
}

export function sheetMaxHeight(windowHeight: number, topInset: number, bottomInset: number): number {
  const available = windowHeight - Math.max(0, topInset) - Math.max(0, bottomInset) - 24;
  return Math.max(160, Math.min(available, windowHeight * 0.86, 720));
}

export function modalMaxHeight(windowHeight: number, topInset: number, bottomInset: number): number {
  return Math.max(160, windowHeight - Math.max(0, topInset) - Math.max(0, bottomInset) - 48);
}

export const FONT_SCALE_CAP = 1.5;

export function scaledSize(size: number, fontScale: number): number {
  const scale = Math.min(Math.max(fontScale || 1, 1), FONT_SCALE_CAP);
  return Math.round(size * scale);
}

/** Line height stays above the scaled font so Android and iOS do not clip glyphs. */
export function scaledLineHeight(line: number, font: number, fontScale: number): number {
  return Math.max(scaledSize(line, fontScale), Math.ceil(scaledSize(font, fontScale) * 1.25));
}

/** Equal tracks. Padding lives inside each track so a gap cannot push the row past 100%. */
export function gridTrackPercent(columns: number): number {
  return 100 / Math.max(1, columns);
}

export function columnsFit(contentWidth: number, columns: number, gap: number): boolean {
  const count = Math.max(1, columns);
  if (contentWidth <= 0) return false;
  const width = (contentWidth - gap * (count - 1)) / count;
  return width > 0 && width * count + gap * (count - 1) <= contentWidth + 0.01;
}
