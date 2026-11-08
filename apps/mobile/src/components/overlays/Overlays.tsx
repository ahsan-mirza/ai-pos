import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Modal, Pressable, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Button } from "@/components/buttons/Button";
import { StickyActionBar } from "@/components/layout/Screen";
import { AppText } from "@/components/primitives/Text";
import { useI18n } from "@/i18n/I18nProvider";
import { modalMaxHeight, sheetMaxHeight } from "@/hooks/breakpoints";
import { useWindowSize } from "@/hooks/useResponsive";
import { useTheme } from "@/theme/ThemeProvider";

interface ToastItem {
  id: number;
  message: string;
  tone: "info" | "success" | "danger";
}

const ToastContext = createContext<{ show: (message: string, tone?: ToastItem["tone"]) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const show = useCallback((message: string, tone: ToastItem["tone"] = "info") => {
    const id = Date.now();
    setItems((current) => [...current, { id, message, tone }]);
    setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 3200);
  }, []);
  const value = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <View pointerEvents="none" style={{ position: "absolute", left: 16, right: 16, top: insets.top + 8, gap: 8 }}>
        {items.map((item) => (
          <View key={item.id} style={{ backgroundColor: item.tone === "danger" ? theme.colors.danger : item.tone === "success" ? theme.colors.success : theme.colors.text, borderRadius: theme.radius.md, padding: theme.space.md }}>
            <AppText tone="inverse">{item.message}</AppText>
          </View>
        ))}
      </View>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const value = useContext(ToastContext);
  if (value === null) throw new Error("useToast must be used inside ToastProvider.");
  return value;
}

export function Snackbar(props: { message: string }) {
  const theme = useTheme();
  return (
    <View style={{ backgroundColor: theme.colors.text, borderRadius: theme.radius.md, padding: theme.space.md }}>
      <AppText tone="inverse">{props.message}</AppText>
    </View>
  );
}

export function AppModal(props: { visible: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const theme = useTheme();
  const { t, isRTL } = useI18n();
  const insets = useSafeAreaInsets();
  const window = useWindowSize();
  return (
    <Modal visible={props.visible} transparent animationType="fade" onRequestClose={props.onClose} statusBarTranslucent navigationBarTranslucent>
      <Pressable accessibilityLabel={t("cancel")} onPress={props.onClose} style={{ flex: 1, backgroundColor: theme.colors.overlay, justifyContent: "center", paddingHorizontal: theme.space.lg, paddingTop: insets.top + theme.space.lg, paddingBottom: insets.bottom + theme.space.lg }}>
        <Pressable onPress={() => undefined} style={{ maxHeight: modalMaxHeight(window.height, insets.top, insets.bottom), backgroundColor: theme.colors.surface, borderRadius: theme.radius.lg, direction: isRTL ? "rtl" : "ltr" }}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: theme.space.lg, gap: theme.space.md }}>
            <AppText variant="heading">{props.title}</AppText>
            {props.children}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export function BottomSheet(props: { visible: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const theme = useTheme();
  const window = useWindowSize();
  const insets = useSafeAreaInsets();
  const { t, isRTL } = useI18n();
  return (
    <Modal visible={props.visible} transparent animationType="slide" onRequestClose={props.onClose} statusBarTranslucent navigationBarTranslucent>
      <Pressable accessibilityLabel={t("cancel")} onPress={props.onClose} style={{ flex: 1, backgroundColor: theme.colors.overlay, justifyContent: "flex-end" }}>
        <Pressable onPress={() => undefined} style={{ maxHeight: sheetMaxHeight(window.height, insets.top, insets.bottom), backgroundColor: theme.colors.surface, borderTopLeftRadius: theme.radius.xl, borderTopRightRadius: theme.radius.xl, paddingBottom: insets.bottom, direction: isRTL ? "rtl" : "ltr" }}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: theme.space.lg, gap: theme.space.md }}>
            <View style={{ alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: theme.colors.border }} />
            <AppText variant="heading">{props.title}</AppText>
            {props.children}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

export function ConfirmationDialog(props: { visible: boolean; title: string; message: string; confirmLabel?: string; danger?: boolean; loading?: boolean; onConfirm: () => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <AppModal visible={props.visible} title={props.title} onClose={props.onClose}>
      <AppText tone="secondary">{props.message}</AppText>
      <StickyActionBar>
        <Button fullWidth variant="outline" label={t("cancel")} accessibilityLabel={t("cancel")} onPress={props.onClose} />
        <Button fullWidth variant={props.danger ? "danger" : "primary"} label={props.confirmLabel ?? t("confirm")} accessibilityLabel={props.confirmLabel ?? t("confirm")} loading={props.loading} onPress={props.onConfirm} />
      </StickyActionBar>
    </AppModal>
  );
}

export function ActionSheet(props: { visible: boolean; title: string; actions: { label: string; onPress: () => void; danger?: boolean }[]; onClose: () => void }) {
  return (
    <BottomSheet visible={props.visible} title={props.title} onClose={props.onClose}>
      {props.actions.map((action) => (
        <Button key={action.label} variant={action.danger ? "danger" : "outline"} fullWidth label={action.label} accessibilityLabel={action.label} onPress={action.onPress} />
      ))}
    </BottomSheet>
  );
}

export function Dropdown(props: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false);
  const selected = props.options.find((option) => option.value === props.value)?.label ?? props.value;
  return (
    <View>
      <Button variant="outline" label={selected || props.label} accessibilityLabel={props.label} onPress={() => setOpen(true)} />
      <BottomSheet visible={open} title={props.label} onClose={() => setOpen(false)}>
        {props.options.map((option) => (
          <Button key={option.value} variant={option.value === props.value ? "primary" : "ghost"} fullWidth label={option.label} accessibilityLabel={option.label} onPress={() => { props.onChange(option.value); setOpen(false); }} />
        ))}
      </BottomSheet>
    </View>
  );
}
