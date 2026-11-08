import { type ReactNode } from "react";
import { ActivityIndicator, Pressable, View, type StyleProp, type ViewStyle } from "react-native";
import { AppText } from "@/components/primitives/Text";
import { useTheme } from "@/theme/ThemeProvider";
import type { AppTheme } from "@/theme/tokens";

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger" | "success" | "icon" | "text" | "link";
export type ButtonSize = "xs" | "sm" | "md" | "lg" | "xl";

export interface ButtonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  icon?: ReactNode;
  iconPosition?: "start" | "end";
  label?: string;
  accessibilityLabel: string;
  onPress?: () => void;
  borderRadius?: number;
  style?: StyleProp<ViewStyle>;
}

function colors(theme: AppTheme, variant: ButtonVariant, pressed: boolean): { background: string; border: string; text: string } {
  const primary = pressed ? theme.colors.primaryPressed : theme.colors.primary;
  if (variant === "primary") return { background: primary, border: primary, text: theme.colors.white };
  if (variant === "danger") return { background: theme.colors.danger, border: theme.colors.danger, text: theme.colors.white };
  if (variant === "success") return { background: theme.colors.success, border: theme.colors.success, text: theme.colors.white };
  if (variant === "secondary") return { background: theme.colors.surfaceMuted, border: theme.colors.surfaceMuted, text: theme.colors.text };
  if (variant === "outline") return { background: theme.colors.surface, border: theme.colors.border, text: theme.colors.text };
  return { background: "transparent", border: "transparent", text: variant === "link" ? theme.colors.primary : theme.colors.text };
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled = false,
  fullWidth = false,
  icon,
  iconPosition = "start",
  label,
  accessibilityLabel,
  onPress,
  borderRadius,
  style,
}: ButtonProps) {
  const theme = useTheme();
  const inline = variant === "link" || variant === "text";
  const height = Math.max(variant === "icon" ? theme.touchTarget : theme.controlHeight[size], inline ? 0 : theme.touchTarget);
  const horizontal = variant === "icon" || inline ? theme.space.sm : size === "xs" ? theme.space.sm : theme.space.lg;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => {
        const tone = colors(theme, variant, pressed);
        return [
          {
            minHeight: inline ? undefined : height,
            paddingHorizontal: horizontal,
            paddingVertical: inline ? 0 : theme.space.xs,
            borderRadius: borderRadius ?? (variant === "link" ? 0 : theme.radius.md),
            backgroundColor: tone.background,
            borderWidth: variant === "outline" ? 1 : 0,
            borderColor: tone.border,
            alignItems: "center",
            justifyContent: "center",
            flexDirection: iconPosition === "end" ? "row-reverse" : "row",
            gap: theme.space.sm,
            opacity: disabled ? 0.45 : pressed ? 0.92 : 1,
            alignSelf: fullWidth ? "stretch" : "flex-start",
            maxWidth: "100%",
          },
          style,
        ];
      }}
    >
      {loading ? <ActivityIndicator color={variant === "primary" || variant === "danger" || variant === "success" ? theme.colors.white : theme.colors.primary} /> : icon}
      {label ? (
        <AppText variant={size === "xs" || size === "sm" ? "caption" : "body"} weight="semibold" tone={variant === "primary" || variant === "danger" || variant === "success" ? "inverse" : variant === "link" ? "primary" : "primary"} style={[{ flexShrink: 1, textAlign: "center" }, variant === "link" ? { color: theme.colors.primary, textDecorationLine: "underline" } : variant === "outline" || variant === "secondary" || variant === "ghost" || variant === "text" || variant === "icon" ? { color: theme.colors.text } : undefined]}>
          {label}
        </AppText>
      ) : null}
    </Pressable>
  );
}

export function ButtonRow({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return <View style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.space.sm }}>{children}</View>;
}
