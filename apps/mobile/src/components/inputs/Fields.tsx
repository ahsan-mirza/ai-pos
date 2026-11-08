import DateTimePicker from "@react-native-community/datetimepicker";
import { useState, type ReactNode } from "react";
import { Platform, Pressable, Switch, View } from "react-native";
import { Button } from "@/components/buttons/Button";
import { Input } from "@/components/inputs/Input";
import { Icon } from "@/components/primitives/Icon";
import { AppText } from "@/components/primitives/Text";
import { useTheme } from "@/theme/ThemeProvider";

export function SearchInput(props: { value: string; onChangeText: (value: string) => void; placeholder: string; accessibilityLabel: string }) {
  const theme = useTheme();
  return <Input variant="search" leading={<Icon name="search" size={theme.iconSize.md} color={theme.colors.textSecondary} />} value={props.value} onChangeText={props.onChangeText} placeholder={props.placeholder} accessibilityLabel={props.accessibilityLabel} onClear={() => props.onChangeText("")} />;
}

export function CurrencyInput(props: { label: string; value: string; onChangeText: (value: string) => void; error?: string; currency: string }) {
  return <Input variant="currency" label={props.label} value={props.value} onChangeText={props.onChangeText} error={props.error} helperText={props.currency} accessibilityLabel={props.label} />;
}

export function PhoneInput(props: { label: string; value: string; onChangeText: (value: string) => void; error?: string }) {
  return <Input variant="phone" label={props.label} value={props.value} onChangeText={props.onChangeText} error={props.error} helperText="+971…" accessibilityLabel={props.label} />;
}

export function DateField(props: { label: string; value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const date = props.value ? new Date(`${props.value}T00:00:00`) : new Date();
  return (
    <View>
      <Pressable accessibilityRole="button" accessibilityLabel={props.label} onPress={() => setOpen(true)}>
        <View pointerEvents="none">
          <Input variant="date" label={props.label} value={props.value} />
        </View>
      </Pressable>
      {open ? (
        <DateTimePicker
          value={Number.isNaN(date.getTime()) ? new Date() : date}
          mode="date"
          onChange={(event, next) => {
            if (Platform.OS !== "ios" || event.type === "dismissed") setOpen(false);
            if (event.type === "dismissed" || !next) return;
            const month = String(next.getMonth() + 1).padStart(2, "0");
            const day = String(next.getDate()).padStart(2, "0");
            props.onChange(`${next.getFullYear()}-${month}-${day}`);
          }}
        />
      ) : null}
      {open && Platform.OS === "ios" ? <Button variant="outline" label="Done" accessibilityLabel="Done" onPress={() => setOpen(false)} /> : null}
    </View>
  );
}

export function TimeField(props: { label: string; value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <View>
      <Pressable accessibilityRole="button" accessibilityLabel={props.label} onPress={() => setOpen(true)}>
        <View pointerEvents="none">
          <Input variant="time" label={props.label} value={props.value} />
        </View>
      </Pressable>
      {open ? (
        <DateTimePicker
          value={new Date()}
          mode="time"
          onChange={(event, next) => {
            if (Platform.OS !== "ios" || event.type === "dismissed") setOpen(false);
            if (event.type === "dismissed" || !next) return;
            props.onChange(`${String(next.getHours()).padStart(2, "0")}:${String(next.getMinutes()).padStart(2, "0")}`);
          }}
        />
      ) : null}
      {open && Platform.OS === "ios" ? <Button variant="outline" label="Done" accessibilityLabel="Done" onPress={() => setOpen(false)} /> : null}
    </View>
  );
}

export function SelectField(props: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; error?: string }) {
  const theme = useTheme();
  return (
    <View style={{ gap: theme.space.xs }}>
      <AppText variant="label" tone="secondary">{props.label}</AppText>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.space.sm }}>
        {props.options.map((option) => {
          const selected = option.value === props.value;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={option.label}
              onPress={() => props.onChange(option.value)}
              style={{
                minHeight: theme.touchTarget,
                paddingHorizontal: theme.space.md,
                borderRadius: theme.radius.pill,
                borderWidth: 1,
                borderColor: selected ? theme.colors.primary : theme.colors.border,
                backgroundColor: selected ? theme.colors.primary : theme.colors.surface,
                justifyContent: "center",
              }}
            >
              <AppText variant="caption" tone={selected ? "inverse" : "primary"}>{option.label}</AppText>
            </Pressable>
          );
        })}
      </View>
      {props.error ? <AppText variant="caption" tone="danger">{props.error}</AppText> : null}
    </View>
  );
}

