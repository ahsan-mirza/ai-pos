import { useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useKeyboardState } from "react-native-keyboard-controller";
import { breakpoint, screenPadding } from "@/theme/tokens";
import { breakpointOf, directoryColumns, gridColumns, masterDetail, type BreakpointName } from "@/hooks/breakpoints";

export type { BreakpointName } from "@/hooks/breakpoints";
export { breakpointOf, gridColumns } from "@/hooks/breakpoints";

export function useWindowSize() {
  return useWindowDimensions();
}

export function useBreakpoint(): BreakpointName {
  const { width } = useWindowDimensions();
  return breakpointOf(width);
}

export function useScreenSize() {
  const { width, height } = useWindowDimensions();
  return { width, height, breakpoint: breakpointOf(width) };
}

export function useOrientation(): "portrait" | "landscape" {
  const { width, height } = useWindowDimensions();
  return width > height ? "landscape" : "portrait";
}

export function useSafeArea() {
  return useSafeAreaInsets();
}

export function useKeyboardHeight(): number {
  return useKeyboardState((state) => state.height);
}

export function useResponsiveSpacing() {
  const { width } = useWindowDimensions();
  const name = breakpointOf(width);
  const page = name === "smallPhone" ? screenPadding.smallPhone : name === "tablet" || name === "largeTablet" ? screenPadding.tablet : screenPadding.phone;
  const card = name === "smallPhone" ? 12 : 16;
  return { page, card, gap: name === "smallPhone" ? 8 : 12 };
}

export function useResponsiveFontSize() {
  const { width, fontScale } = useWindowDimensions();
  const compact = width < breakpoint.smallPhone ? 0.94 : 1;
  return {
    scale: (size: number) => Math.round(size * compact * Math.min(fontScale, 1.3)),
  };
}

export function useResponsiveWidth() {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const content = width - insets.left - insets.right;
  return {
    window: width,
    content,
    percent: (ratio: number) => content * ratio,
    modal: Math.min(content - 32, breakpointOf(width) === "largeTablet" ? 560 : 420),
    card: (columns: number, gap: number, padding: number) => (content - padding * 2 - gap * (columns - 1)) / columns,
  };
}

export function useResponsiveHeight() {
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  return {
    window: height,
    content: height - insets.top - insets.bottom,
    percent: (ratio: number) => height * ratio,
    sheet: Math.min(height * 0.86, 720),
  };
}

export function useResponsive() {
  const window = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const keyboard = useKeyboardHeight();
  const spacing = useResponsiveSpacing();
  const fonts = useResponsiveFontSize();
  const name = breakpointOf(window.width);
  return {
    width: window.width,
    height: window.height,
    fontScale: window.fontScale,
    breakpoint: name,
    isSmallPhone: name === "smallPhone",
    isPhone: name === "smallPhone" || name === "phone" || name === "largePhone",
    isTablet: name === "tablet" || name === "largeTablet",
    isLargeTablet: name === "largeTablet",
    isLandscape: window.width > window.height,
    columns: gridColumns(window.width),
    directoryColumns: directoryColumns(window.width),
    masterDetail: masterDetail(window.width),
    insets,
    keyboard,
    spacing,
    fonts,
  };
}
