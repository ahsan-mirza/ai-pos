import { Text as NativeText, useWindowDimensions, type TextProps, type TextStyle } from "react-native";
import { scaledLineHeight, scaledSize } from "@/hooks/breakpoints";
import { useI18n } from "@/i18n/I18nProvider";
import { useTheme } from "@/theme/ThemeProvider";

type Variant = "display" | "title" | "heading" | "body" | "caption" | "label";

const size: Record<Variant, "display" | "xxl" | "lg" | "md" | "sm" | "xs"> = {
  display: "display",
  title: "xxl",
  heading: "lg",
  body: "md",
  caption: "sm",
  label: "xs",
};

export function AppText({
  variant = "body",
  tone = "primary",
  weight,
  style,
  ...props
}: TextProps & { variant?: Variant; tone?: "primary" | "secondary" | "inverse" | "danger" | "success"; weight?: "regular" | "medium" | "semibold" | "bold" }) {
  const theme = useTheme();
  const { fontScale } = useWindowDimensions();
  const { isRTL } = useI18n();
  const color =
    tone === "secondary" ? theme.colors.textSecondary : tone === "inverse" ? theme.colors.white : tone === "danger" ? theme.colors.danger : tone === "success" ? theme.colors.success : theme.colors.text;
  const step = size[variant];
  const textStyle: TextStyle = {
    color,
    fontSize: scaledSize(theme.fontSize[step], fontScale),
    lineHeight: scaledLineHeight(theme.lineHeight[step], theme.fontSize[step], fontScale),
    fontWeight: theme.fontWeight[weight ?? (variant === "body" || variant === "caption" ? "regular" : "semibold")],
    textAlign: "auto",
    writingDirection: isRTL ? "rtl" : "ltr",
  };
  return <NativeText {...props} allowFontScaling={false} style={[textStyle, style]} />;
}