export function MultiSelect(props: { label: string; values: string[]; options: { value: string; label: string }[]; onChange: (values: string[]) => void }) {
  const theme = useTheme();
  return (
    <View style={{ gap: theme.space.xs }}>
      <AppText variant="label" tone="secondary">{props.label}</AppText>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.space.sm }}>
        {props.options.map((option) => {
          const selected = props.values.includes(option.value);
          return (
            <Pressable
              key={option.value}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: selected }}
              accessibilityLabel={option.label}
              onPress={() => props.onChange(selected ? props.values.filter((item) => item !== option.value) : [...props.values, option.value])}
              style={{ minHeight: theme.touchTarget, paddingHorizontal: theme.space.md, borderRadius: theme.radius.pill, borderWidth: 1, borderColor: selected ? theme.colors.primary : theme.colors.border, backgroundColor: selected ? theme.colors.primary : theme.colors.surface, justifyContent: "center" }}
            >
              <AppText variant="caption" tone={selected ? "inverse" : "primary"}>{option.label}</AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function Checkbox(props: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  const theme = useTheme();
  return (
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: props.checked }} accessibilityLabel={props.label} onPress={() => props.onChange(!props.checked)} style={{ flexDirection: "row", alignItems: "center", gap: theme.space.sm, minHeight: theme.touchTarget }}>
      <View style={{ width: 22, height: 22, borderRadius: 6, borderWidth: 1, borderColor: props.checked ? theme.colors.primary : theme.colors.border, backgroundColor: props.checked ? theme.colors.primary : theme.colors.surface }} />
      <AppText style={{ flex: 1 }}>{props.label}</AppText>
    </Pressable>
  );
}

export function RadioGroup(props: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }) {
  return <SelectField label={props.label} value={props.value} options={props.options} onChange={props.onChange} />;
}

export function SwitchField(props: { label: string; value: boolean; onChange: (value: boolean) => void }) {
  const theme = useTheme();
  return (
    <View style={{ minHeight: theme.touchTarget, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: theme.space.sm }}>
      <AppText style={{ flex: 1 }}>{props.label}</AppText>
      <Switch accessibilityLabel={props.label} value={props.value} onValueChange={props.onChange} trackColor={{ true: theme.colors.primary, false: theme.colors.border }} />
    </View>
  );
}

