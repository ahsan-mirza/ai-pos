import { Children, type ReactNode } from "react";
import { Pressable, View } from "react-native";
import { useSegments } from "expo-router";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AppText } from "@/components/primitives/Text";
import { useI18n } from "@/i18n/I18nProvider";
import { safeBottom } from "@/hooks/breakpoints";
import { useNetwork } from "@/hooks/useNetwork";
import { useResponsive } from "@/hooks/useResponsive";
import { useTheme } from "@/theme/ThemeProvider";

export function ScreenContainer(props: { children: ReactNode; scroll?: boolean; footer?: ReactNode; embedded?: boolean }) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const layout = useResponsive();
  const { online } = useNetwork();
  const { t } = useI18n();
  const inTabs = useSegments().includes("(tabs)");
  const top = props.embedded ? 0 : insets.top;
  const left = props.embedded ? 0 : insets.left;
  const right = props.embedded ? 0 : insets.right;
  const bottom = props.embedded ? 0 : safeBottom(inTabs, insets.bottom);
  return (
    <View style={{ flex: 1, minWidth: 0, paddingTop: top, paddingLeft: left, paddingRight: right, backgroundColor: theme.colors.canvas }}>
      {online ? null : (
        <View style={{ backgroundColor: theme.colors.warning, paddingHorizontal: layout.spacing.page, paddingVertical: theme.space.sm }}>
          <AppText variant="caption">{t("offline")}</AppText>
        </View>
      )}
      {props.scroll ? (
        <KeyboardAwareScrollView
          bottomOffset={16}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ padding: layout.spacing.page, paddingBottom: (props.footer ? 0 : bottom) + theme.space.xxl, gap: theme.space.md }}
        >
          {props.children}
        </KeyboardAwareScrollView>
      ) : (
        <View style={{ flex: 1, minWidth: 0, paddingBottom: bottom }}>{props.children}</View>
      )}
      {props.footer ? (
        <KeyboardStickyView offset={{ closed: 0, opened: 0 }}>
          <View style={{ padding: layout.spacing.page, paddingBottom: bottom + theme.space.md, backgroundColor: theme.colors.surface, borderTopWidth: 1, borderTopColor: theme.colors.border }}>
            {props.footer}
          </View>
        </KeyboardStickyView>
      ) : null}
    </View>
  );
}

export function ResponsiveGrid(props: { columns: number; gap: number; children: ReactNode }) {
  const columns = Math.max(1, props.columns);
  const pad = props.gap / 2;
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", marginHorizontal: -pad }}>
      {Children.map(props.children, (child, index) => (
        <View key={index} style={{ width: `${100 / columns}%`, paddingHorizontal: pad, paddingBottom: props.gap }}>
          {child}
        </View>
      ))}
    </View>
  );
}

export function ScreenTitle(props: { title: string; subtitle?: string }) {
  return (
    <View style={{ gap: 4 }}>
      <AppText variant="title">{props.title}</AppText>
      {props.subtitle ? <AppText tone="secondary">{props.subtitle}</AppText> : null}
    </View>
  );
}

export function AppHeader(props: { title: string; onBack?: () => void; action?: ReactNode }) {
  const theme = useTheme();
  const { t, isRTL } = useI18n();
  return (
    <View style={{ minHeight: 52, paddingHorizontal: theme.space.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
        {props.onBack ? (
          <Pressable accessibilityRole="button" accessibilityLabel={t("back")} onPress={props.onBack} style={{ minWidth: theme.touchTarget, minHeight: theme.touchTarget, justifyContent: "center" }}>
            <AppText style={{ color: theme.colors.primary }}>{isRTL ? "→" : "←"}</AppText>
          </Pressable>
        ) : null}
        <AppText variant="heading" numberOfLines={2} style={{ flex: 1 }}>{props.title}</AppText>
      </View>
      {props.action ? <View style={{ flexShrink: 0, maxWidth: "46%" }}>{props.action}</View> : null}
    </View>
  );
}

export function StickyActionBar(props: { children: ReactNode }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {Children.map(props.children, (child, index) => (
        <View key={index} style={{ flexGrow: 1, flexBasis: 140, minWidth: 0 }}>
          {child}
        </View>
      ))}
    </View>
  );
}

export function FormFooter(props: { children: ReactNode }) {
  return <StickyActionBar>{props.children}</StickyActionBar>;
}

export function FloatingActionButton(props: { label: string; onPress: () => void }) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { isRTL } = useI18n();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={props.label}
      onPress={props.onPress}
      style={{
        position: "absolute",
        left: isRTL ? 16 : undefined,
        right: isRTL ? undefined : 16,
        bottom: insets.bottom + 16,
        minHeight: theme.touchTarget,
        paddingHorizontal: theme.space.lg,
        borderRadius: theme.radius.pill,
        backgroundColor: theme.colors.primary,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <AppText tone="inverse" weight="semibold">{props.label}</AppText>
    </Pressable>
  );
}

export function KeyboardAwareContainer(props: { children: ReactNode }) {
  const layout = useResponsive();
  return (
    <KeyboardAwareScrollView bottomOffset={16} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: layout.spacing.page, gap: layout.spacing.gap }}>
      {props.children}
    </KeyboardAwareScrollView>
  );
}
