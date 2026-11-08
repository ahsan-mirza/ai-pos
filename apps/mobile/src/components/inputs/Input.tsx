import { forwardRef, useImperativeHandle, useRef, useState, type ReactNode } from "react";
import { Pressable, TextInput, View, type KeyboardTypeOptions, type TextInputProps } from "react-native";
import { Icon } from "@/components/primitives/Icon";
import { AppText } from "@/components/primitives/Text";
import { useI18n } from "@/i18n/I18nProvider";
import { useTheme } from "@/theme/ThemeProvider";

export type InputVariant = "text" | "email" | "password" | "number" | "currency" | "phone" | "search" | "multiline" | "date" | "time" | "readonly";

export interface InputProps extends Omit<TextInputProps, "editable"> {
  variant?: InputVariant;
  label?: string;
  helperText?: string;
  error?: string;
  required?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
  onClear?: () => void;
  maxLength?: number;
  disabled?: boolean;
}

function keyboard(variant: InputVariant): KeyboardTypeOptions {
  if (variant === "email") return "email-address";
  if (variant === "number" || variant === "currency") return "decimal-pad";
  if (variant === "phone") return "phone-pad";
  return "default";
}

export const Input = forwardRef<{ focus: () => void }, InputProps>(function Input({
  variant = "text",
  label,
  helperText,
  error,
  required = false,
  leading,
  trailing,
  onClear,
  maxLength,
  disabled = false,
  value,
  style,
  ...props
}, ref) {
  const theme = useTheme();
  const inputRef = useRef<{ focus: () => void } | null>(null);
  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }));
  const { t, isRTL } = useI18n();
  const [hidden, setHidden] = useState(true);
  const [focused, setFocused] = useState(false);
  const readOnly = variant === "readonly" || disabled;
  const text = typeof value === "string" ? value : "";
  return (
    <View style={{ gap: theme.space.xs, alignSelf: "stretch" }}>
      {label ? (
        <AppText variant="label" weight="medium" tone="secondary">
          {label}
          {required ? " *" : ""}
        </AppText>
      ) : null}
      <View
        style={{
          minHeight: variant === "multiline" ? 96 : Math.max(theme.controlHeight.md, theme.touchTarget),
          borderWidth: 1,
          borderColor: error ? theme.colors.danger : focused ? theme.colors.primary : theme.colors.border,
          borderRadius: theme.radius.md,
          backgroundColor: theme.colors.surfaceMuted,
          paddingHorizontal: theme.space.md,
          flexDirection: "row",
          alignItems: variant === "multiline" ? "flex-start" : "center",
          gap: theme.space.sm,
        }}
      >
        {leading}
        <TextInput
          ref={(node) => {
            inputRef.current = node as { focus: () => void } | null;
          }}
          {...props}
          value={value}
          editable={!readOnly}
          secureTextEntry={variant === "password" && hidden}
          keyboardType={keyboard(variant)}
          returnKeyType={variant === "search" ? "search" : props.returnKeyType}
          autoCorrect={variant === "search" ? false : props.autoCorrect}
          autoCapitalize={variant === "email" || variant === "search" ? "none" : props.autoCapitalize}
          multiline={variant === "multiline"}
          maxLength={maxLength}
          placeholderTextColor={theme.colors.textSecondary}
          accessibilityLabel={props.accessibilityLabel ?? label}
          onFocus={(event) => {
            setFocused(true);
            props.onFocus?.(event);
          }}
          onBlur={(event) => {
            setFocused(false);
            props.onBlur?.(event);
          }}
          style={[
            {
              flex: 1,
              color: theme.colors.text,
              fontSize: theme.fontSize.md,
              paddingVertical: theme.space.sm,
              minHeight: variant === "multiline" ? 72 : theme.touchTarget - theme.space.sm,
              textAlign: "auto",
              writingDirection: isRTL ? "rtl" : "ltr",
            },
            style,
          ]}
        />
        {variant === "password" ? (
          <Pressable accessibilityRole="button" accessibilityLabel={hidden ? t("showPassword") : t("hidePassword")} onPress={() => setHidden((current) => !current)} style={{ minWidth: theme.touchTarget, minHeight: theme.touchTarget, alignItems: "center", justifyContent: "center" }}>
            <Icon name={hidden ? "eye" : "eyeOff"} size={theme.iconSize.md} color={theme.colors.textSecondary} />
          </Pressable>
        ) : null}
        {onClear && text.length > 0 ? (
          <Pressable accessibilityRole="button" accessibilityLabel={t("clear")} onPress={onClear}>
            <AppText variant="caption">{t("clear")}</AppText>
          </Pressable>
        ) : null}
        {trailing}
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: theme.space.sm }}>
        <AppText variant="caption" tone={error ? "danger" : "secondary"} style={{ flex: 1 }}>
          {error ?? helperText ?? ""}
        </AppText>
        {maxLength ? (
          <AppText variant="caption" tone="secondary">
            {text.length}/{maxLength}
          </AppText>
        ) : null}
      </View>
    </View>
  );
});
