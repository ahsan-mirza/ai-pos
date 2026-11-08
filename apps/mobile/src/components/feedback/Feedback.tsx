import { ActivityIndicator, View } from "react-native";
import { Button } from "@/components/buttons/Button";
import { AppText } from "@/components/primitives/Text";
import { useTheme } from "@/theme/ThemeProvider";

export function StatusBadge(props: { label: string; tone?: "neutral" | "success" | "warning" | "danger" | "info" }) {
  const theme = useTheme();
  const tone = props.tone ?? "neutral";
  const color = tone === "success" ? theme.colors.success : tone === "warning" ? theme.colors.warning : tone === "danger" ? theme.colors.danger : tone === "info" ? theme.colors.info : theme.colors.textSecondary;
  return (
    <View style={{ alignSelf: "flex-start", borderRadius: theme.radius.pill, paddingHorizontal: theme.space.sm, paddingVertical: 4, backgroundColor: theme.colors.surfaceMuted }}>
      <AppText variant="caption" weight="semibold" style={{ color }}>{props.label}</AppText>
    </View>
  );
}

export function Avatar(props: { name: string }) {
  const theme = useTheme();
  const letter = props.name.trim().charAt(0).toUpperCase() || "?";
  return (
    <View accessibilityLabel={props.name} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: theme.colors.surfaceMuted, alignItems: "center", justifyContent: "center" }}>
      <AppText weight="bold">{letter}</AppText>
    </View>
  );
}

export function EmptyState(props: { title: string; message?: string; actionLabel?: string; onAction?: () => void }) {
  return (
    <View style={{ paddingVertical: 24, gap: 8 }}>
      <AppText weight="semibold">{props.title}</AppText>
      {props.message ? <AppText tone="secondary">{props.message}</AppText> : null}
      {props.actionLabel && props.onAction ? <Button label={props.actionLabel} accessibilityLabel={props.actionLabel} onPress={props.onAction} /> : null}
    </View>
  );
}

export function ErrorState(props: { message: string; onRetry?: () => void; retryLabel: string }) {
  return (
    <View style={{ padding: 16, gap: 12 }}>
      <AppText tone="danger">{props.message}</AppText>
      {props.onRetry ? <Button label={props.retryLabel} accessibilityLabel={props.retryLabel} onPress={props.onRetry} /> : null}
    </View>
  );
}

export function LoadingSkeleton(props: { lines?: number }) {
  const theme = useTheme();
  return (
    <View style={{ gap: theme.space.sm }}>
      {Array.from({ length: props.lines ?? 4 }, (_, index) => (
        <View key={index} style={{ height: index === 0 ? 28 : 16, width: index === 0 ? "50%" : "100%", borderRadius: 8, backgroundColor: theme.colors.surfaceMuted }} />
      ))}
    </View>
  );
}

export function LoadingBlock(props: { label: string }) {
  const theme = useTheme();
  return (
    <View style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 8 }}>
      <ActivityIndicator color={theme.colors.primary} />
      <AppText tone="secondary">{props.label}</AppText>
    </View>
  );
}
