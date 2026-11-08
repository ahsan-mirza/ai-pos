/**
 * AxizPOS mobile tokens.
 * Primary and charcoal come from packages/design-tokens (the approved brand).
 * Surfaces follow the mobile reference: white cards on a light grey canvas.
 */
export const palette = {
  primary: "#F26A21",
  primaryPressed: "#D55D1D",
  danger: "#E5484D",
  warning: "#F59E0B",
  success: "#16A36A",
  info: "#3B82F6",
  canvas: "#F7F8FA",
  surface: "#FFFFFF",
  surfaceMuted: "#F3F4F6",
  text: "#222026",
  textSecondary: "#8A94A6",
  border: "#E7EAF0",
  white: "#FFFFFF",
  overlay: "rgba(23, 32, 51, 0.45)",
} as const;

export const fontSize = {
  xs: 12,
  sm: 13,
  md: 15,
  lg: 17,
  xl: 20,
  xxl: 24,
  display: 28,
} as const;

export const lineHeight = {
  xs: 16,
  sm: 18,
  md: 22,
  lg: 24,
  xl: 28,
  xxl: 32,
  display: 34,
} as const;

export const fontWeight = {
  regular: "400",
  medium: "500",
  semibold: "600",
  bold: "700",
} as const;

export const space = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 14,
  lg: 16,
  xl: 18,
  pill: 999,
} as const;

export const shadow = {
  none: {
    shadowColor: "transparent",
    shadowOpacity: 0,
    shadowRadius: 0,
    shadowOffset: { width: 0, height: 0 },
    elevation: 0,
  },
  card: {
    shadowColor: "#172033",
    shadowOpacity: 0.04,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },
} as const;

export const iconSize = {
  sm: 16,
  md: 20,
  lg: 24,
  xl: 28,
} as const;

export const controlHeight = {
  xs: 28,
  sm: 36,
  md: 52,
  lg: 52,
  xl: 60,
} as const;

export const screenPadding = {
  smallPhone: 16,
  phone: 20,
  tablet: 24,
} as const;

export const touchTarget = 44;

export const motion = {
  fast: 120,
  normal: 220,
  slow: 320,
} as const;

export const breakpoint = {
  smallPhone: 360,
  largePhone: 430,
  tablet: 600,
  largeTablet: 900,
} as const;

export interface AppTheme {
  colors: {
    primary: string;
    primaryPressed: string;
    danger: string;
    warning: string;
    success: string;
    info: string;
    canvas: string;
    surface: string;
    surfaceMuted: string;
    text: string;
    textSecondary: string;
    border: string;
    white: string;
    overlay: string;
  };
  fontSize: typeof fontSize;
  lineHeight: typeof lineHeight;
  fontWeight: typeof fontWeight;
  space: typeof space;
  radius: typeof radius;
  shadow: typeof shadow;
  iconSize: typeof iconSize;
  controlHeight: typeof controlHeight;
  screenPadding: typeof screenPadding;
  touchTarget: number;
  motion: typeof motion;
  breakpoint: typeof breakpoint;
}

export function createTheme(primary: string = palette.primary): AppTheme {
  return {
    colors: { ...palette, primary, primaryPressed: primary },
    fontSize,
    lineHeight,
    fontWeight,
    space,
    radius,
    shadow,
    iconSize,
    controlHeight,
    screenPadding,
    touchTarget,
    motion,
    breakpoint,
  };
}

export const defaultTheme = createTheme();
