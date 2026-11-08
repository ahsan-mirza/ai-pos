import { useState, type ReactNode } from "react";
import { Pressable, View } from "react-native";
import { MiniSpark } from "@/components/charts/Charts";
import { AppText } from "@/components/primitives/Text";
import { useTheme } from "@/theme/ThemeProvider";

function Shell({ children, onPress }: { children: ReactNode; onPress?: () => void }) {
  const theme = useTheme();
  const body = (
    <View style={{ backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.space.lg, gap: theme.space.sm, ...theme.shadow.card }}>
      {children}
    </View>
  );
  if (!onPress) return body;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={{ alignSelf: "stretch" }}>
      {body}
    </Pressable>
  );
}

export function DefaultCard(props: { title: string; children?: ReactNode; onPress?: () => void }) {
  return (
    <Shell onPress={props.onPress}>
      <AppText weight="semibold">{props.title}</AppText>
      {props.children}
    </Shell>
  );
}

export function KPICard(props: {
  title: string;
  value: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "flat";
  percentage?: string;
  comparison?: string;
  status?: string;
  loading?: boolean;
  series?: number[];
}) {
  const theme = useTheme();
  const trendColor = props.trend === "down" ? theme.colors.danger : props.trend === "up" ? theme.colors.success : theme.colors.textSecondary;
  return (
    <Shell>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <AppText variant="caption" tone="secondary">{props.title}</AppText>
        {props.icon}
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: theme.space.sm }}>
        {props.loading ? <View style={{ height: 28, width: "60%", borderRadius: 8, backgroundColor: theme.colors.surfaceMuted }} /> : <AppText variant="title" numberOfLines={1} style={{ flex: 1 }}>{props.value}</AppText>}
        {props.series ? <MiniSpark values={props.series} /> : null}
      </View>
      <AppText variant="caption" numberOfLines={1} style={{ color: props.percentage ? trendColor : theme.colors.textSecondary }}>
        {[props.percentage, props.comparison, props.status].filter(Boolean).join(" · ") || " "}
      </AppText>
    </Shell>
  );
}

export function SummaryCard(props: { title: string; lines: { label: string; value: string }[] }) {
  return (
    <Shell>
      <AppText weight="semibold">{props.title}</AppText>
      {props.lines.map((line) => (
        <View key={line.label} style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
          <AppText variant="caption" tone="secondary" style={{ flex: 1 }}>{line.label}</AppText>
          <AppText variant="caption" weight="semibold" style={{ flexShrink: 1, maxWidth: "58%" }}>{line.value}</AppText>
        </View>
      ))}
    </Shell>
  );
}

export function ActionCard(props: { title: string; subtitle?: string; onPress: () => void }) {
  return (
    <Shell onPress={props.onPress}>
      <AppText weight="semibold">{props.title}</AppText>
      {props.subtitle ? <AppText variant="caption" tone="secondary">{props.subtitle}</AppText> : null}
    </Shell>
  );
}

export function InformationCard(props: { title?: string; rows: { label: string; value: string }[] }) {
  return <SummaryCard title={props.title ?? "Details"} lines={props.rows} />;
}

export function StatusCard(props: { title: string; status: string; tone?: "success" | "warning" | "danger" | "info" }) {
  const theme = useTheme();
  const color = props.tone === "danger" ? theme.colors.danger : props.tone === "warning" ? theme.colors.warning : props.tone === "info" ? theme.colors.info : theme.colors.success;
  return (
    <Shell>
      <AppText weight="semibold">{props.title}</AppText>
      <AppText weight="semibold" style={{ color }}>{props.status}</AppText>
    </Shell>
  );
}

export function ExpandableCard(props: { title: string; summary?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Shell onPress={() => setOpen((current) => !current)}>
      <AppText weight="semibold">{props.title}</AppText>
      {props.summary ? <AppText variant="caption" tone="secondary">{props.summary}</AppText> : null}
      {open ? props.children : null}
    </Shell>
  );
}

export function ListCard(props: { title: string; subtitle?: string; amount?: string; status?: string; leading?: ReactNode; onPress?: () => void }) {
  return (
    <Shell onPress={props.onPress}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        {props.leading}
        <View style={{ flex: 1, minWidth: 0 }}>
          <AppText weight="semibold">{props.title}</AppText>
          {props.subtitle ? <AppText variant="caption" tone="secondary">{props.subtitle}</AppText> : null}
        </View>
        <View style={{ flexShrink: 1, maxWidth: "46%", alignItems: "flex-end" }}>
          {props.amount ? <AppText weight="semibold">{props.amount}</AppText> : null}
          {props.status ? <AppText variant="caption" tone="secondary">{props.status}</AppText> : null}
        </View>
      </View>
    </Shell>
  );
}

export function ProductCard(props: { name: string; sku: string; price: string; stock?: string; onPress?: () => void }) {
  return <ListCard title={props.name} subtitle={props.sku} amount={props.price} status={props.stock} onPress={props.onPress} />;
}

export function TransactionCard(props: { title: string; when?: string; amount: string; status?: string; onPress?: () => void }) {
  return <ListCard title={props.title} subtitle={props.when} amount={props.amount} status={props.status} onPress={props.onPress} />;
}
