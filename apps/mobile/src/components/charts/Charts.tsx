import { useState, type ReactNode } from "react";
import { View } from "react-native";
import Svg, { Circle, Path, Rect } from "react-native-svg";
import { AppText } from "@/components/primitives/Text";
import { useTheme } from "@/theme/ThemeProvider";

function ChartFrame(props: { title?: string; empty: boolean; children: (width: number) => ReactNode }) {
  const theme = useTheme();
  const [width, setWidth] = useState(0);
  const inner = Math.max(0, width - theme.space.md * 2);
  return (
    <View
      accessibilityRole="image"
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      style={{ alignSelf: "stretch", backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, borderWidth: 1, borderColor: theme.colors.border, padding: theme.space.md, gap: theme.space.sm, ...theme.shadow.card }}
    >
      {props.title ? <AppText weight="semibold">{props.title}</AppText> : null}
      {props.empty || inner <= 0 ? <AppText tone="secondary">—</AppText> : props.children(inner)}
    </View>
  );
}

export function LineChart(props: { title?: string; values: number[]; label?: string }) {
  const theme = useTheme();
  const values = props.values.filter((value) => Number.isFinite(value));
  if (values.length < 2) return <ChartFrame title={props.title} empty>{() => null}</ChartFrame>;
  return (
    <ChartFrame title={props.title} empty={false}>
      {(width) => {
        const height = 120;
        const max = Math.max(...values);
        const min = Math.min(...values);
        const span = max - min || 1;
        const step = width / (values.length - 1);
        const points = values.map((value, index) => `${index * step},${height - ((value - min) / span) * (height - 8) - 4}`);
        const first = points[0] ?? `0,${height}`;
        return (
          <Svg width={width} height={height} accessibilityLabel={props.label ?? props.title ?? "Line chart"}>
            <Path d={`M ${points.join(" L ")}`} stroke={theme.colors.primary} strokeWidth={2} fill="none" />
            <Circle cx={Number(first.split(",")[0])} cy={Number(first.split(",")[1])} r={3} fill={theme.colors.primary} />
          </Svg>
        );
      }}
    </ChartFrame>
  );
}

export function BarChart(props: { title?: string; values: { label: string; value: number }[] }) {
  const theme = useTheme();
  return (
    <ChartFrame title={props.title} empty={props.values.length === 0}>
      {(width) => {
        const max = Math.max(1, ...props.values.map((item) => item.value));
        const gap = 6;
        const count = Math.max(props.values.length, 1);
        const barWidth = Math.max(2, (width - gap * (count - 1)) / count);
        return (
          <Svg width={width} height={120}>
            {props.values.map((item, index) => (
              <Rect key={`${item.label}-${index}`} x={index * (barWidth + gap)} y={120 - (item.value / max) * 110} width={barWidth} height={(item.value / max) * 110} rx={4} fill={theme.colors.primary} />
            ))}
          </Svg>
        );
      }}
    </ChartFrame>
  );
}

export function DonutChart(props: { title?: string; values: { label: string; value: number }[] }) {
  const theme = useTheme();
  const total = props.values.reduce((sum, item) => sum + item.value, 0);
  const colors = [theme.colors.primary, theme.colors.text, theme.colors.info, theme.colors.success, theme.colors.warning];
  let start = 0;
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  return (
    <ChartFrame title={props.title} empty={total <= 0}>
      {(width) => (
      <View style={{ flexDirection: width < 280 ? "column" : "row", alignItems: width < 280 ? "flex-start" : "center", gap: 16, maxWidth: width }}>
        <Svg width={110} height={110}>
          {props.values.map((item, index) => {
            const length = total === 0 ? 0 : (item.value / total) * circumference;
            const dash = `${length} ${circumference - length}`;
            const rotation = (start / total) * 360 - 90;
            start += item.value;
            return <Circle key={item.label} cx={55} cy={55} r={radius} stroke={colors[index % colors.length]} strokeWidth={12} fill="none" strokeDasharray={dash} rotation={rotation} origin="55,55" />;
          })}
        </Svg>
        <View style={{ flex: 1, gap: 4, minWidth: 0 }}>
          {props.values.map((item) => (
            <AppText key={item.label} variant="caption" tone="secondary">{item.label}</AppText>
          ))}
        </View>
      </View>
      )}
    </ChartFrame>
  );
}

export function AreaChart(props: { title?: string; values: number[] }) {
  return <LineChart title={props.title} values={props.values} />;
}

export function PieChart(props: { title?: string; values: { label: string; value: number }[] }) {
  return <DonutChart title={props.title} values={props.values} />;
}