export function SegmentedControl(props: { values: string[]; selected: number; onChange: (index: number) => void; accessibilityLabel: string }) {
  const theme = useTheme();
  return (
    <View accessibilityRole="tablist" accessibilityLabel={props.accessibilityLabel} style={{ flexDirection: "row", backgroundColor: theme.colors.surfaceMuted, borderRadius: theme.radius.md, padding: 4 }}>
      {props.values.map((value, index) => {
        const selected = index === props.selected;
        return (
          <Pressable key={value} accessibilityRole="tab" accessibilityState={{ selected }} accessibilityLabel={value} onPress={() => props.onChange(index)} style={{ flex: 1, minHeight: theme.touchTarget, borderRadius: theme.radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: selected ? theme.colors.surface : "transparent", paddingHorizontal: 4 }}>
            <AppText variant="caption" weight="semibold" style={{ color: selected ? theme.colors.primary : theme.colors.textSecondary }}>{value}</AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Stepper(props: { label: string; value: number; onChange: (value: number) => void; min?: number }) {
  const theme = useTheme();
  const min = props.min ?? 0;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: theme.touchTarget }}>
      <AppText>{props.label}</AppText>
      <View style={{ flexDirection: "row", alignItems: "center", gap: theme.space.md }}>
        <Pressable accessibilityRole="button" accessibilityLabel={`${props.label} minus`} onPress={() => props.onChange(Math.max(min, props.value - 1))} style={{ width: theme.touchTarget, height: theme.touchTarget, alignItems: "center", justifyContent: "center" }}>
          <AppText weight="bold">−</AppText>
        </Pressable>
        <AppText weight="semibold">{String(props.value)}</AppText>
        <Pressable accessibilityRole="button" accessibilityLabel={`${props.label} plus`} onPress={() => props.onChange(props.value + 1)} style={{ width: theme.touchTarget, height: theme.touchTarget, alignItems: "center", justifyContent: "center" }}>
          <AppText weight="bold">+</AppText>
        </Pressable>
      </View>
    </View>
  );
}

export function QuantitySelector(props: { value: number; onChange: (value: number) => void }) {
  return <Stepper label="Qty" value={props.value} onChange={props.onChange} min={1} />;
}

function SliderTrack(props: { value: number; min: number; max: number; onChange: (value: number) => void; label: string }) {
  const theme = useTheme();
  const [width, setWidth] = useState(1);
  const ratio = (props.value - props.min) / Math.max(1, props.max - props.min);
  const update = (x: number) => {
    const next = props.min + (Math.min(width, Math.max(0, x)) / width) * (props.max - props.min);
    props.onChange(Math.round(next));
  };
  return (
    <View accessibilityLabel={props.label}>
      <AppText variant="caption" tone="secondary">{props.label}: {props.value}</AppText>
      <View
        onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
        onStartShouldSetResponder={() => true}
        onResponderMove={(event) => update(event.nativeEvent.locationX)}
        onResponderRelease={(event) => update(event.nativeEvent.locationX)}
        style={{ height: theme.touchTarget, justifyContent: "center" }}
      >
        <View style={{ height: 4, borderRadius: 2, backgroundColor: theme.colors.border }}>
          <View style={{ width: `${ratio * 100}%`, height: 4, borderRadius: 2, backgroundColor: theme.colors.primary }} />
        </View>
      </View>
    </View>
  );
}

export function Slider(props: { label: string; value: number; min?: number; max?: number; onChange: (value: number) => void }) {
  return <SliderTrack label={props.label} value={props.value} min={props.min ?? 0} max={props.max ?? 100} onChange={props.onChange} />;
}

export function RangeSlider(props: { label: string; minValue: number; maxValue: number; min?: number; max?: number; onChange: (min: number, max: number) => void }) {
  const floor = props.min ?? 0;
  const ceiling = props.max ?? 100;
  return (
    <View>
      <SliderTrack label={`${props.label} min`} value={props.minValue} min={floor} max={ceiling} onChange={(value) => props.onChange(Math.min(value, props.maxValue), props.maxValue)} />
      <SliderTrack label={`${props.label} max`} value={props.maxValue} min={floor} max={ceiling} onChange={(value) => props.onChange(props.minValue, Math.max(value, props.minValue))} />
    </View>
  );
}

export function ProgressBar(props: { value: number; label?: string }) {
  const theme = useTheme();
  const ratio = Math.max(0, Math.min(1, props.value));
  return (
    <View accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(ratio * 100) }}>
      {props.label ? <AppText variant="caption" tone="secondary">{props.label}</AppText> : null}
      <View style={{ height: 8, borderRadius: 4, backgroundColor: theme.colors.border, marginTop: 6 }}>
        <View style={{ width: `${ratio * 100}%`, height: 8, borderRadius: 4, backgroundColor: theme.colors.primary }} />
      </View>
    </View>
  );
}

export function Tabs(props: { tabs: { id: string; label: string }[]; selected: string; onChange: (id: string) => void }) {
  const theme = useTheme();
  return (
    <View accessibilityRole="tablist" style={{ flexDirection: "row", flexWrap: "wrap", gap: theme.space.sm }}>
      {props.tabs.map((tab) => {
        const selected = tab.id === props.selected;
        return (
          <Pressable
            key={tab.id}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={tab.label}
            onPress={() => props.onChange(tab.id)}
            style={{ minHeight: theme.touchTarget, paddingHorizontal: theme.space.md, borderRadius: theme.radius.pill, borderWidth: 1, borderColor: selected ? theme.colors.primary : theme.colors.border, backgroundColor: selected ? theme.colors.primary : theme.colors.surface, justifyContent: "center" }}
          >
            <AppText variant="caption" weight="semibold" style={{ color: selected ? theme.colors.white : theme.colors.text }}>{tab.label}</AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

export function Accordion(props: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const theme = useTheme();
  return (
    <View style={{ borderWidth: 1, borderColor: theme.colors.border, borderRadius: theme.radius.md, backgroundColor: theme.colors.surface }}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} accessibilityLabel={props.title} onPress={() => setOpen((current) => !current)} style={{ minHeight: theme.touchTarget, justifyContent: "center", paddingHorizontal: theme.space.lg }}>
        <AppText weight="semibold">{props.title}</AppText>
      </Pressable>
      {open ? <View style={{ padding: theme.space.lg, paddingTop: 0 }}>{props.children}</View> : null}
    </View>
  );
}

export function CollapsiblePanel(props: { title: string; children: ReactNode }) {
  return <Accordion title={props.title}>{props.children}</Accordion>;
}
