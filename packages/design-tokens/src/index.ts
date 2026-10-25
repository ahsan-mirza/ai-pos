export const colors = {
  accent: "#F26A21",
  danger: "#DC2626",
  warning: "#D97706",
  neutral: "#CBCECE",
  canvas: "#EAEAEA",
  border: "#DBDBDB",
  charcoal: "#222026",
  card: "#FFFFFF",
  surface: "#F3F4F6",
} as const;

/** The first series follows the runtime primary color; use these as CSS values (`style`), not SVG attributes. */
export const chartColors = ["var(--primary)", "#222026", "#8A868E", "#CBCECE"] as const;

export const fontFamily = "Archivo, sans-serif";

export const radius = {
  card: "20px",
} as const;
