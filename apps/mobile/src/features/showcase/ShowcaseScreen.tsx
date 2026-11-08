import { useState } from "react";
import { View } from "react-native";
import { Button, ButtonRow } from "@/components/buttons/Button";
import { DefaultCard, KPICard, ListCard, ProductCard, StatusCard, TransactionCard } from "@/components/cards/Cards";
import { BarChart } from "@/components/charts/Charts";
import { StatusBadge } from "@/components/feedback/Feedback";
import { Accordion, Checkbox, ProgressBar, QuantitySelector, RangeSlider, SearchInput, SegmentedControl, Slider, SwitchField } from "@/components/inputs/Fields";
import { Input } from "@/components/inputs/Input";
import { VirtualizedList } from "@/components/lists/VirtualizedList";
import { ScreenContainer, ScreenTitle } from "@/components/layout/Screen";
import { BottomSheet } from "@/components/overlays/Overlays";
import { useI18n } from "@/i18n/I18nProvider";

const sample = [
  { id: "1", name: "Sample item" },
  { id: "2", name: "Second item" },
];

export function ShowcaseScreen() {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const [on, setOn] = useState(true);
  const [qty, setQty] = useState(1);
  const [slider, setSlider] = useState(40);
  const [sheet, setSheet] = useState(false);
  const [segment, setSegment] = useState(0);
  return (
    <ScreenContainer scroll>
      <ScreenTitle title={t("designSystem")} subtitle="Sample controls. Business screens load live data." />
      <ButtonRow>
        <Button label="Primary" accessibilityLabel="Primary" onPress={() => undefined} />
        <Button variant="secondary" label="Secondary" accessibilityLabel="Secondary" onPress={() => undefined} />
        <Button variant="outline" label="Outline" accessibilityLabel="Outline" onPress={() => undefined} />
        <Button variant="ghost" label="Ghost" accessibilityLabel="Ghost" onPress={() => undefined} />
        <Button variant="danger" label="Danger" accessibilityLabel="Danger" onPress={() => undefined} />
        <Button variant="success" label="Success" accessibilityLabel="Success" onPress={() => undefined} />
        <Button variant="text" label="Text" accessibilityLabel="Text" onPress={() => undefined} />
        <Button variant="link" label="Link" accessibilityLabel="Link" onPress={() => undefined} />
        <Button size="xs" label="XS" accessibilityLabel="Extra small" onPress={() => undefined} />
        <Button size="xl" label="XL" accessibilityLabel="Extra large" onPress={() => undefined} />
      </ButtonRow>
      <Input label="Text" accessibilityLabel="Text" placeholder="Name" />
      <Input variant="password" label="Password" accessibilityLabel="Password" value="secret" />
      <SearchInput value={search} onChangeText={setSearch} placeholder={t("search")} accessibilityLabel={t("search")} />
      <SwitchField label="Enabled" value={on} onChange={setOn} />
      <Checkbox label="Checked" checked={on} onChange={setOn} />
      <SegmentedControl values={["Today", "Week", "Month"]} selected={segment} onChange={setSegment} accessibilityLabel="Range" />
      <QuantitySelector value={qty} onChange={setQty} />
      <Slider label="Progress target" value={slider} onChange={setSlider} />
      <RangeSlider label="Range" minValue={10} maxValue={slider} onChange={(min) => setSlider(min)} />
      <ProgressBar value={slider / 100} label="Progress" />
      <StatusBadge label="Open" tone="info" />
      <View style={{ flexDirection: "row", gap: 8 }}>
        <View style={{ flex: 1 }}><KPICard title="Sample" value="128" trend="up" percentage="+4%" comparison="vs yesterday" /></View>
        <View style={{ flex: 1 }}><StatusCard title="Register" status="Open" tone="success" /></View>
      </View>
      <DefaultCard title="Card"><AppTextSample /></DefaultCard>
      <ProductCard name="Sample product" sku="SKU-1" price="AED 12.00" stock="4 on hand" />
      <TransactionCard title="Receipt 1001" when="Today" amount="AED 42.00" status="Paid" />
      <ListCard title="List row" subtitle="Subtitle" amount="AED 8.00" status="Active" />
      <BarChart title="Sample" values={[{ label: "A", value: 4 }, { label: "B", value: 9 }]} />
      <Accordion title="More"><Input label="Inside" accessibilityLabel="Inside" /></Accordion>
      <Button variant="outline" label="Bottom sheet" accessibilityLabel="Bottom sheet" onPress={() => setSheet(true)} />
      <BottomSheet visible={sheet} title="Actions" onClose={() => setSheet(false)}>
        <Button label="Close" accessibilityLabel="Close" onPress={() => setSheet(false)} />
      </BottomSheet>
      <View style={{ height: 220 }}>
        <VirtualizedList data={sample} keyExtractor={(item) => item.id} renderItem={(item) => <ListCard title={item.name} />} />
      </View>
    </ScreenContainer>
  );
}

function AppTextSample() {
  return null;
}
